"""Run source-reviewed QA cases against an existing corpus; no ingestion writes.

python -m scripts.evaluate_quality --output /tmp/anchor-quality.jsonl
"""

import argparse
import asyncio
import json
import re
from pathlib import Path
from time import perf_counter

from anchor.config import Settings
from anchor.db.pool import Database
from anchor.db.repository import AnchorRepository
from anchor.pipeline.citations import validate_and_hydrate_citations
from anchor.pipeline.service import QueryService, contextualize_question
from anchor.providers.gemini import GeminiEmbeddingProvider, GeminiGenerationProvider
from anchor.providers.rerank import CohereRerankProvider
from anchor.schemas import ConversationTurn, QueryExecutionResult, QueryResponse, RetrievedChunk
from anchor.services.metrics import Metrics
from anchor.services.tracing import NullTrace, Tracer


def failures(case: dict, response: dict) -> list[str]:
    expected = "answered" if case["expected_outcome"] == "answer" else "refused"
    if response.get("status") != expected:
        return [f"expected {expected}, got {response.get('status')}: {response.get('refusal_reason')}"]
    if expected == "refused":
        return []
    result = []
    answer = re.sub(r"(?<=\d),(?=\d)", "", response["answer"])
    for pattern in case["required_patterns"]:
        if not re.search(pattern, answer, re.IGNORECASE):
            result.append("missing fact: " + pattern)
    if not any(citation["doc_id"] in case["doc_ids"] for citation in response["citations"]):
        result.append("missing expected source")
    cited_documents = {citation["doc_id"] for citation in response["citations"]}
    for doc_id in case.get("required_doc_ids", []):
        if doc_id not in cited_documents:
            result.append("missing required source: " + doc_id)
    return result


async def run(args):
    settings = Settings()
    settings.langfuse_public_key = ""
    settings.langfuse_secret_key = ""
    settings.gemini_max_retries = 2
    settings.gemini_retry_base_seconds = 1
    database = Database(settings)
    await database.open()
    cases = [json.loads(line) for line in Path(args.dataset).read_text().splitlines() if line.strip()]
    contexts = {}
    if args.contexts:
        contexts = {row["id"]: row for row in map(json.loads, Path(args.contexts).read_text().splitlines())}
    if args.only:
        cases = [case for case in cases if case["id"] in args.only.split(",")]
    if not cases:
        await database.close()
        raise ValueError("No evaluation cases selected")
    failed = False
    try:
        with Path(args.output).open("w") as output:
            for model in args.models.split(",") if args.models else [settings.generation_model]:
                overrides = {"generation_model": model}
                if args.models:
                    overrides["multipart_generation_model"] = model
                current = settings.model_copy(update=overrides)
                generation = GeminiGenerationProvider(current)
                service = QueryService(
                    settings=current,
                    repository=AnchorRepository(database, current),
                    embedding_provider=GeminiEmbeddingProvider(current),
                    generation_provider=generation,
                    rerank_provider=CohereRerankProvider(current),
                    tracer=Tracer(current),
                    metrics=Metrics("anchor_quality"),
                )
                passed = 0
                for case in cases:
                    started = perf_counter()
                    record = {"id": case["id"], "model": model, "question": case["question"]}
                    try:
                        generation.last_usage_metadata = {}
                        history = [ConversationTurn(**turn) for turn in case.get("history", [])]
                        if args.contexts:
                            chunks = [RetrievedChunk(**chunk) for chunk in contexts[case["id"]].get("context", [])]
                            question = contextualize_question(case["question"], history)
                            model_response = await service._generate_with_retry(question, chunks, NullTrace())
                            valid, citations = validate_and_hydrate_citations(
                                model_response, chunks, max_rendered=current.max_citations,
                            )
                            if not valid:
                                model_response = await generation.generate(
                                    question=question, context_chunks=chunks,
                                    retry_note=service._validation_retry_note(model_response),
                                )
                                valid, citations = validate_and_hydrate_citations(
                                    model_response, chunks, max_rendered=current.max_citations,
                                )
                            if not valid:
                                record["invalid_model_response"] = model_response.model_dump(mode="json")
                                raise ValueError("invalid supporting citations")
                            result = QueryExecutionResult(
                                response=QueryResponse(
                                    request_id="quality-replay", status=model_response.status, answer=model_response.answer,
                                    refusal_reason=model_response.refusal_reason, citations=citations,
                                    disclaimer="Corpus evaluation.", latency_ms=int((perf_counter() - started) * 1000),
                                ),
                                context_chunks=chunks,
                            )
                        else:
                            result = await service.execute(case["question"], history=history)
                        response = result.response.model_dump(mode="json")
                        record["model"] = getattr(generation, "last_model_used", model)
                        errors = failures(case, response)
                        record.update(
                            response=response,
                            failures=errors,
                            context=[chunk.model_dump(mode="json") for chunk in result.context_chunks],
                            retrieved=[
                                {"chunk_id": chunk.chunk_id, "doc_id": chunk.doc_id, "score": chunk.relevance_score}
                                for chunk in result.retrieved_chunks
                            ],
                            usage=generation.last_usage_metadata,
                        )
                        passed += not errors
                    except Exception as exc:
                        record.update(failures=[f"{type(exc).__name__}: {exc}"])
                    record["elapsed_seconds"] = round(perf_counter() - started, 3)
                    failed |= bool(record["failures"])
                    output.write(json.dumps(record) + "\n")
                    output.flush()
                    print(json.dumps({
                        "id": case["id"], "model": record["model"], "failures": record["failures"], "elapsed": record["elapsed_seconds"]
                    }), flush=True)
                    if args.pause:
                        await asyncio.sleep(args.pause)
                print(json.dumps({
                    "model": model if args.models else "configured routing",
                    "passed": passed, "total": len(cases),
                }), flush=True)
    finally:
        await database.close()
    return int(failed)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="eval/quality.jsonl")
    parser.add_argument("--models", help="Pin both ordinary and multipart generation to these models; default uses configured routing.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--only")
    parser.add_argument("--pause", type=float, default=6.5, help="Pause between cases; default respects Cohere's trial quota.")
    parser.add_argument("--contexts", help="Replay stored passages for generation-only model comparison.")
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
