import logging
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import Response as PlainResponse

from anchor.config import get_settings
from anchor.db.pool import Database
from anchor.db.repository import AnchorRepository
from anchor.logging import configure_logging
from anchor.pipeline.service import DISCLAIMER, QueryService
from anchor.providers.gemini import GeminiEmbeddingProvider, GeminiGenerationProvider, ProviderError
from anchor.providers.rerank import CohereRerankProvider
from anchor.schemas import (
    ChatConversation,
    ChatHistoryResponse,
    ChatQueryRequest,
    ChatQueryResponse,
    ConversationTurn,
    QueryRequest,
    QueryResponse,
)
from anchor.services.chat_sessions import create_session_token, hash_session_token, is_valid_session_token, should_secure_session_cookie
from anchor.services.metrics import Metrics
from anchor.services.rate_limit import RateLimiter, RateLimitExceeded
from anchor.services.tracing import Tracer

logger = logging.getLogger(__name__)

REFUSAL_CONTENT = {
    "not_in_corpus": "The indexed RBI and SEBI documents do not cover this question.",
    "insufficient_support": "Related material was found, but it was not strong enough to support a reliable answer.",
    "ambiguous_question": "A little more detail is needed before this can be answered from the official corpus.",
    "rate_limited": "This demo has reached its query limit for your connection. Please try again later.",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.validate_query_runtime()
    configure_logging(settings.log_level)
    database = Database(settings)
    await database.open()
    repository = AnchorRepository(database, settings)
    embedding_provider = GeminiEmbeddingProvider(settings)
    generation_provider = GeminiGenerationProvider(settings)
    rerank_provider = CohereRerankProvider(settings)
    tracer = Tracer(settings)
    metrics = Metrics(settings.metrics_namespace)
    app.state.repository = repository
    app.state.rate_limiter = RateLimiter(repository, settings)
    app.state.query_service = QueryService(
        settings=settings,
        repository=repository,
        embedding_provider=embedding_provider,
        generation_provider=generation_provider,
        rerank_provider=rerank_provider,
        tracer=tracer,
        metrics=metrics,
    )
    app.state.metrics = metrics
    app.state.tracer = tracer
    app.state.settings = settings
    app.state.db = database
    try:
        yield
    finally:
        await database.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Anchor API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.cors_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"service": "anchor-api", "status": "ok"}

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz(request: Request) -> dict[str, str]:
        ready = await request.app.state.repository.healthcheck()
        if not ready:
            raise HTTPException(status_code=503, detail="database unavailable")
        return {"status": "ready"}

    @app.get("/metrics")
    async def metrics(request: Request) -> PlainResponse:
        content, content_type = request.app.state.metrics.render()
        return PlainResponse(content=content, media_type=content_type)

    @app.post("/query", response_model=QueryResponse)
    async def query(request: Request, payload: QueryRequest) -> QueryResponse:
        settings = request.app.state.settings
        question = payload.question.strip()
        if not question or len(question) > settings.max_query_chars:
            raise HTTPException(
                status_code=422,
                detail=f"question must be between 1 and {settings.max_query_chars} characters",
            )
        ip_address = request.headers.get("x-real-ip", "").strip()
        if not ip_address:
            ip_address = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if not ip_address:
            ip_address = request.client.host if request.client else "unknown"
        request_id = request.headers.get("x-request-id") or str(uuid4())
        try:
            await request.app.state.rate_limiter.check(ip_address)
        except RateLimitExceeded:
            result = QueryResponse(
                request_id=request_id,
                status="refused",
                answer="",
                refusal_reason="rate_limited",
                citations=[],
                disclaimer=DISCLAIMER,
                latency_ms=0,
            )
            request_trace = request.app.state.tracer.start_query_trace(
                request_id=request_id,
                question=question,
            )
            request.app.state.metrics.record_response(result)
            request_trace.end(
                output={
                    "status": result.status,
                    "refusal_reason": result.refusal_reason,
                    "latency_ms": result.latency_ms,
                }
            )
            return JSONResponse(status_code=429, content=result.model_dump(mode="json"))
        try:
            result = await request.app.state.query_service.execute(
                question,
                request_id=request_id,
                history=payload.history,
            )
        except ProviderError as exc:
            logger.exception(
                "upstream_provider_error",
                extra={
                    "extra_fields": {
                        "request_id": request_id,
                        "provider": exc.provider,
                        "provider_status_code": exc.status_code,
                    }
                },
            )
            raise HTTPException(status_code=504, detail="upstream provider unavailable") from exc
        return result.response

    @app.get("/chat-api/conversations", response_model=ChatHistoryResponse)
    async def chat_history(request: Request, response: Response) -> ChatHistoryResponse:
        session_hash = await ensure_chat_session(request, response)
        conversations = await request.app.state.repository.list_chat_conversations(session_hash)
        return ChatHistoryResponse(conversations=conversations)

    @app.post("/chat-api/conversations", response_model=ChatConversation)
    async def create_chat_conversation(request: Request, response: Response) -> ChatConversation:
        session_hash = await ensure_chat_session(request, response)
        return await request.app.state.repository.create_chat_conversation(session_hash)

    @app.delete("/chat-api/conversations/{conversation_id}", status_code=204)
    async def delete_chat_conversation(
        conversation_id: UUID,
        request: Request,
        response: Response,
    ) -> None:
        session_hash = await ensure_chat_session(request, response)
        deleted = await request.app.state.repository.delete_chat_conversation(session_hash, conversation_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="conversation not found")

    @app.post("/chat-api/conversations/{conversation_id}/query", response_model=ChatQueryResponse)
    async def chat_query(
        conversation_id: UUID,
        payload: ChatQueryRequest,
        request: Request,
        response: Response,
    ) -> ChatQueryResponse:
        settings = request.app.state.settings
        question = payload.question.strip()
        if not question or len(question) > settings.max_query_chars:
            raise HTTPException(
                status_code=422,
                detail=f"question must be between 1 and {settings.max_query_chars} characters",
            )
        session_hash = await ensure_chat_session(request, response)
        started = await request.app.state.repository.append_chat_query(
            session_hash,
            conversation_id,
            question,
            user_message_id=payload.user_message_id,
            assistant_message_id=payload.assistant_message_id,
        )
        if started is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        return await execute_persisted_chat_query(
            request=request,
            session_hash=session_hash,
            conversation_id=conversation_id,
            assistant_message_id=started.assistant_message_id,
            question=question,
            history=started.history,
        )

    @app.post(
        "/chat-api/conversations/{conversation_id}/messages/{assistant_message_id}/retry",
        response_model=ChatQueryResponse,
    )
    async def retry_chat_message(
        conversation_id: UUID,
        assistant_message_id: UUID,
        request: Request,
        response: Response,
    ) -> ChatQueryResponse:
        session_hash = await ensure_chat_session(request, response)
        retry = await request.app.state.repository.prepare_chat_retry(
            session_hash,
            conversation_id,
            assistant_message_id,
        )
        if retry is None:
            raise HTTPException(status_code=404, detail="message not found")
        return await execute_persisted_chat_query(
            request=request,
            session_hash=session_hash,
            conversation_id=conversation_id,
            assistant_message_id=assistant_message_id,
            question=retry.question,
            history=retry.history,
        )

    return app


def client_ip(request: Request) -> str:
    ip_address = request.headers.get("x-real-ip", "").strip()
    if not ip_address:
        ip_address = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if not ip_address:
        ip_address = request.client.host if request.client else "unknown"
    return ip_address


async def ensure_chat_session(request: Request, response: Response) -> str:
    settings = request.app.state.settings
    token = request.cookies.get(settings.session_cookie_name)
    if not is_valid_session_token(token):
        token = create_session_token()
        response.set_cookie(
            key=settings.session_cookie_name,
            value=token,
            max_age=settings.session_cookie_max_age_days * 24 * 60 * 60,
            path="/",
            secure=should_secure_session_cookie(request, settings),
            httponly=True,
            samesite="lax",
        )
    session_hash = hash_session_token(token)
    await request.app.state.repository.touch_chat_session(session_hash)
    return session_hash


def assistant_content_from_response(response: QueryResponse) -> str:
    if response.status == "answered":
        return response.answer
    if response.refusal_reason:
        return REFUSAL_CONTENT[response.refusal_reason]
    return "No grounded answer was available."


async def execute_persisted_chat_query(
    *,
    request: Request,
    session_hash: str,
    conversation_id: UUID,
    assistant_message_id: UUID,
    question: str,
    history: list[ConversationTurn],
) -> ChatQueryResponse:
    request_id = request.headers.get("x-request-id") or str(uuid4())
    try:
        await request.app.state.rate_limiter.check(client_ip(request))
    except RateLimitExceeded:
        response = QueryResponse(
            request_id=request_id,
            status="refused",
            answer="",
            refusal_reason="rate_limited",
            citations=[],
            disclaimer=DISCLAIMER,
            latency_ms=0,
        )
        request_trace = request.app.state.tracer.start_query_trace(
            request_id=request_id,
            question=question,
        )
        request.app.state.metrics.record_response(response)
        request_trace.end(
            output={
                "status": response.status,
                "refusal_reason": response.refusal_reason,
                "latency_ms": response.latency_ms,
            }
        )
        await request.app.state.repository.complete_chat_assistant_message(
            conversation_id,
            assistant_message_id,
            content=assistant_content_from_response(response),
            response=response,
        )
        conversation = await request.app.state.repository.get_chat_conversation(session_hash, conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="conversation not found") from None
        return ChatQueryResponse(conversation=conversation)
    try:
        result = await request.app.state.query_service.execute(
            question,
            request_id=request_id,
            history=history,
        )
    except ProviderError as exc:
        await request.app.state.repository.fail_chat_assistant_message(
            conversation_id,
            assistant_message_id,
            error="The query service is temporarily unavailable. Please try again.",
        )
        logger.exception(
            "upstream_provider_error",
            extra={
                "extra_fields": {
                    "request_id": request_id,
                    "provider": exc.provider,
                    "provider_status_code": exc.status_code,
                }
            },
        )
        raise HTTPException(status_code=504, detail="upstream provider unavailable") from exc
    await request.app.state.repository.complete_chat_assistant_message(
        conversation_id,
        assistant_message_id,
        content=assistant_content_from_response(result.response),
        response=result.response,
    )
    conversation = await request.app.state.repository.get_chat_conversation(session_hash, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return ChatQueryResponse(conversation=conversation)


def main() -> None:
    import uvicorn

    uvicorn.run("anchor.api.app:create_app", factory=True, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
