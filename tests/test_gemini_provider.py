import asyncio
import json

import httpx
import pytest

from anchor.config import Settings
from anchor.providers import gemini
from anchor.providers.gemini import GeminiAPIClient, GeminiEmbeddingProvider, GeminiGenerationProvider, ProviderError
from anchor.schemas import RetrievedChunk


def settings() -> Settings:
    return Settings.model_validate(
        {
            "database_url": "postgresql://anchor:anchor@localhost:5432/anchor",
            "gemini_api_key": "key",
            "cohere_api_key": "key",
        }
    )


class FakeGeminiClient:
    def __init__(self, payload: dict):
        self.payload = payload
        self.calls: list[tuple[str, dict]] = []

    async def post(self, path: str, payload: dict) -> dict:
        self.calls.append((path, payload))
        return self.payload


class RaisingAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        pass

    async def post(self, *args, **kwargs):
        raise httpx.ConnectError("boom")


class InvalidJsonAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        pass

    async def post(self, *args, **kwargs):
        return httpx.Response(200, content=b"not-json")


class RateLimitThenSuccessAsyncClient:
    calls = 0

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        pass

    async def post(self, *args, **kwargs):
        self.__class__.calls += 1
        if self.__class__.calls == 1:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(200, json={"ok": True})


def test_embedding_provider_uses_retrieval_config() -> None:
    provider = GeminiEmbeddingProvider(settings())
    provider.client = FakeGeminiClient({"embedding": {"values": [0.0] * 768}})  # type: ignore[assignment]

    vector = asyncio.run(provider.embed_query("What is KYC?"))

    assert len(vector) == 768
    _, payload = provider.client.calls[0]  # type: ignore[attr-defined]
    assert payload["embedContentConfig"]["taskType"] == "RETRIEVAL_QUERY"
    assert payload["embedContentConfig"]["outputDimensionality"] == 768


def test_embedding_provider_batches_document_embeddings() -> None:
    settings_obj = settings()
    settings_obj.embedding_batch_size = 2
    provider = GeminiEmbeddingProvider(settings_obj)
    provider.client = FakeGeminiClient(
        {
            "embeddings": [
                {"values": [0.1] * 768},
                {"values": [0.2] * 768},
            ],
            "usageMetadata": {"promptTokenCount": 10},
        }
    )  # type: ignore[assignment]

    vectors = asyncio.run(provider.embed_documents(["one", "two"]))

    assert len(vectors) == 2
    path, payload = provider.client.calls[0]  # type: ignore[attr-defined]
    assert path == "gemini-embedding-2:batchEmbedContents"
    assert len(payload["requests"]) == 2
    assert payload["requests"][0]["model"] == "models/gemini-embedding-2"
    assert payload["requests"][0]["embedContentConfig"]["taskType"] == "RETRIEVAL_DOCUMENT"
    assert payload["requests"][0]["embedContentConfig"]["outputDimensionality"] == 768
    assert provider.last_usage_metadata["promptTokenCount"] == 10


def test_embedding_provider_paces_document_embedding_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    settings_obj = settings()
    settings_obj.embedding_batch_size = 1
    settings_obj.embedding_batch_pause_seconds = 12.5
    provider = GeminiEmbeddingProvider(settings_obj)
    provider.client = FakeGeminiClient({"embeddings": [{"values": [0.0] * 768}]})  # type: ignore[assignment]
    monkeypatch.setattr(gemini.asyncio, "sleep", fake_sleep)

    vectors = asyncio.run(provider.embed_documents(["one", "two", "three"]))

    assert len(vectors) == 3
    assert len(provider.client.calls) == 3  # type: ignore[attr-defined]
    assert sleeps == [12.5, 12.5]


def test_api_client_wraps_transport_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(gemini.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(httpx, "AsyncClient", RaisingAsyncClient)
    client = GeminiAPIClient(settings())

    with pytest.raises(ProviderError):
        asyncio.run(client.post("gemini-3-flash-preview:generateContent", {}))


def test_api_client_retries_rate_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_sleep(seconds: float) -> None:
        return None

    RateLimitThenSuccessAsyncClient.calls = 0
    monkeypatch.setattr(gemini.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(httpx, "AsyncClient", RateLimitThenSuccessAsyncClient)
    client = GeminiAPIClient(settings())

    assert asyncio.run(client.post("gemini-3-flash-preview:generateContent", {})) == {"ok": True}
    assert RateLimitThenSuccessAsyncClient.calls == 2


def test_api_client_wraps_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", InvalidJsonAsyncClient)
    client = GeminiAPIClient(settings())

    with pytest.raises(ProviderError):
        asyncio.run(client.post("gemini-3-flash-preview:generateContent", {}))


def test_generation_provider_parses_structured_output_and_records_usage() -> None:
    response_text = json.dumps(
        {
            "status": "answered",
            "answer": "Supported answer.",
            "citations": [{"chunk_id": "chunk-001"}],
        }
    )
    provider = GeminiGenerationProvider(settings())
    provider.client = FakeGeminiClient(
        {
            "candidates": [{"content": {"parts": [{"text": response_text}]}}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5, "totalTokenCount": 15},
        }
    )  # type: ignore[assignment]

    result = asyncio.run(
        provider.generate(
            question="What is KYC?",
            context_chunks=[
                RetrievedChunk(
                    chunk_id="chunk-001",
                    doc_id="rbi_kyc_2016",
                    doc_title="KYC",
                    regulator="RBI",
                    section_path="KYC",
                    text="KYC text",
                    source_url="https://example.com",
                )
            ],
        )
    )

    assert result.status == "answered"
    assert provider.last_usage_metadata["totalTokenCount"] == 15
    _, payload = provider.client.calls[0]  # type: ignore[attr-defined]
    assert "systemInstruction" in payload
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert "responseJsonSchema" in payload["generationConfig"]
