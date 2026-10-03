"""Compare the linear and bounded graph pipelines on an unchanged local index."""

import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter

from anchor.config import Settings
from anchor.db.pool import Database
from anchor.db.repository import AnchorRepository
from anchor.pipeline.service import QueryService
from anchor.providers.gemini import GeminiAPIClient, GeminiEmbeddingProvider, GeminiGenerationProvider
from anchor.providers.rerank import CohereRerankProvider
from anchor.providers.workflow import GeminiWorkflowProvider
from anchor.services.metrics import Metrics
from anchor.services.tracing import NullSpan, NullTrace
from scripts.evaluate_quality import failures
from scripts.prepare_chunking_experiment import experiment_settings


class RecordedSpan(NullSpan):
    def __init__(self, rows, name, input=None):
        self.rows, self.name, self.input = rows, name, input

    def end(self, output=None):
        self.rows.append({"name": self.name, "input": self.input, "output": output})


class RecordedTrace(NullTrace):
    def __init__(self, rows):
        super().__init__()
        self.rows = rows

    def span(self, name, input=None):
        return RecordedSpan(self.rows, name, input)

    def generation(self, name, model, input=None):
        return RecordedSpan(self.rows, name, {"model": model, "input": input})


class RecordedTracer:
    def __init__(self):
        self.rows = []

    def start_query_trace(self, **kwargs):
        return RecordedTrace(self.rows)


async def run(args):
    base = Settings()
    base.langfuse_public_key = base.langfuse_secret_key = ""
    base.generation_model = base.multipart_generation_model = "gemini-3.5-flash-lite"
    base.generation_thinking_level = "low"
    base.max_completion_tokens = base.multipart_max_completion_tokens = 4096
    base.gemini_max_retries = 2
    base.gemini_retry_base_seconds = 1
    settings = experiment_settings(base, "structured")
    cases = [json.loads(line) for line in Path(args.dataset).read_text().splitlines()]
    if args.only:
        cases = [c for c in cases if c["id"] in args.only.split(",")]
    db = Database(settings)
    await db.open()
    events = []
    original_post = GeminiAPIClient.post
    original_review = GeminiWorkflowProvider.structured_review
    reviews = []

    async def recorded_review(self, task, content, schema, **kwargs):
        data = await original_review(self, task, content, schema, **kwargs)
        reviews.append(data)
        return data

    async def recorded_post(self, path, payload):
        started = perf_counter()
        try:
            response = await original_post(self, path, payload)
        except Exception as exc:
            events.append({"path": path, "error": type(exc).__name__, "seconds": perf_counter() - started})
            raise
        events.append({"path": path, "usage": response.get("usageMetadata", {}), "seconds": perf_counter() - started})
        return response

    GeminiAPIClient.post = recorded_post
    GeminiWorkflowProvider.structured_review = recorded_review
    try:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        done = {(r["variant"], r["id"]) for r in map(json.loads, output.read_text().splitlines())} if output.exists() else set()
        with output.open("a") as file:
            for variant in args.variants.split(","):
                current = settings.model_copy(update={"multipart_workflow_enabled": variant == "workflow"})
                for case in cases:
                    if (variant, case["id"]) in done:
                        continue
                    tracer = RecordedTracer()
                    service = QueryService(settings=current, repository=AnchorRepository(db, current),
                                           embedding_provider=GeminiEmbeddingProvider(current),
                                           generation_provider=GeminiGenerationProvider(current),
                                           rerank_provider=CohereRerankProvider(current), tracer=tracer,
                                           metrics=Metrics("anchor_workflow_eval"))
                    events.clear()
                    reviews.clear()
                    started = perf_counter()
                    row = {"variant": variant, "id": case["id"], "question": case["question"], "model": current.generation_model}
                    try:
                        result = await service.execute(case["question"])
                        response = result.response.model_dump(mode="json")
                        row.update(response=response, pattern_failures=failures(case, response),
                                   context=[c.model_dump() for c in result.context_chunks])
                    except Exception as exc:
                        row.update(error=f"{type(exc).__name__}: {exc}", pattern_failures=["runtime error"])
                    row.update(seconds=perf_counter() - started, provider_calls=events.copy(), trace=tracer.rows, reviews=reviews.copy())
                    file.write(json.dumps(row) + "\n")
                    file.flush()
                    print(json.dumps({k: row[k] for k in ["variant", "id", "pattern_failures", "seconds"]}), flush=True)
                    await asyncio.sleep(args.pause)
    finally:
        GeminiAPIClient.post = original_post
        GeminiWorkflowProvider.structured_review = original_review
        await db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="eval/workflow_quality.jsonl")
    parser.add_argument("--output", default=".benchmarks/workflow/answers.jsonl")
    parser.add_argument("--variants", default="linear,workflow")
    parser.add_argument("--only")
    parser.add_argument("--pause", type=float, default=13)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
