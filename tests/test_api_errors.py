from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from anchor.api import app as api
from anchor.config import Settings
from anchor.providers.gemini import ProviderError
from anchor.schemas import ChatConversation
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
