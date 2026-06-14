import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from anchor.config import get_settings
from anchor.db.pool import Database
from anchor.db.repository import AnchorRepository
from anchor.logging import configure_logging
from anchor.pipeline.service import DISCLAIMER, QueryService
from anchor.providers.gemini import GeminiEmbeddingProvider, GeminiGenerationProvider, ProviderError
from anchor.providers.rerank import CohereRerankProvider
from anchor.schemas import QueryRequest, QueryResponse
from anchor.services.metrics import Metrics
from anchor.services.rate_limit import RateLimiter, RateLimitExceeded
from anchor.services.tracing import Tracer

logger = logging.getLogger(__name__)


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
    async def metrics(request: Request) -> Response:
        content, content_type = request.app.state.metrics.render()
        return Response(content=content, media_type=content_type)

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
            result = await request.app.state.query_service.execute(question, request_id=request_id)
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

    return app


def main() -> None:
    import uvicorn

    uvicorn.run("anchor.api.app:create_app", factory=True, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
