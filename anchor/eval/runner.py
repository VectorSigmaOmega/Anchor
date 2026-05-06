from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from uuid import uuid4

from anchor.config import get_settings
from anchor.db.pool import Database
from anchor.db.repository import AnchorRepository
from anchor.pipeline.service import QueryService
from anchor.providers.rerank import CohereRerankProvider
from anchor.providers.vertex import VertexEmbeddingProvider, VertexGenerationProvider
from anchor.schemas import Citation, EvalRow, QueryExecutionResult, QueryResponse
from anchor.services.metrics import Metrics
from anchor.services.tracing import Tracer

DATASET_PATH = Path("eval/golden.jsonl")
SMOKE_PATH = Path("eval/smoke.jsonl")
DOCS_EVAL_PATH = Path("docs/EVAL.md")


def load_dataset(path: Path) -> list[EvalRow]:
    rows: list[EvalRow] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        rows.append(EvalRow.model_validate_json(line))
    return rows


@dataclass
class EvalSample:
    row: EvalRow
    result: QueryExecutionResult


class FixtureEvalService:
    async def execute(self, row: EvalRow) -> QueryExecutionResult:
        if row.expected_outcome == "refusal":
            refusal_reason = "ambiguous_question" if "ambiguous" in row.notes else "not_in_corpus"
            response = QueryResponse(
                request_id=f"fixture-{row.id}",
                status="refused",
                answer="",
                refusal_reason=refusal_reason,
                citations=[],
                disclaimer="Demo only. Not legal or financial advice.",
                latency_ms=12,
            )
            return QueryExecutionResult(response=response, retrieved_chunks=[], context_chunks=[])

        citation_targets = row.reference_citations or [{"doc_id": row.doc_ids[0], "section_path": row.doc_ids[0]}]
        citations = [
            Citation(
                chunk_id=f"{target['doc_id']}::fixture",
                doc_id=target["doc_id"],
                doc_title=target["doc_id"].replace("_", " "),
                regulator="RBI" if target["doc_id"].startswith("rbi_") else "SEBI",
                section_title=target.get("section_path", target["doc_id"]),
                page=None,
                source_url="https://example.invalid/fixture",
                quote=row.reference_answer,
            )
            for target in citation_targets[:1]
        ]
        response = QueryResponse(
            request_id=f"fixture-{row.id}",
            status="answered",
            answer=row.reference_answer,
            refusal_reason=None,
            citations=citations,
            disclaimer="Demo only. Not legal or financial advice.",
            latency_ms=18,
        )
        return QueryExecutionResult(response=response, retrieved_chunks=[], context_chunks=[])


class LiveEvalService:
    def __init__(self, query_service: QueryService, database: Database) -> None:
        self.query_service = query_service
        self.database = database

    async def execute(self, row: EvalRow) -> QueryExecutionResult:
        return await self.query_service.execute(row.question, request_id=f"eval-{row.id}-{uuid4()}")

    async def close(self) -> None:
        await self.database.close()


async def build_live_eval_service() -> LiveEvalService:
    settings = get_settings()
    database = Database(settings)
    await database.open()
    repository = AnchorRepository(database, settings)
    query_service = QueryService(
        settings=settings,
        repository=repository,
        embedding_provider=VertexEmbeddingProvider(settings),
        generation_provider=VertexGenerationProvider(settings),
        rerank_provider=CohereRerankProvider(settings),
        tracer=Tracer(settings),
        metrics=Metrics(f"{settings.metrics_namespace}_eval"),
    )
    return LiveEvalService(query_service, database)


def score(samples: list[EvalSample]) -> dict[str, float]:
    answerable = [sample for sample in samples if sample.row.expected_outcome == "answer"]
    refusal_rows = [sample for sample in samples if sample.row.expected_outcome == "refusal"]

    citation_validity = mean(
        1.0
        if (
            sample.result.response.status == "answered"
            and len(sample.result.response.citations) >= 1
            and all(citation.doc_id in sample.row.doc_ids for citation in sample.result.response.citations)
        )
        else 0.0
        for sample in answerable
    ) if answerable else 1.0

    groundedness = mean(
        1.0
        if (
            sample.result.response.status == "answered"
            and any(citation.doc_id in sample.row.doc_ids for citation in sample.result.response.citations)
        )
        else 0.0
        for sample in answerable
    ) if answerable else 1.0

    retrieval_recall = mean(
        1.0
        if any(chunk.doc_id in sample.row.doc_ids for chunk in sample.result.retrieved_chunks[:5])
        else (
            1.0
            if any(citation.doc_id in sample.row.doc_ids for citation in sample.result.response.citations)
            else 0.0
        )
        for sample in answerable
    ) if answerable else 1.0

    refusal_precision = mean(
        1.0 if sample.result.response.status == "refused" else 0.0 for sample in refusal_rows
    ) if refusal_rows else 1.0

    malformed_count = sum(
        1
        for sample in samples
        if sample.result.response.status == "answered" and len(sample.result.response.citations) == 0
    )
    latency_ms = mean(sample.result.response.latency_ms for sample in samples) if samples else 0.0

    return {
        "retrieval_recall_at_5": round(retrieval_recall, 4),
        "citation_validity": round(citation_validity, 4),
        "faithfulness_groundedness": round(groundedness, 4),
        "refusal_precision": round(refusal_precision, 4),
        "average_latency_ms": round(latency_ms, 1),
        "malformed_output_count": float(malformed_count),
    }


def smoke_passes(metrics: dict[str, float]) -> bool:
    return (
        metrics["citation_validity"] >= 1.0
        and metrics["retrieval_recall_at_5"] >= 0.75
        and metrics["refusal_precision"] >= 0.80
        and metrics["malformed_output_count"] <= 1
    )


def render_markdown(mode: str, fixture_mode: bool, metrics: dict[str, float]) -> str:
    mode_label = "Smoke" if mode == "smoke" else "Full"
    execution_label = "fixture mode" if fixture_mode else "live query service"
    return "\n".join(
        [
            "# Anchor Evaluation",
            "",
            "## Latest Run",
            "",
            f"- Mode: {mode_label}",
            f"- Execution: {execution_label}",
            f"- Retrieval Recall@5: {metrics['retrieval_recall_at_5']:.2f}",
            f"- Citation validity: {metrics['citation_validity']:.2f}",
            f"- Faithfulness / groundedness: {metrics['faithfulness_groundedness']:.2f}",
            f"- Refusal precision: {metrics['refusal_precision']:.2f}",
            f"- Average latency (ms): {metrics['average_latency_ms']:.1f}",
            f"- Malformed outputs: {int(metrics['malformed_output_count'])}",
            "",
            "## Method",
            "",
            "- Full eval runs the direct query service against the indexed corpus when cloud credentials and PostgreSQL are available.",
            (
                "- CI smoke eval runs against the fixed `eval/smoke.jsonl` subset in fixture mode to "
                "validate the benchmark path without external providers."
            ),
            (
                "- Citation validity requires every answered response to include at least one citation "
                "whose `doc_id` matches the expected document set."
            ),
            "- Groundedness is tracked as a citation-overlap proxy against the reviewed reference set.",
        ]
    )


def write_eval_doc(mode: str, fixture_mode: bool, metrics: dict[str, float]) -> None:
    DOCS_EVAL_PATH.write_text(render_markdown(mode, fixture_mode, metrics) + "\n", encoding="utf-8")


def emit_json(metrics: dict[str, float]) -> str:
    return json.dumps(metrics, ensure_ascii=True)
