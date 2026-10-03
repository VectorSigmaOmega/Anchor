import json

import httpx
import pytest
import respx

from anchor.config import Settings
from anchor.db.repository import AnchorRepository
from anchor.providers.factory import build_embedding_provider, build_generation_provider
from anchor.providers.gemini import MalformedModelOutputError, ProviderError
from anchor.providers.openai import OpenAIAPIClient, OpenAIEmbeddingProvider, OpenAIGenerationProvider
from anchor.schemas import ConversationTurn, RetrievedChunk


def settings(**overrides) -> Settings:
    return Settings(_env_file=None, database_url="postgresql://test", generation_provider="openai",
                    embedding_provider="openai", openai_api_key="test-key", cohere_api_key="test-key",
                    embedding_dimension=3, **overrides)


@respx.mock
async def test_embeddings_restore_input_order_and_use_configured_dimension():
    route = respx.post("https://api.openai.com/v1/embeddings").mock(return_value=httpx.Response(200, json={
        "data": [{"index": 1, "embedding": [2, 2, 2]}, {"index": 0, "embedding": [1, 1, 1]}],
        "usage": {"total_tokens": 6},
    }))
    provider = OpenAIEmbeddingProvider(settings())
    assert await provider.embed_documents(["first", "second"]) == [[1, 1, 1], [2, 2, 2]]
    request = json.loads(route.calls[0].request.content)
    assert request["model"] == "text-embedding-3-small"
    assert request["dimensions"] == 3
    assert provider.last_usage_metadata["total_tokens"] == 6


@pytest.mark.parametrize("rows", [
    [{"index": 0, "embedding": [1, 2]}],
    [{"index": 2, "embedding": [1, 2, 3]}],
    [],
])
@respx.mock
async def test_embeddings_reject_bad_dimensions_indices_and_counts(rows):
    respx.post("https://api.openai.com/v1/embeddings").mock(return_value=httpx.Response(200, json={"data": rows}))
    with pytest.raises(MalformedModelOutputError):
        await OpenAIEmbeddingProvider(settings()).embed_query("question")


@respx.mock
async def test_quota_exhaustion_fails_without_retries():
    route = respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=httpx.Response(429, json={"error": {"code": "insufficient_quota"}})
    )
    with pytest.raises(ProviderError) as exc:
        await OpenAIAPIClient(settings()).post("embeddings", {})
    assert exc.value.status_code == 429
    assert route.call_count == 1


@respx.mock
async def test_responses_api_schema_and_output_parsing():
    answer = {"status": "answered", "answer": "The annual credit limit is one lakh.",
              "refusal_reason": None, "citations": [{"chunk_id": "small-accounts", "quote": "Annual credits may not exceed one lakh."}]}
    route = respx.post("https://api.openai.com/v1/responses").mock(return_value=httpx.Response(200, json={
        "status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(answer)}]}],
        "usage": {"total_tokens": 50},
    }))
    chunk = RetrievedChunk(chunk_id="small-accounts", doc_id="kyc", doc_title="KYC", regulator="RBI",
                           section_path="Small accounts", text="Annual credits may not exceed one lakh.", source_url="https://example.com")
    result = await OpenAIGenerationProvider(settings()).generate(question="What is the credit limit?", context_chunks=[chunk])
    assert result.answer == answer["answer"]
    request = json.loads(route.calls[0].request.content)
    assert request["store"] is False
    assert request["model"] == "gpt-4.1-mini"
    assert request["text"]["format"]["strict"] is True
    assert request["text"]["format"]["schema"]["properties"]["citations"]["items"]["properties"]["chunk_id"]["enum"] == ["small-accounts"]


@respx.mock
async def test_followup_rewrite_preserves_the_new_subject():
    standalone = "How often must banks update KYC for low-risk customers?"
    route = respx.post("https://api.openai.com/v1/responses").mock(return_value=httpx.Response(200, json={
        "status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": json.dumps({"question": standalone})},
        ]}],
    }))
    history = [ConversationTurn(role="user", content="How often must banks update KYC for high-risk customers?")]
    result = await OpenAIGenerationProvider(settings()).rewrite_question("What about low-risk customers?", history)
    assert result == standalone
    request = json.loads(route.calls[0].request.content)
    assert "high-risk customers" in request["input"]
    assert "Current question: What about low-risk customers?" in request["input"]
    assert request["store"] is False


@respx.mock
async def test_incomplete_generation_is_not_accepted():
    respx.post("https://api.openai.com/v1/responses").mock(return_value=httpx.Response(200, json={"status": "incomplete", "output": []}))
    with pytest.raises(MalformedModelOutputError):
        await OpenAIGenerationProvider(settings()).generate(question="What is KYC?", context_chunks=[])


def test_factories_and_provider_credentials():
    s = settings()
    assert isinstance(build_embedding_provider(s), OpenAIEmbeddingProvider)
    assert isinstance(build_generation_provider(s), OpenAIGenerationProvider)
    s.validate_query_runtime()
    s.openai_api_key = ""
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        s.validate_query_runtime()


def test_embedding_index_rejects_different_model_even_with_same_dimension():
    repo = AnchorRepository(None, settings())  # type: ignore[arg-type]
    with pytest.raises(ProviderError, match="different embedding model"):
        repo._check_embedding_profile({"provider": "gemini", "model": "gemini-embedding-2", "dimension": 3})
    repo._check_embedding_profile({"provider": "openai", "model": "text-embedding-3-small", "dimension": 3})
