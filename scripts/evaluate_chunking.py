"""Controlled real-provider comparison; cached plans/query vectors are shared.

Latency excludes planning and query embedding for every variant. Production
code, prompts, reranker, budgets and answer model stay identical across indexes.
"""

import argparse
import asyncio
import json
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from anchor.config import Settings
from anchor.db.pool import Database
from anchor.db.repository import AnchorRepository
from anchor.pipeline.service import QueryService
from anchor.providers.gemini import GeminiEmbeddingProvider, GeminiGenerationProvider
from anchor.providers.rerank import CohereRerankProvider
from anchor.services.metrics import Metrics
from anchor.services.tracing import Tracer
from scripts.evaluate_quality import failures
from scripts.prepare_chunking_experiment import ROOT, experiment_settings


class CachedEmbedding(GeminiEmbeddingProvider):
    def __init__(self, settings, cache):
        super().__init__(settings)
        self.cache = cache

    async def embed_query(self, text):
        key = sha256(text.encode()).hexdigest()
        return self.cache["queries"][key]


class RecordedGeneration(GeminiGenerationProvider):
    def __init__(self, settings, cache):
        super().__init__(settings)
        self.cache = cache
        self.usages = []

    async def plan_retrieval_questions(self, question):
        return self.cache["plans"][question]

    async def generate(self, **kwargs):
        response = await super().generate(**kwargs)
        self.usages.append(self.last_usage_metadata.copy())
        return response


class RecordedReranker(CohereRerankProvider):
    async def rerank(self, question, candidates, top_n):
        self.candidates = list(candidates)
        return await super().rerank(question, candidates, top_n)


async def warm_cache(settings, cases):
    from anchor.pipeline.service import is_multipart_question

    path = ROOT / "query-cache.json"
    cache = json.loads(path.read_text()) if path.exists() else {"plans": {}, "queries": {}}
    generation = GeminiGenerationProvider(settings)
    embedding = GeminiEmbeddingProvider(settings)
    for case in cases:
        if case["expected_outcome"] != "answer":
            continue
        question = case["question"]
        if question not in cache["plans"]:
            cache["plans"][question] = await generation.plan_retrieval_questions(question) if is_multipart_question(question) else []
        queries = [question, *cache["plans"][question]]
        for query in queries:
            key = sha256(query.encode()).hexdigest()
            if key not in cache["queries"]:
                cache["queries"][key] = await embedding.embed_query(query)
        path.write_text(json.dumps(cache))
        print(json.dumps({"cached": case["id"], "queries": len(queries)}), flush=True)
    return cache


async def run(args):
    settings = Settings()
    settings.langfuse_public_key = ""
    settings.langfuse_secret_key = ""
    settings.generation_model = "gemini-3.5-flash-lite"
    settings.multipart_generation_model = "gemini-3.5-flash-lite"
    settings.generation_thinking_level = "low"
    settings.max_completion_tokens = 4096
    settings.multipart_max_completion_tokens = 4096
    settings.gemini_max_retries = 3
    settings.gemini_retry_base_seconds = 2
    cases = [json.loads(line) for line in Path(args.dataset).read_text().splitlines()]
    if args.only:
        cases = [c for c in cases if c["id"] in args.only.split(",")]
    cache = await warm_cache(settings, cases)
    if args.warm_only:
        return
    for strategy in args.strategies.split(","):
        current = settings if strategy == "baseline" else experiment_settings(settings, strategy)
        db = Database(current)
        await db.open()
        try:
            repository = AnchorRepository(db, current)
            await repository.validate_embedding_profile()
            generation = RecordedGeneration(current, cache)
            reranker = RecordedReranker(current)
            service = QueryService(
                settings=current,
                repository=repository,
                embedding_provider=CachedEmbedding(current, cache),
                generation_provider=generation,
                rerank_provider=reranker,
                tracer=Tracer(current),
                metrics=Metrics("anchor_chunking"),
            )
            output_path = ROOT / (strategy + ".answers.jsonl")
            done = set()
            if output_path.exists():
                done = {r["id"] for r in map(json.loads, output_path.read_text().splitlines())}
            with output_path.open("a") as output:
                for case in cases:
                    if case["id"] in done:
                        continue
                    generation.usages = []
                    reranker.candidates = []
                    started = perf_counter()
                    row = {
                        "id": case["id"],
                        "strategy": strategy,
                        "question": case["question"],
                        "plans": cache["plans"].get(case["question"], []),
                    }
                    try:
                        result = await asyncio.wait_for(service.execute(case["question"]), timeout=current.query_timeout_seconds)
                        response = result.response.model_dump(mode="json")
                        row.update(
                            response=response,
                            pattern_failures=failures(case, response),
                            model=getattr(generation, "last_model_used", None),
                            context=[c.model_dump(mode="json") for c in result.context_chunks],
                            reranked=[c.model_dump(mode="json") for c in result.retrieved_chunks],
                            candidates=[c.model_dump(mode="json") for c in reranker.candidates],
                            generation_usages=generation.usages,
                        )
                    except Exception as exc:
                        row.update(error=f"{type(exc).__name__}: {exc}", pattern_failures=["runtime error"])
                    row["elapsed_seconds"] = round(perf_counter() - started, 3)
                    output.write(json.dumps(row) + "\n")
                    output.flush()
                    print(json.dumps({k: row[k] for k in ["strategy", "id", "pattern_failures", "elapsed_seconds"]}), flush=True)
                    await asyncio.sleep(7)
        finally:
            await db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="eval/chunking_quality.jsonl")
    parser.add_argument("--strategies", default="baseline,fixed,structured")
    parser.add_argument("--only")
    parser.add_argument("--warm-only", action="store_true")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
