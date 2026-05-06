from anchor.config import Settings
from anchor.pipeline.service import QueryService
from anchor.schemas import ModelCitation, ModelQueryResponse, QueryExecutionResult, RetrievedChunk
from anchor.services.metrics import Metrics
from anchor.services.tracing import Tracer


class FakeRepository:
    async def lexical_search(self, question: str, limit: int) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                chunk_id="chunk-001",
                doc_id="rbi_kyc_2016",
                doc_title="Master Direction - Know Your Customer (KYC) Direction, 2016",
                regulator="RBI",
                section_path="Master Direction - Know Your Customer (KYC) Direction, 2016 > Customer Due Diligence (CDD) Procedure",
                page=14,
                text="Banks should perform customer due diligence before opening accounts.",
                source_url="https://example.com/kyc",
                lexical_score=0.92,
            )
        ]

    async def dense_search(self, embedding: list[float], limit: int) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                chunk_id="chunk-001",
                doc_id="rbi_kyc_2016",
                doc_title="Master Direction - Know Your Customer (KYC) Direction, 2016",
                regulator="RBI",
                section_path="Master Direction - Know Your Customer (KYC) Direction, 2016 > Customer Due Diligence (CDD) Procedure",
                page=14,
                text="Banks should perform customer due diligence before opening accounts.",
                source_url="https://example.com/kyc",
                dense_score=0.95,
            ),
            RetrievedChunk(
                chunk_id="chunk-002",
                doc_id="rbi_kyc_2016",
                doc_title="Master Direction - Know Your Customer (KYC) Direction, 2016",
                regulator="RBI",
                section_path="Master Direction - Know Your Customer (KYC) Direction, 2016 > Customer Due Diligence (CDD) Procedure",
                page=15,
                text="Customer due diligence includes identification and verification steps.",
                source_url="https://example.com/kyc",
                dense_score=0.82,
            ),
        ]


class FakeEmbeddingProvider:
    async def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class FakeGenerationProvider:
    async def generate(
        self,
        *,
        question: str,
        context_chunks: list[RetrievedChunk],
        retry_note: str | None = None,
    ) -> ModelQueryResponse:
        return ModelQueryResponse(
            status="answered",
            answer="The RBI KYC direction requires customer due diligence before opening accounts.",
            refusal_reason=None,
            citations=[ModelCitation(chunk_id=context_chunks[0].chunk_id)],
        )


class FakeRerankProvider:
    async def rerank(
        self,
        question: str,
        candidates: list[RetrievedChunk],
        top_n: int,
    ) -> list[RetrievedChunk]:
        reranked: list[RetrievedChunk] = []
        for index, chunk in enumerate(candidates[:top_n], start=1):
            copy = chunk.model_copy()
            copy.relevance_score = 0.9 if index == 1 else 0.5
            reranked.append(copy)
        return reranked


def test_query_service_answer_path() -> None:
    settings = Settings.model_validate(
        {
            "database_url": "postgresql://anchor:anchor@localhost:5432/anchor",
            "vertex_project_id": "project",
            "vertex_location": "us-central1",
            "google_application_credentials": "/tmp/fake.json",
            "cohere_api_key": "key",
        }
    )
    service = QueryService(
        settings=settings,
        repository=FakeRepository(),  # type: ignore[arg-type]
        embedding_provider=FakeEmbeddingProvider(),
        generation_provider=FakeGenerationProvider(),
        rerank_provider=FakeRerankProvider(),
        tracer=Tracer(settings),
        metrics=Metrics("anchor_test"),
    )

    result: QueryExecutionResult = __import__("asyncio").run(
        service.execute("What does the RBI KYC direction require for customer due diligence?")
    )

    assert result.response.status == "answered"
    assert result.response.citations[0].doc_id == "rbi_kyc_2016"

