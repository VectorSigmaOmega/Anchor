from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Sequence
from uuid import uuid4

from anchor.config import Settings
from anchor.db.repository import AnchorRepository
from anchor.logging import log_extra
from anchor.pipeline.citations import validate_and_hydrate_citations
from anchor.pipeline.refusal import has_direct_support, is_ambiguous_question, is_out_of_scope_question, refusal_reason_for_context
from anchor.pipeline.rrf import fuse_ranked_chunk_lists
from anchor.providers.gemini import EmbeddingProvider, GenerationProvider, MalformedModelOutputError, ProviderError
from anchor.providers.rerank import RerankProvider
from anchor.schemas import ConversationTurn, ModelQueryResponse, QueryExecutionResult, QueryResponse, RetrievedChunk
from anchor.services.metrics import Metrics
from anchor.services.tracing import NullTrace, Tracer

logger = logging.getLogger(__name__)
DISCLAIMER = "Demo only. Not legal or financial advice."
MAX_CONTEXT_TURNS = 4
MAX_CONTEXT_TURN_CHARS = 4000
DIRECT_ANSWER_RE = re.compile(
    r"\b(just|only|simply)?\s*(give|tell|provide|answer)\b.*\b(answer|it)\b",
    re.IGNORECASE,
)
FOLLOWUP_RE = re.compile(r"\b(this|that|these|those|it|they|their|same)\b|^(what|how) about\b", re.IGNORECASE)


def is_multipart_question(question: str) -> bool:
    numbered_parts = re.findall(r"\(\d+\)|(?:^|\n)\s*\d+[.)]", question)
    return (
        len(numbered_parts) >= 2
        or question.count(";") >= 2
        or question.count("?") >= 2
        or (len(question.split()) >= 30 and bool(re.search(r"\b(compare|separately)\b", question, re.IGNORECASE)))
    )


def balanced_candidates(pools: Sequence[list[RetrievedChunk]], limit: int) -> list[RetrievedChunk]:
    """Reserve candidate space for every search rather than one dominant topic."""
    selected: list[RetrievedChunk] = []
    seen: set[str] = set()
    for rank in range(max((len(pool) for pool in pools), default=0)):
        for pool in pools:
            if rank < len(pool) and pool[rank].chunk_id not in seen:
                selected.append(pool[rank])
                seen.add(pool[rank].chunk_id)
                if len(selected) == limit:
                    return selected
    return selected


def needs_question_rewrite(question: str) -> bool:
    return bool(FOLLOWUP_RE.search(question)) or len(question.split()) <= 5


def is_direct_answer_followup(question: str) -> bool:
    normalized = " ".join(question.lower().split())
    return normalized in {"just give the answer", "give the answer", "answer it"} or bool(
        DIRECT_ANSWER_RE.search(question)
    )


def resolve_current_question(question: str, history: Sequence[ConversationTurn]) -> str:
    if not is_direct_answer_followup(question):
        return question
    previous_user_question = next(
        (turn.content for turn in reversed(history) if turn.role == "user"),
        None,
    )
    if not previous_user_question:
        return question
    return previous_user_question


def contextualize_question(question: str, history: Sequence[ConversationTurn]) -> str:
    if not history:
        return question

    recent_turns = history[-MAX_CONTEXT_TURNS:]
    rendered_turns = []
    for turn in recent_turns:
        compact_content = " ".join(turn.content.split())[:MAX_CONTEXT_TURN_CHARS]
        rendered_turns.append(f"{turn.role.title()}: {compact_content}")

    current_question = resolve_current_question(question, history)

    return "\n".join(
        [
            "Prior conversation (use only to resolve the current question):",
            *rendered_turns,
            "",
            f"Current question: {current_question}",
        ]
    )


class QueryService:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: AnchorRepository,
        embedding_provider: EmbeddingProvider,
        generation_provider: GenerationProvider,
        rerank_provider: RerankProvider,
        tracer: Tracer,
        metrics: Metrics,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.embedding_provider = embedding_provider
        self.generation_provider = generation_provider
        self.rerank_provider = rerank_provider
        self.tracer = tracer
        self.metrics = metrics

    async def execute(
        self,
        question: str,
        request_id: str | None = None,
        history: Sequence[ConversationTurn] | None = None,
    ) -> QueryExecutionResult:
        try:
            async with asyncio.timeout(self.settings.query_timeout_seconds):
                return await self._execute(question, request_id=request_id, history=history)
        except TimeoutError as exc:
            raise ProviderError("Query exceeded its time budget", provider="pipeline") from exc

    async def _execute(
        self,
        question: str,
        request_id: str | None = None,
        history: Sequence[ConversationTurn] | None = None,
    ) -> QueryExecutionResult:
        request_id = request_id or str(uuid4())
        started = time.perf_counter()
        trace = self.tracer.start_query_trace(request_id=request_id, question=question)
        conversation_history = history or []
        resolved_question = resolve_current_question(question, conversation_history)
        contextual_question = contextualize_question(question, conversation_history)
        response: QueryResponse | None = None
        reranked: list[RetrievedChunk] = []
        context_chunks: list[RetrievedChunk] = []
        was_rewritten = False
        try:
            request_validation = trace.span("request_validation", input={"question_length": len(question)})
            request_validation.end(output={"valid": True})
            rewrite = getattr(self.generation_provider, "rewrite_question", None)
            if conversation_history and resolved_question == question and needs_question_rewrite(question) and callable(rewrite):
                rewrite_span = trace.span("question_rewrite", input={"question": question})
                rewritten = await rewrite(question, conversation_history)
                rewrite_span.end(output={"question": rewritten, "resolved": bool(rewritten)})
                if rewritten:
                    was_rewritten = True
                    resolved_question = rewritten
                    contextual_question = contextualize_question(rewritten, conversation_history)
            early_refusal = None
            if is_out_of_scope_question(resolved_question):
                early_refusal = "not_in_corpus"
            elif is_ambiguous_question(resolved_question):
                early_refusal = "ambiguous_question"
            if early_refusal:
                response = self._refusal_response(request_id, early_refusal, started)
                self.metrics.record_response(response)
                return QueryExecutionResult(response=response)
            search_questions = [resolved_question] if was_rewritten else [contextual_question]
            if resolved_question not in search_questions:
                search_questions.append(resolved_question)
            if contextual_question != question and not was_rewritten:
                search_questions.append(question)
            planned_questions: list[str] = []
            planner = getattr(self.generation_provider, "plan_retrieval_questions", None)
            if is_multipart_question(resolved_question) and callable(planner):
                plan_span = trace.span("retrieval_plan", input={"question": resolved_question})
                planned_questions = await planner(resolved_question)
                plan_span.end(output={"questions": planned_questions})
                search_questions.extend(q for q in planned_questions if q not in search_questions)
            lexical_results, dense_results = await self._search(search_questions, trace)
            fused_chunks = self._fuse(lexical_results, dense_results, trace)
            topic_pools: list[list[RetrievedChunk]] = []
            if planned_questions:
                for search_question, lexical, dense in zip(search_questions, lexical_results, dense_results, strict=True):
                    if search_question in planned_questions:
                        topic_pools.append(fuse_ranked_chunk_lists(
                            [(self._content_passages(lexical), "lexical_score"),
                             (self._content_passages(dense), "dense_score")],
                            constant=self.settings.rrf_constant,
                        ))
                candidate_count = self.settings.multipart_rerank_candidate_count
                fused_pool = balanced_candidates([*topic_pools, fused_chunks], candidate_count)
            else:
                fused_pool = fused_chunks[: self.settings.rerank_candidate_count]
            reranked = await self._rerank(
                resolved_question if was_rewritten else contextual_question, fused_pool, trace,
                top_n=len(fused_pool) if topic_pools else None,
            )
            reranked, hinted_titles = self._apply_document_hints(contextual_question, reranked, trace)
            context_span = trace.span("context_selection", input={"reranked_count": len(reranked)})
            context_chunks = self._select_context(
                contextual_question,
                question,
                reranked,
                hinted_titles,
            )
            if topic_pools:
                context_chunks = self._select_multipart_context(reranked, topic_pools)
            context_span.end(
                output={
                    "context_count": len(context_chunks),
                    "chunks": [
                        {
                            "chunk_id": chunk.chunk_id,
                            "doc_id": chunk.doc_id,
                            "section_path": chunk.section_path,
                            "relevance_score": chunk.relevance_score,
                        }
                        for chunk in context_chunks
                    ],
                }
            )
            refusal_reason = refusal_reason_for_context(
                contextual_question,
                reranked,
                context_chunks,
                self.settings,
                ambiguity_question=resolved_question,
            )
            if refusal_reason:
                response = self._refusal_response(request_id, refusal_reason, started)
            else:
                model_response = await self._generate_with_retry(contextual_question, context_chunks, trace)
                validation_span = trace.span(
                    "response_validation",
                    input={"model_status": model_response.status},
                )
                hydrated = validate_and_hydrate_citations(
                    model_response, context_chunks, max_rendered=self.settings.max_citations
                )
                if not hydrated[0]:
                    try:
                        retry_response = await self._generate(
                            contextual_question,
                            context_chunks,
                            trace,
                            retry_note=self._validation_retry_note(model_response),
                        )
                    except MalformedModelOutputError:
                        hydrated = (False, [])
                    else:
                        hydrated = validate_and_hydrate_citations(
                            retry_response, context_chunks, max_rendered=self.settings.max_citations
                        )
                        model_response = retry_response
                validation_span.end(
                    output={
                        "valid": hydrated[0],
                        "citations": len(hydrated[1]),
                    }
                )
                if not hydrated[0]:
                    self.metrics.citation_validation_failures.inc()
                    response = self._refusal_response(request_id, "insufficient_support", started)
                else:
                    response = QueryResponse(
                        request_id=request_id,
                        status=model_response.status,
                        answer=model_response.answer if model_response.status == "answered" else "",
                        refusal_reason=model_response.refusal_reason,
                        citations=hydrated[1],
                        disclaimer=DISCLAIMER,
                        latency_ms=self._latency_ms(started),
                    )
            assert response is not None
            self.metrics.record_response(response)
            log_extra(
                logger,
                logging.INFO,
                "query_completed",
                request_id=request_id,
                status=response.status,
                refusal_reason=response.refusal_reason,
                latency_ms=response.latency_ms,
                citations=len(response.citations),
            )
            return QueryExecutionResult(
                response=response,
                retrieved_chunks=reranked,
                context_chunks=context_chunks,
            )
        except Exception as exc:
            trace.end(output={"error": str(exc)})
            raise
        finally:
            self.metrics.query_latency.observe(time.perf_counter() - started)
            if response is not None:
                trace.end(
                    output={
                        "status": response.status,
                        "refusal_reason": response.refusal_reason,
                        "latency_ms": response.latency_ms,
                    }
                )
            else:
                self.metrics.requests_total.labels(status="error").inc()
                trace.end(output={"status": "error", "latency_ms": self._latency_ms(started)})

    async def _search(
        self,
        questions: Sequence[str],
        trace: NullTrace,
    ) -> tuple[list[list[RetrievedChunk]], list[list[RetrievedChunk]]]:
        results = await asyncio.gather(
            *[self._lexical_search(question, trace) for question in questions],
            *[self._dense_search(question, trace) for question in questions],
        )
        split_at = len(questions)
        return (
            list(results[:split_at]),
            list(results[split_at:]),
        )

    async def _lexical_search(self, question: str, trace: NullTrace) -> list[RetrievedChunk]:
        span = trace.span("lexical_search", input={"question": question})
        chunks = await self.repository.lexical_search(question, self.settings.lexical_candidate_count)
        span.end(output={"count": len(chunks)})
        return chunks

    def _fuse(
        self,
        lexical_results: list[list[RetrievedChunk]],
        dense_results: list[list[RetrievedChunk]],
        trace: NullTrace,
    ) -> list[RetrievedChunk]:
        span = trace.span(
            "fusion",
            input={
                "lexical_count": sum(len(chunks) for chunks in lexical_results),
                "dense_count": sum(len(chunks) for chunks in dense_results),
                "lexical_queries": len(lexical_results),
                "dense_queries": len(dense_results),
            },
        )
        fused = fuse_ranked_chunk_lists(
            [
                *[(self._content_passages(chunks), "lexical_score") for chunks in lexical_results],
                *[(self._content_passages(chunks), "dense_score") for chunks in dense_results],
            ],
            constant=self.settings.rrf_constant,
        )
        span.end(
            output={
                "count": len(fused),
                "top_chunks": [
                    {
                        "chunk_id": chunk.chunk_id,
                        "doc_id": chunk.doc_id,
                        "fused_score": chunk.fused_score,
                    }
                    for chunk in fused[: self.settings.final_context_top_k]
                ],
            }
        )
        return fused

    @staticmethod
    def _content_passages(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return [chunk for chunk in chunks if not re.search(
            r"(?:^| > )(?:contents|table of contents|list of abbreviations)(?: > |$)",
            chunk.section_path, re.IGNORECASE,
        )]

    async def _dense_search(self, question: str, trace: NullTrace) -> list[RetrievedChunk]:
        span = trace.span("dense_search", input={"question": question})
        try:
            embedding = await self.embedding_provider.embed_query(question)
            chunks = await self.repository.dense_search(embedding, self.settings.dense_candidate_count)
            span.end(
                output={
                    "count": len(chunks),
                    "usage_metadata": getattr(self.embedding_provider, "last_usage_metadata", {}),
                }
            )
            return chunks
        except Exception as exc:
            span.end(output={"error": str(exc)})
            raise

    async def _rerank(
        self, question: str, fused_pool: list[RetrievedChunk], trace: NullTrace,
        *, top_n: int | None = None,
    ) -> list[RetrievedChunk]:
        span = trace.span("rerank", input={"candidate_count": len(fused_pool)})
        try:
            reranked = await self.rerank_provider.rerank(
                question,
                fused_pool,
                top_n=top_n if top_n is not None else self.settings.rerank_top_k,
            )
            span.end(
                output={
                    "count": len(reranked),
                    "top_chunks": [
                        {
                            "chunk_id": chunk.chunk_id,
                            "doc_id": chunk.doc_id,
                            "relevance_score": chunk.relevance_score,
                        }
                        for chunk in reranked[: self.settings.final_context_top_k]
                    ],
                }
            )
            return reranked
        except Exception as exc:
            span.end(output={"error": str(exc)})
            raise

    def _apply_document_hints(
        self,
        question: str,
        reranked: list[RetrievedChunk],
        trace: NullTrace,
    ) -> tuple[list[RetrievedChunk], set[str]]:
        span = trace.span("document_hint_boost", input={"candidate_count": len(reranked)})
        normalized_question = " ".join(question.lower().split())
        hinted_titles = {
            chunk.doc_title.lower()
            for chunk in reranked
            if chunk.doc_title and chunk.doc_title.lower() in normalized_question
        }
        if not hinted_titles:
            span.end(output={"hinted_documents": []})
            return reranked, hinted_titles

        boosted: list[RetrievedChunk] = []
        for chunk in reranked:
            copy = chunk.model_copy()
            if copy.doc_title.lower() in hinted_titles:
                copy.relevance_score = min(1.0, (copy.relevance_score or 0.0) + 0.05)
            boosted.append(copy)
        boosted.sort(key=lambda chunk: (chunk.relevance_score or 0.0), reverse=True)
        span.end(output={"hinted_documents": sorted(hinted_titles)})
        return boosted, hinted_titles

    def _select_context(
        self,
        contextual_question: str,
        raw_question: str,
        reranked: list[RetrievedChunk],
        hinted_titles: set[str],
    ) -> list[RetrievedChunk]:
        default_context = reranked[: self.settings.final_context_top_k]
        if not hinted_titles:
            return default_context

        hinted_context = [
            chunk
            for chunk in reranked
            if chunk.doc_title.lower() in hinted_titles
        ][: self.settings.final_context_top_k]
        if hinted_context and (
            has_direct_support(raw_question, hinted_context)
            or has_direct_support(contextual_question, hinted_context)
        ):
            return hinted_context
        return default_context

    def _select_multipart_context(
        self, reranked: list[RetrievedChunk], topic_pools: list[list[RetrievedChunk]],
    ) -> list[RetrievedChunk]:
        supported = {
            c.chunk_id: c for c in reranked
            if (c.relevance_score or 0.0) >= self.settings.rerank_min_support_score
        }
        pools = [
            sorted(
                [supported[c.chunk_id] for c in pool if c.chunk_id in supported],
                key=lambda c: c.relevance_score or 0.0, reverse=True,
            )[:2]
            for pool in topic_pools
        ]
        reserved = balanced_candidates(pools, self.settings.multipart_context_top_k)
        seen = {c.chunk_id for c in reserved}
        reserved.extend(c for c in reranked if c.chunk_id in supported and c.chunk_id not in seen)
        return reserved[:self.settings.multipart_context_top_k]

    async def _generate(
        self,
        question: str,
        context_chunks: list[RetrievedChunk],
        trace: NullTrace,
        retry_note: str | None = None,
    ) -> ModelQueryResponse:
        span = trace.generation(
            "generation",
            model=getattr(self.generation_provider, "model_for_context", lambda _: self.settings.generation_model)(context_chunks),
            input={"context_chunks": len(context_chunks)},
        )
        response = await self.generation_provider.generate(
            question=question,
            context_chunks=context_chunks,
            retry_note=retry_note,
        )
        usage_metadata = getattr(self.generation_provider, "last_usage_metadata", {})
        span.end(
            output={
                "status": response.status,
                "citation_count": len(response.citations),
                "refusal_reason": response.refusal_reason,
                "usage_metadata": usage_metadata,
            }
        )
        return response

    async def _generate_with_retry(
        self,
        question: str,
        context_chunks: list[RetrievedChunk],
        trace: NullTrace,
    ) -> ModelQueryResponse:
        try:
            return await self._generate(question, context_chunks, trace)
        except MalformedModelOutputError:
            try:
                return await self._generate(
                    question,
                    context_chunks,
                    trace,
                    retry_note=(
                        "Your previous output was invalid or malformed. Return valid JSON only, "
                        "and refuse if the context cannot support the answer."
                    ),
                )
            except MalformedModelOutputError:
                return ModelQueryResponse(
                    status="refused",
                    answer="",
                    refusal_reason="insufficient_support",
                    citations=[],
                )

    def _refusal_response(self, request_id: str, refusal_reason: str, started: float) -> QueryResponse:
        return QueryResponse(
            request_id=request_id,
            status="refused",
            answer="",
            refusal_reason=refusal_reason,  # type: ignore[arg-type]
            citations=[],
            disclaimer=DISCLAIMER,
            latency_ms=self._latency_ms(started),
        )

    def _validation_retry_note(self, model_response: ModelQueryResponse) -> str:
        if model_response.status == "refused" and (model_response.answer or model_response.citations):
            return (
                "Your previous output was invalid because status='refused' included an answer and/or citations. "
                "If the supplied context supports any useful limited answer, return status='answered', a plain-text "
                "answer that explicitly states the limit of what the context supports, and citations using allowed "
                "chunk IDs only. If the context supports no useful answer, return status='refused' with an empty "
                "answer, a refusal_reason, and citations=[]."
            )
        return (
            "Your previous output was invalid. Use only supplied sources and return plain text "
            "without markdown tables or HTML, and keep refused responses empty with no citations. "
            "If labelled E excerpts are supplied, use their [E...] references "
            "in answer text; the server supplies the exact quotes and numbered references. "
            "Otherwise each citation must include a verbatim contiguous quote copied exactly from its chunk. "
            f"Use at most {self.settings.max_citations} distinct citations. For the legacy quote format, inline [n] markers must refer to "
            "the one-based returned citation order, never chunk ID suffixes. "
            "Copy table rows exactly including vertical bars, and never reconstruct quotations. "
            "For an answered response, omit refusal_reason."
        )

    @staticmethod
    def _latency_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
