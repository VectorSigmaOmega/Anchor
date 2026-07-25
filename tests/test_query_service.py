from anchor.config import Settings
from anchor.pipeline.service import (
    QueryService,
    contextualize_question,
    is_direct_answer_followup,
    resolve_current_question,
)
from anchor.schemas import ConversationTurn, ModelCitation, ModelQueryResponse, QueryExecutionResult, RetrievedChunk
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


def research_chunk(chunk_id: str, text: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        doc_id="sebi_research_analysts_2026",
        doc_title="Master Circular for Research Analysts",
        regulator="SEBI",
        section_path="Master Circular for Research Analysts > 7. Investor Charter for Research Analysts",
        page=32,
        text=text,
        source_url="https://example.com/sebi",
        lexical_score=0.92,
    )


class RawFollowUpRepository:
    def __init__(self) -> None:
        self.lexical_questions: list[str] = []

    async def lexical_search(self, question: str, limit: int) -> list[RetrievedChunk]:
        self.lexical_questions.append(question)
        if question == "what is the Investor Charter?":
            return [
                research_chunk(
                    "sebi-ra-092",
                    "All research analysts are required to bring the Investor Charter to the notice of their clients.",
                ),
                research_chunk(
                    "sebi-ra-093",
                    "Research Analysts must disclose the Investor Charter on websites and mobile applications.",
                ),
            ]
        return []

    async def dense_search(self, embedding: list[float], limit: int) -> list[RetrievedChunk]:
        return []


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


class RefusedThenAnsweredGenerationProvider:
    def __init__(self) -> None:
        self.retry_notes: list[str | None] = []

    async def generate(
        self,
        *,
        question: str,
        context_chunks: list[RetrievedChunk],
        retry_note: str | None = None,
    ) -> ModelQueryResponse:
        self.retry_notes.append(retry_note)
        if retry_note is None:
            return ModelQueryResponse(
                status="refused",
                answer="The provided context says research analysts must bring the Investor Charter to clients' notice.",
                refusal_reason="insufficient_support",
                citations=[ModelCitation(chunk_id=context_chunks[0].chunk_id)],
            )
        return ModelQueryResponse(
            status="answered",
            answer="The provided context says research analysts must bring the Investor Charter to clients' notice.",
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


def test_contextualize_question_adds_recent_history() -> None:
    question = contextualize_question(
        "What about those steps for NBFCs?",
        [
            ConversationTurn(
                role="user",
                content="What customer due diligence steps does the RBI KYC direction require?",
            ),
            ConversationTurn(
                role="assistant",
                content="The direction requires identification and verification before account opening.",
            ),
        ],
    )

    assert "User: What customer due diligence steps" in question
    assert "Assistant: The direction requires identification" in question
    assert question.endswith("Current question: What about those steps for NBFCs?")


def test_contextualize_question_resolves_direct_answer_followup() -> None:
    question = contextualize_question(
        "just give the answer",
        [
            ConversationTurn(
                role="user",
                content="Master Circular is issued in exercise of powers conferred under which section?",
            ),
            ConversationTurn(
                role="assistant",
                content="It is issued under Section 11(1).",
            ),
        ],
    )

    assert is_direct_answer_followup("just give the answer")
    assert resolve_current_question(
        "just give the answer",
        [
            ConversationTurn(
                role="user",
                content="Master Circular is issued in exercise of powers conferred under which section?",
            )
        ],
    ) == "Master Circular is issued in exercise of powers conferred under which section?"
    assert question.endswith(
        "Current question: Master Circular is issued in exercise of powers conferred under which section?"
    )


def test_query_service_answer_path() -> None:
    settings = Settings.model_validate(
        {
            "database_url": "postgresql://anchor:anchor@localhost:5432/anchor",
            "gemini_api_key": "key",
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


def test_query_service_searches_raw_question_for_followups() -> None:
    settings = Settings.model_validate(
        {
            "database_url": "postgresql://anchor:anchor@localhost:5432/anchor",
            "gemini_api_key": "key",
            "cohere_api_key": "key",
        }
    )
    repository = RawFollowUpRepository()
    service = QueryService(
        settings=settings,
        repository=repository,  # type: ignore[arg-type]
        embedding_provider=FakeEmbeddingProvider(),
        generation_provider=FakeGenerationProvider(),
        rerank_provider=FakeRerankProvider(),
        tracer=Tracer(settings),
        metrics=Metrics("anchor_test_raw_followup"),
    )

    result = __import__("asyncio").run(
        service.execute(
            "what is the Investor Charter?",
            history=[
                ConversationTurn(
                    role="user",
                    content="What must a research analyst disclose in a research report?",
                ),
                ConversationTurn(
                    role="assistant",
                    content="Research analysts must maintain the rationale for their recommendations.",
                ),
            ],
        )
    )

    assert result.response.status == "answered"
    assert "what is the Investor Charter?" in repository.lexical_questions
    assert any(question.startswith("Prior conversation") for question in repository.lexical_questions)


def test_query_service_retries_refused_response_with_answer_and_citations() -> None:
    settings = Settings.model_validate(
        {
            "database_url": "postgresql://anchor:anchor@localhost:5432/anchor",
            "gemini_api_key": "key",
            "cohere_api_key": "key",
        }
    )
    generation_provider = RefusedThenAnsweredGenerationProvider()
    service = QueryService(
        settings=settings,
        repository=RawFollowUpRepository(),  # type: ignore[arg-type]
        embedding_provider=FakeEmbeddingProvider(),
        generation_provider=generation_provider,
        rerank_provider=FakeRerankProvider(),
        tracer=Tracer(settings),
        metrics=Metrics("anchor_test_refused_retry"),
    )

    result = __import__("asyncio").run(service.execute("what is the Investor Charter?"))

    assert result.response.status == "answered"
    assert len(generation_provider.retry_notes) == 2
    assert "status='refused' included an answer" in (generation_provider.retry_notes[1] or "")


def test_query_service_boosts_documents_named_in_conversation_context() -> None:
    settings = Settings.model_validate(
        {
            "database_url": "postgresql://anchor:anchor@localhost:5432/anchor",
            "gemini_api_key": "key",
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
        metrics=Metrics("anchor_test_document_hint"),
    )
    research = research_chunk(
        "sebi-ra-005",
        "This Master Circular is issued in exercise of powers conferred under Section 11(1).",
    )
    research.relevance_score = 0.93
    other = RetrievedChunk(
        chunk_id="sebi-other-001",
        doc_id="sebi_other",
        doc_title="Master Circular for Other Intermediaries",
        regulator="SEBI",
        section_path="Master Circular for Other Intermediaries",
        text="This Master Circular is issued in exercise of powers conferred under Section 11(1).",
        source_url="https://example.com/other",
        relevance_score=0.96,
    )

    boosted, hinted_titles = service._apply_document_hints(
        "Prior answer: The Master Circular for Research Analysts is available on the SEBI website.",
        [other, research],
        Tracer(settings).start_query_trace(request_id="test", question="test"),
    )
    context = service._select_context(
        "Prior answer: The Master Circular for Research Analysts is available on the SEBI website.",
        "Master Circular is issued in exercise of powers conferred under which section?",
        boosted,
        hinted_titles,
    )

    assert boosted[0].chunk_id == "sebi-ra-005"
    assert (boosted[0].relevance_score or 0.0) > (other.relevance_score or 0.0)
    assert [chunk.chunk_id for chunk in context] == ["sebi-ra-005"]
