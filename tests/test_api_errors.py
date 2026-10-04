import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from anchor.api import app as api
from anchor.config import Settings
from anchor.providers.gemini import ProviderError
from anchor.schemas import ChatConversation, QueryExecutionResult, QueryResponse
from anchor.services.metrics import Metrics
from anchor.services.rate_limit import RateLimitExceeded
from anchor.services.tracing import Tracer


async def test_application_lifespan_initializes_the_query_service(monkeypatch):
    settings = Settings(database_url="postgresql://unused", gemini_api_key="test", cohere_api_key="test")
    database = SimpleNamespace(open=AsyncMock(), close=AsyncMock())
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    monkeypatch.setattr(api, "Database", lambda settings: database)
    monkeypatch.setattr(api, "AnchorRepository", lambda db, settings: SimpleNamespace(validate_embedding_profile=AsyncMock()))
    application = api.create_app()

    async with api.lifespan(application):
        database.open.assert_awaited_once()
        assert application.state.query_service.settings.generation_model == settings.generation_model

    database.close.assert_awaited_once()


@pytest.fixture
def app(monkeypatch):
    settings = Settings(database_url="postgresql://unused")
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    app = api.create_app()
    app.state.settings = settings
    app.state.metrics = Metrics("anchor_api_test")
    app.state.tracer = Tracer(settings)
    app.state.rate_limiter = SimpleNamespace(check=AsyncMock())
    app.state.query_service = SimpleNamespace(
        execute=AsyncMock(side_effect=ProviderError("credits depleted", provider="gemini", status_code=402))
    )
    now = datetime.now(UTC)
    app.state.repository = SimpleNamespace(
        touch_chat_session=AsyncMock(),
        append_chat_query=AsyncMock(return_value=SimpleNamespace(assistant_message_id=uuid4(), history=[])),
        prepare_chat_retry=AsyncMock(return_value=SimpleNamespace(assistant_message_id=uuid4(), question="What is KYC?", history=[])),
        fail_chat_assistant_message=AsyncMock(),
        complete_chat_assistant_message=AsyncMock(),
        get_chat_conversation=AsyncMock(return_value=ChatConversation(id=uuid4(), title="KYC", createdAt=now, updatedAt=now)),
    )
    return app


def stream_events(response):
    return [(line.split("\n", 1)[0].removeprefix("event: "),
             json.loads(line.split("data: ", 1)[1]))
            for line in response.text.split("\n\n") if line.startswith("event: ")]


@pytest.mark.parametrize("suffix", ["query/stream", "messages/{id}/retry/stream"])
async def test_chat_stream_reports_real_stages_and_saved_result(app, suffix):
    async def execute(question, *, request_id, history, on_progress):
        for stage in ("searching", "drafting", "checking"):
            on_progress(stage)
        return QueryExecutionResult(response=QueryResponse(
            request_id=request_id, status="answered", answer="Banks identify customers.",
            citations=[], disclaimer="Demo only.", latency_ms=500,
        ))

    app.state.query_service.execute.side_effect = execute
    path = f"/chat-api/conversations/{uuid4()}/{suffix.replace('{id}', str(uuid4()))}"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(path, json={"question": "What is KYC?"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "anchor_session=" in response.headers["set-cookie"]
    events = stream_events(response)
    assert [data["stage"] for kind, data in events if kind == "progress"] == [
        "queued", "searching", "drafting", "checking",
    ]
    assert [kind for kind, _ in events][-1] == "result"
    assert "createdAt" in events[-1][1]["conversation"]
    app.state.repository.complete_chat_assistant_message.assert_awaited_once()


@pytest.mark.parametrize("suffix", ["query/stream", "messages/{id}/retry/stream"])
async def test_chat_stream_reports_provider_error_and_persists_failure(app, suffix):
    path = f"/chat-api/conversations/{uuid4()}/{suffix.replace('{id}', str(uuid4()))}"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(path, json={"question": "What is KYC?"})

    assert response.status_code == 200
    events = stream_events(response)
    assert events[-1] == ("error", {"status": 503,
                                    "detail": "The query service is temporarily unavailable. Please try again later."})
    app.state.repository.fail_chat_assistant_message.assert_awaited_once()
    app.state.repository.complete_chat_assistant_message.assert_not_awaited()


async def test_disconnected_chat_stream_cancels_work_and_clears_pending_message(app):
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def execute(question, *, request_id, history, on_progress):
        on_progress("searching")
        started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    app.state.query_service.execute.side_effect = execute
    request = api.Request({"type": "http", "method": "POST", "path": "/chat-api/test/query/stream",
                           "headers": [], "client": ("192.0.2.1", 1234), "app": app})
    stream = api.stream_persisted_chat_query(
        request=request, response=api.Response(), session_hash="session", conversation_id=uuid4(),
        assistant_message_id=uuid4(), question="What is KYC?", history=[],
    )
    iterator = stream.body_iterator

    assert "queued" in await anext(iterator)
    await asyncio.wait_for(started.wait(), timeout=1)
    await iterator.aclose()

    assert cancelled.is_set()
    app.state.repository.fail_chat_assistant_message.assert_awaited_once()
    app.state.repository.complete_chat_assistant_message.assert_not_awaited()


async def test_chat_stream_keeps_ip_limit_and_retry_delay(app):
    app.state.rate_limiter.check.side_effect = RateLimitExceeded("rate limit exceeded", retry_after_seconds=42)
    transport = httpx.ASGITransport(app=app, client=("192.0.2.1", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/chat-api/conversations/{uuid4()}/query/stream",
            json={"question": "What is KYC?"}, headers={"X-Forwarded-For": "198.51.100.2"},
        )

    assert response.status_code == 200
    result = stream_events(response)[-1]
    assert result[0] == "result"
    assert result[1]["retryAfterSeconds"] == 42
    app.state.rate_limiter.check.assert_awaited_once_with("192.0.2.1")
    app.state.query_service.execute.assert_not_awaited()
    app.state.repository.complete_chat_assistant_message.assert_awaited_once()


@pytest.mark.parametrize("path", ["/query", "/chat-api/conversations/{id}/query", "/chat-api/conversations/{id}/messages/{id}/retry"])
async def test_provider_outages_return_service_errors_and_persist_chat_failure(app, path):
    path = path.replace("{id}", str(uuid4()))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(path, json={"question": "What is KYC?"})

    assert response.status_code == 503
    assert "temporarily unavailable" in response.json()["detail"]
    if path.startswith("/chat-api/"):
        app.state.repository.fail_chat_assistant_message.assert_awaited_once()
        app.state.repository.complete_chat_assistant_message.assert_not_awaited()


@pytest.mark.parametrize("path", ["/chat-api/conversations/{id}/query", "/chat-api/conversations/{id}/messages/{id}/retry"])
async def test_unexpected_query_errors_do_not_leave_chat_messages_pending(app, path):
    app.state.query_service.execute.side_effect = PermissionError("TLS bundle unavailable during deployment")
    path = path.replace("{id}", str(uuid4()))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(path, json={"question": "What is KYC?"})

    assert response.status_code == 500
    assert response.json()["detail"] == "The query could not be completed. Please try again."
    app.state.repository.fail_chat_assistant_message.assert_awaited_once()
    app.state.repository.complete_chat_assistant_message.assert_not_awaited()


@pytest.mark.parametrize("path", ["/query", "/chat-api/conversations/{id}/query", "/chat-api/conversations/{id}/messages/{id}/retry"])
async def test_rate_limits_use_trusted_client_and_return_retry_after(app, path):
    app.state.rate_limiter.check.side_effect = RateLimitExceeded("rate limit exceeded", retry_after_seconds=42)
    path = path.replace("{id}", str(uuid4()))
    transport = httpx.ASGITransport(app=app, client=("192.0.2.1", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            path,
            json={"question": "What is KYC?"},
            headers={"X-Real-IP": "198.51.100.1", "X-Forwarded-For": "198.51.100.2"},
        )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "42"
    app.state.rate_limiter.check.assert_awaited_once_with("192.0.2.1")
    app.state.query_service.execute.assert_not_awaited()
    if path.startswith("/chat-api/"):
        assert "createdAt" in response.json()["conversation"]
        app.state.repository.complete_chat_assistant_message.assert_awaited_once()


@pytest.mark.parametrize("path", ["/query", "/chat-api/conversations/{id}/query"])
@pytest.mark.parametrize("length,expected_status", [(4000, 503), (4001, 422)])
async def test_long_questions_reach_the_service_and_overlimit_questions_are_rejected(app, path, length, expected_status):
    app.state.settings.max_query_chars = 4000
    question = "q" * length
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(path.replace("{id}", str(uuid4())), json={"question": question})
    assert response.status_code == expected_status
    if length == 4000:
        # The mock provider fails, proving length validation forwarded all text.
        assert app.state.query_service.execute.call_args.args[0] == question
    else:
        app.state.query_service.execute.assert_not_awaited()
