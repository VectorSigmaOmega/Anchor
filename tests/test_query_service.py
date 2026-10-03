import asyncio

import pytest

from anchor.config import Settings
from anchor.pipeline.service import (
    QueryService,
    contextualize_question,
    is_direct_answer_followup,
    resolve_current_question,
)
from anchor.providers.gemini import ProviderError
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
            answer=context_chunks[0].text,
            refusal_reason=None,
            citations=[ModelCitation(chunk_id=context_chunks[0].chunk_id, quote=context_chunks[0].text)],
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
                citations=[ModelCitation(chunk_id=context_chunks[0].chunk_id, quote=context_chunks[0].text)],
            )
        return ModelQueryResponse(
            status="answered",
            answer="The provided context says research analysts must bring the Investor Charter to clients' notice.",
            refusal_reason=None,
            citations=[ModelCitation(chunk_id=context_chunks[0].chunk_id, quote=context_chunks[0].text)],
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


async def test_multipart_search_keeps_deposit_evidence_when_fee_results_dominate():
    from unittest.mock import AsyncMock

    fees = [research_chunk(f"fee-{n}", "Research analyst annual fee rules apply.") for n in range(25)]
    deposit = research_chunk("deposit", "Research analyst deposit is based on prior-year client counts.")
    weak = research_chunk("unrelated", "A poorly supported unrelated rule.")

    class Repository:
        async def lexical_search(self, question, limit):
            return [deposit, weak] if question == "Research analyst client deposits" else fees

        async def dense_search(self, embedding, limit):
            return []

    class Reranker(FakeRerankProvider):
        async def rerank(self, question, candidates, top_n):
            result = await super().rerank(question, candidates, top_n)
            for c in result:
                if c.chunk_id == "unrelated":
                    c.relevance_score = 0.01
            return result

    settings = Settings(_env_file=None, database_url="postgresql://unused")
    generation = FakeGenerationProvider()
    generation.plan_retrieval_questions = AsyncMock(return_value=[
        "Research analyst annual fees", "Research analyst client deposits",
    ])
    reranker = Reranker()
    reranker.rerank = AsyncMock(wraps=reranker.rerank)
    service = QueryService(settings=settings, repository=Repository(), embedding_provider=FakeEmbeddingProvider(),
                           generation_provider=generation, rerank_provider=reranker,
                           tracer=Tracer(settings), metrics=Metrics("multipart_test"))
    result = await service.execute("Compare SEBI research analyst requirements: annual fees; deposits; client counts.")
    assert result.response.status == "answered"
    assert "deposit" in {c.chunk_id for c in result.context_chunks}
    assert "unrelated" not in {c.chunk_id for c in result.context_chunks}
    reranker.rerank.assert_awaited_once()
    generation.plan_retrieval_questions.assert_awaited_once()


async def test_ordinary_question_does_not_add_a_paid_planning_call():
    from unittest.mock import AsyncMock

    settings = Settings(_env_file=None, database_url="postgresql://unused")
    generation = FakeGenerationProvider()
    generation.plan_retrieval_questions = AsyncMock()
    service = QueryService(settings=settings, repository=FakeRepository(), embedding_provider=FakeEmbeddingProvider(),
                           generation_provider=generation, rerank_provider=FakeRerankProvider(),
                           tracer=Tracer(settings), metrics=Metrics("ordinary_question_test"))
    await service.execute("What is the RBI KYC requirement?")
    generation.plan_retrieval_questions.assert_not_awaited()


def test_long_question_and_answer_history_remain_usable_for_followups():
    question = "Explain SEBI requirements. " + ("x" * 3930) + " and the final deposit deadline."
    history = [ConversationTurn(role="user", content=question),
               ConversationTurn(role="assistant", content="A detailed supported answer. " * 200)]
    rendered = contextualize_question("What about those deposits?", history)
    assert "and the final deposit deadline." in rendered
    assert rendered.endswith("Current question: What about those deposits?")


@pytest.mark.parametrize("stage", ["embedding", "rerank"])
async def test_provider_outage_is_not_reported_as_a_corpus_refusal(stage: str) -> None:
    from unittest.mock import AsyncMock

    settings = Settings(database_url="postgresql://unused")
    embedding = FakeEmbeddingProvider()
    rerank = FakeRerankProvider()
    generation = FakeGenerationProvider()
    generation.generate = AsyncMock()  # type: ignore[method-assign]
    error = ProviderError("credits depleted", provider=stage, status_code=402)
    if stage == "embedding":
        embedding.embed_query = AsyncMock(side_effect=error)  # type: ignore[method-assign]
    else:
        rerank.rerank = AsyncMock(side_effect=error)  # type: ignore[method-assign]
    service = QueryService(
        settings=settings,
        repository=FakeRepository(),  # type: ignore[arg-type]
        embedding_provider=embedding,
        generation_provider=generation,
        rerank_provider=rerank,
        tracer=Tracer(settings),
        metrics=Metrics("anchor_outage_test"),
    )

    with pytest.raises(ProviderError) as caught:
        await service.execute("What does the RBI KYC direction require?")

    assert caught.value is error
    generation.generate.assert_not_awaited()
    assert service.metrics.requests_total.labels(status="error")._value.get() == 1
    assert service.metrics.refusals_total.labels(reason="not_in_corpus")._value.get() == 0


async def test_query_timeout_cancels_provider_work() -> None:
    from unittest.mock import AsyncMock

    cancelled = asyncio.Event()

    async def stalled_embedding(text: str) -> list[float]:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return []

    settings = Settings(database_url="postgresql://unused", query_timeout_seconds=0.01)
    embedding = FakeEmbeddingProvider()
    embedding.embed_query = stalled_embedding  # type: ignore[method-assign]
    generation = FakeGenerationProvider()
    generation.generate = AsyncMock()  # type: ignore[method-assign]
    service = QueryService(
        settings=settings,
        repository=FakeRepository(),  # type: ignore[arg-type]
        embedding_provider=embedding,
        generation_provider=generation,
        rerank_provider=FakeRerankProvider(),
        tracer=Tracer(settings),
        metrics=Metrics("anchor_timeout_test"),
    )

    with pytest.raises(ProviderError, match="time budget"):
        await service.execute("What is KYC?")

    assert cancelled.is_set()
    generation.generate.assert_not_awaited()


@pytest.mark.parametrize("question,reason", [
    ("What is the GST rate on stock brokerage?", "not_in_corpus"),
    ("What does this rule require?", "ambiguous_question"),
])
async def test_unanswerable_questions_do_not_call_paid_providers(question: str, reason: str) -> None:
    from unittest.mock import AsyncMock

    settings = Settings(database_url="postgresql://unused")
    embedding = FakeEmbeddingProvider()
    embedding.embed_query = AsyncMock()  # type: ignore[method-assign]
    generation = FakeGenerationProvider()
    generation.generate = AsyncMock()  # type: ignore[method-assign]
    rerank = FakeRerankProvider()
    rerank.rerank = AsyncMock()  # type: ignore[method-assign]
    service = QueryService(
        settings=settings, repository=FakeRepository(),  # type: ignore[arg-type]
        embedding_provider=embedding, generation_provider=generation,
        rerank_provider=rerank, tracer=Tracer(settings), metrics=Metrics("anchor_scope_test"),
    )

    result = await service.execute(question)

    assert result.response.refusal_reason == reason
    embedding.embed_query.assert_not_awaited()
    generation.generate.assert_not_awaited()
    rerank.rerank.assert_not_awaited()


async def test_followup_retrieval_uses_the_resolved_question_without_old_risk_category() -> None:
    from unittest.mock import AsyncMock

    standalone = "How often must banks update KYC for low-risk customers?"
    repository = FakeRepository()
    repository.lexical_search = AsyncMock(wraps=repository.lexical_search)  # type: ignore[method-assign]
    embedding = FakeEmbeddingProvider()
    embedding.embed_query = AsyncMock(wraps=embedding.embed_query)  # type: ignore[method-assign]
    generation = FakeGenerationProvider()
    generation.rewrite_question = AsyncMock(return_value=standalone)  # type: ignore[attr-defined]
    settings = Settings(database_url="postgresql://unused")
    service = QueryService(
        settings=settings, repository=repository,  # type: ignore[arg-type]
        embedding_provider=embedding, generation_provider=generation,
        rerank_provider=FakeRerankProvider(), tracer=Tracer(settings), metrics=Metrics("anchor_rewrite_test"),
    )
    history = [
        ConversationTurn(role="user", content="How often must banks update KYC for high-risk customers?"),
        ConversationTurn(role="assistant", content="At least every two years."),
    ]

    result = await service.execute("What about those for low-risk customers?", history=history)

    assert result.response.status == "answered"
    generation.rewrite_question.assert_awaited_once_with("What about those for low-risk customers?", history)
    repository.lexical_search.assert_awaited_once_with(standalone, settings.lexical_candidate_count)
    embedding.embed_query.assert_awaited_once_with(standalone)


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


async def test_multipart_workflow_runs_claim_review_before_returning_answer(monkeypatch):
    from anchor.pipeline.workflow import AnswerReview, EvidenceReview

    calls = []

    class WorkflowProvider(FakeGenerationProvider):
        last_usage_metadata = {}

        def __init__(self, settings):
            pass

        async def plan_retrieval_questions(self, question):
            return ["RBI customer identification requirements", "RBI account opening duties"]

        async def assess_evidence(self, question, requirements, context):
            return EvidenceReview(missing_searches=[], limitations=[], findings=[])

        async def verify_answer(self, question, requirements, draft, context):
            calls.append("verify")
            return AnswerReview(issues=[])

    monkeypatch.setattr("anchor.providers.workflow.GeminiWorkflowProvider", WorkflowProvider)
    settings = Settings(_env_file=None, database_url="postgresql://test", multipart_workflow_enabled=True)
    service = QueryService(settings=settings, repository=FakeRepository(), embedding_provider=FakeEmbeddingProvider(),
                           generation_provider=FakeGenerationProvider(), rerank_provider=FakeRerankProvider(),
                           tracer=Tracer(settings), metrics=Metrics("anchor_workflow_test"))
    result = await service.execute("(1) What identification is required under RBI KYC? (2) What must banks do before opening accounts?")
    assert result.response.status == "answered"
    assert calls == ["verify"]


async def test_workflow_cannot_return_draft_after_persistent_claim_failure(monkeypatch):
    from anchor.pipeline.workflow import AnswerReview, EvidenceReview

    class WorkflowProvider(FakeGenerationProvider):
        last_usage_metadata = {}
        generations = 0

        def __init__(self, settings):
            pass

        async def plan_retrieval_questions(self, question):
            return ["RBI customer identification requirements", "RBI account opening duties"]

        async def assess_evidence(self, question, requirements, context):
            return EvidenceReview(missing_searches=[], limitations=[], findings=[])

        async def generate(self, **kwargs):
            type(self).generations += 1
            return await super().generate(**kwargs)

        async def verify_answer(self, question, requirements, draft, context):
            return AnswerReview(issues=["Cited passage does not support the claimed amount."])

    monkeypatch.setattr("anchor.providers.workflow.GeminiWorkflowProvider", WorkflowProvider)
    settings = Settings(_env_file=None, database_url="postgresql://test", multipart_workflow_enabled=True)
    service = QueryService(settings=settings, repository=FakeRepository(), embedding_provider=FakeEmbeddingProvider(),
                           generation_provider=FakeGenerationProvider(), rerank_provider=FakeRerankProvider(),
                           tracer=Tracer(settings), metrics=Metrics("anchor_workflow_test"))
    result = await service.execute("(1) What identification is required under RBI KYC? (2) What must banks do before opening accounts?")
    assert result.response.status == "refused"
    assert result.response.answer == ""
    assert result.response.citations == []
    assert WorkflowProvider.generations == 2
