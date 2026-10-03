import httpx
import pytest
import respx

from anchor.config import Settings
from anchor.providers.gemini import ProviderError
from anchor.providers.rerank import CohereRerankProvider, format_rerank_document
from anchor.schemas import RetrievedChunk


def test_rerank_document_includes_section_heading() -> None:
    chunk = RetrievedChunk(
        chunk_id="sebi_research_analysts_2026::chunk_005",
        doc_id="sebi_research_analysts_2026",
        doc_title="Master Circular for Research Analysts",
        regulator="SEBI",
        section_path="Master Circular for Research Analysts > issued under Section 11(1)",
        text="of the Securities and Exchange Board of India Act, 1992.",
        source_url="https://example.com",
    )

    document = format_rerank_document(chunk)

    assert "Section 11(1)" in document
    assert "Securities and Exchange Board of India Act" in document


@pytest.mark.parametrize("failure", [httpx.Response(401), httpx.Response(429), httpx.Response(503), httpx.ConnectError("offline")])
@respx.mock
async def test_rerank_failures_are_provider_errors(failure) -> None:
    route = respx.post("https://api.cohere.com/v2/rerank")
    if isinstance(failure, Exception):
        route.mock(side_effect=failure)
    else:
        route.mock(return_value=failure)
    provider = CohereRerankProvider(Settings(database_url="postgresql://unused", cohere_api_key="test-key"))
    chunk = RetrievedChunk(
        chunk_id="kyc-1", doc_id="kyc", doc_title="KYC", regulator="RBI",
        section_path="CDD", text="Identify customers.", source_url="https://example.com",
    )

    with pytest.raises(ProviderError) as caught:
        await provider.rerank("What is KYC?", [chunk], top_n=1)

    assert caught.value.provider == "cohere"
    assert caught.value.status_code == (failure.status_code if isinstance(failure, httpx.Response) else None)


@pytest.mark.parametrize("results", [[], [{"index": -1, "relevance_score": 0.9}], [{"index": 0, "relevance_score": "nan"}]])
@respx.mock
async def test_invalid_reranker_scores_cannot_be_used_as_support(results) -> None:
    respx.post("https://api.cohere.com/v2/rerank").mock(return_value=httpx.Response(200, json={"results": results}))
    provider = CohereRerankProvider(Settings(database_url="postgresql://unused", cohere_api_key="test-key"))
    chunk = RetrievedChunk(
        chunk_id="kyc-1", doc_id="kyc", doc_title="KYC", regulator="RBI",
        section_path="CDD", text="Identify customers.", source_url="https://example.com",
    )

    with pytest.raises(ProviderError, match="invalid rerank response"):
        await provider.rerank("What is KYC?", [chunk], top_n=1)
