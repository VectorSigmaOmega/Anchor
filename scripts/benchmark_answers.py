"""Run substantive regulatory questions against the configured corpus and models.

The report preserves answers and their context for human review. Phrase checks
catch known omissions and numerical regressions; they do not prove entailment.
"""

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from anchor.config import get_settings
from anchor.eval.runner import build_live_eval_service
from anchor.providers.gemini import ProviderError
from anchor.schemas import ConversationTurn


def normalize(text: str) -> str:
    return "".join(char for char in text.casefold() if char.isalnum())


async def run(args: argparse.Namespace) -> int:
    rows = [json.loads(line) for line in args.dataset.read_text().splitlines() if line.strip()]
    if args.limit:
        rows = rows[:args.limit]
    service = await build_live_eval_service()
    settings = get_settings()
    samples = []
    try:
        for row in rows:
            started = time.monotonic()
            try:
                result = await service.query_service.execute(
                    row["question"], history=[ConversationTurn.model_validate(turn) for turn in row.get("history", [])]
                )
                answer = normalize(result.response.answer)
                fact_checks = [any(normalize(option) in answer for option in group) for group in row.get("required_facts", [])]
                source_checks = result.response.status != "answered" or (
                    bool(result.response.citations)
                    and all(c.doc_id in row.get("doc_ids", []) for c in result.response.citations)
                )
                passed = (
                    result.response.status == row["expected_status"] and all(fact_checks) and source_checks
                    and not any(normalize(phrase) in answer for phrase in row.get("forbidden_phrases", []))
                )
                sample = {"case": row, "passed": passed, "fact_checks": fact_checks,
                          "response": result.response.model_dump(),
                          "context": [chunk.model_dump() for chunk in result.context_chunks],
                          "retrieved_top5": [chunk.chunk_id for chunk in result.retrieved_chunks[:5]]}
            except ProviderError as exc:
                sample = {"case": row, "passed": False, "error": {"provider": exc.provider, "http_status": exc.status_code}}
            samples.append(sample)
            print(json.dumps({"id": row["id"], "passed": sample["passed"],
                              "status": sample.get("response", {}).get("status", "error")}), flush=True)
            if sample.get("error", {}).get("http_status") in {401, 402, 403}:
                break
            if row is not rows[-1]:
                await asyncio.sleep(max(0, args.pause_seconds - (time.monotonic() - started)))
    finally:
        await service.close()
    report = {
        "run_at": datetime.now(UTC).isoformat(), "dataset": str(args.dataset), "fixture_mode": False,
        "generation_provider": settings.generation_provider, "generation_model": settings.generation_model,
        "embedding_provider": settings.embedding_provider, "embedding_model": settings.embedding_model,
        "grading_note": "Outcome, expected-document and phrase checks; inspect saved context to assess factual support.",
        "summary": {"total": len(rows), "completed": len(samples), "passed": sum(s["passed"] for s in samples)},
        "samples": samples,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps(report["summary"]))
    return 0 if len(samples) == len(rows) and all(s["passed"] for s in samples) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("eval/regulatory.jsonl"))
    parser.add_argument("--output", type=Path, default=Path(".benchmarks/answer-eval.json"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--pause-seconds", type=float, default=8.0, help="Minimum interval between questions for trial rerank quotas")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
