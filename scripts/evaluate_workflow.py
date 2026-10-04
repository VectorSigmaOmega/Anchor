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
from anchor.providers.gemini import GeminiAPIClient, GeminiEmbeddingProvider, GeminiGenerationProvider, _extract_text
from anchor.providers.rerank import CohereRerankProvider
from anchor.providers.workflow import GeminiWorkflowProvider
from anchor.schemas import RetrievedChunk
from anchor.services.metrics import Metrics
from anchor.services.tracing import NullSpan, NullTrace
from scripts.evaluate_quality import failures
from scripts.prepare_chunking_experiment import experiment_settings


class RecordedSpan(NullSpan):
    def __init__(self, rows, name, input=None):
        self.rows, self.name, self.input = rows, name, input
        self.started = perf_counter()

    def end(self, output=None):
        self.rows.append({"name": self.name, "input": self.input, "output": output,
                          "seconds": perf_counter() - self.started})


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


def replay_context(chunks):
    async def retrieve(*args, **kwargs):
        return chunks, chunks

    return retrieve


async def run(args):
    base = Settings()
    base.langfuse_public_key = base.langfuse_secret_key = ""
    base.generation_model = args.generation_model or args.model
    base.multipart_generation_model = args.model
    base.retrieval_plan_model = args.plan_model
    base.workflow_draft_model = args.draft_model
    base.generation_thinking_level = "low"
    base.max_completion_tokens = base.multipart_max_completion_tokens = 4096
    base.gemini_max_retries = 2
    base.gemini_retry_base_seconds = 1
    settings = experiment_settings(base, "structured")
    cases = [json.loads(line) for line in Path(args.dataset).read_text().splitlines()]
    if args.only:
        cases = [c for c in cases if c["id"] in args.only.split(",")]
    replay_rows = {}
    if args.replay_context:
        for line in Path(args.replay_context).read_text().splitlines():
            row = json.loads(line)
            if row.get("variant") == "workflow" and row.get("context"):
                replay_rows[row["id"]] = [RetrievedChunk.model_validate(chunk) for chunk in row["context"]]
        missing = {case["id"] for case in cases} - replay_rows.keys()
        if missing:
            raise ValueError(f"No frozen context for: {', '.join(sorted(missing))}")
    db = Database(settings)
    await db.open()
    events = []
    original_post = GeminiAPIClient.post
    original_review = GeminiWorkflowProvider.structured_review
    original_generate = GeminiWorkflowProvider.generate
    reviews = []
    drafts = []

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
        event = {"path": path, "usage": response.get("usageMetadata", {}), "seconds": perf_counter() - started}
        schema = payload.get("generationConfig", {}).get("responseJsonSchema", {})
        if "sections" in schema.get("properties", {}):
            event["raw_sectioned_output"] = _extract_text(response)
        events.append(event)
        return response

    async def recorded_generate(self, *, question, context_chunks, retry_note=None):
        result = await original_generate(self, question=question, context_chunks=context_chunks, retry_note=retry_note)
        drafts.append(result.model_dump(mode="json"))
        return result

    GeminiAPIClient.post = recorded_post
    GeminiWorkflowProvider.structured_review = recorded_review
    GeminiWorkflowProvider.generate = recorded_generate
    try:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        done = {(r["variant"], r["id"]) for r in map(json.loads, output.read_text().splitlines())} if output.exists() else set()
        with output.open("a") as file:
            for variant in args.variants.split(","):
                current = settings.model_copy(update={
                    "multipart_workflow_enabled": variant in {"workflow", "lean"},
                    "workflow_topic_review_enabled": variant != "lean",
                    "linear_source_comparison_enabled": variant == "linear_compare",
                })
                for case in cases:
                    if (variant, case["id"]) in done:
                        continue
                    tracer = RecordedTracer()
                    service = QueryService(settings=current, repository=AnchorRepository(db, current),
                                           embedding_provider=GeminiEmbeddingProvider(current),
                                           generation_provider=GeminiGenerationProvider(current),
                                           rerank_provider=CohereRerankProvider(current), tracer=tracer,
                                           metrics=Metrics("anchor_workflow_eval"))
                    if replay_rows:
                        service._retrieve_context = replay_context(replay_rows[case["id"]])
                    events.clear()
                    reviews.clear()
                    drafts.clear()
                    started = perf_counter()
                    row = {"variant": variant, "id": case["id"], "question": case["question"],
                           "model": current.generation_model, "plan_model": current.retrieval_plan_model,
                           "draft_model": current.workflow_draft_model,
                           "replayed_context": bool(replay_rows)}
                    try:
                        result = await service.execute(case["question"])
                        response = result.response.model_dump(mode="json")
                        row.update(response=response, pattern_failures=failures(case, response),
                                   context=[c.model_dump() for c in result.context_chunks])
                    except Exception as exc:
                        cause = exc.__cause__
                        row.update(error=f"{type(exc).__name__}: {exc}",
                                   cause_type=type(cause).__name__ if cause else None,
                                   pattern_failures=["runtime error"])
                    row.update(seconds=perf_counter() - started, provider_calls=events.copy(), trace=tracer.rows,
                               reviews=reviews.copy(), drafts=drafts.copy())
                    file.write(json.dumps(row) + "\n")
                    file.flush()
                    print(json.dumps({k: row[k] for k in ["variant", "id", "pattern_failures", "seconds"]}), flush=True)
                    await asyncio.sleep(args.pause)
    finally:
        GeminiAPIClient.post = original_post
        GeminiWorkflowProvider.structured_review = original_review
        GeminiWorkflowProvider.generate = original_generate
        await db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="eval/workflow_quality.jsonl")
    parser.add_argument("--output", default=".benchmarks/workflow/answers.jsonl")
    parser.add_argument("--variants", default="linear,workflow")
    parser.add_argument("--model", default="gemini-3.5-flash-lite")
    parser.add_argument("--generation-model", help="Model for ordinary questions; defaults to --model.")
    parser.add_argument("--plan-model")
    parser.add_argument("--draft-model")
    parser.add_argument("--only")
    parser.add_argument("--pause", type=float, default=13)
    parser.add_argument("--replay-context", help="Recorded workflow contexts; skips retrieval to isolate answer behavior.")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
