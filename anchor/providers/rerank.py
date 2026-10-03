from __future__ import annotations

from math import isfinite
from typing import Protocol

import httpx

from anchor.config import Settings
from anchor.providers.gemini import ProviderError
from anchor.schemas import RetrievedChunk


def format_rerank_document(chunk: RetrievedChunk) -> str:
    return chunk.retrieval_text()


class RerankProvider(Protocol):
    async def rerank(self, question: str, candidates: list[RetrievedChunk], top_n: int) -> list[RetrievedChunk]:
        ...


class CohereRerankProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def rerank(
        self, question: str, candidates: list[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]:
        if not candidates:
            return []
        documents = [format_rerank_document(chunk) for chunk in candidates]
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                response = await client.post(
                    "https://api.cohere.com/v2/rerank",
                    headers={
                        "Authorization": f"Bearer {self.settings.cohere_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.settings.rerank_model,
                        "query": question,
                        "documents": documents,
                        "top_n": top_n,
                    },
                )
        except httpx.HTTPError as exc:
            raise ProviderError("Cohere request failed", provider="cohere") from exc
        if not response.is_success:
            raise ProviderError(
                f"Cohere request failed with status {response.status_code}",
                provider="cohere",
                status_code=response.status_code,
            )
        ranked: list[RetrievedChunk] = []
        try:
            results = response.json()["results"]
            if not isinstance(results, list) or not results:
                raise ValueError("missing rerank results")
            seen: set[int] = set()
            for item in results:
                index = item["index"]
                score = float(item["relevance_score"])
                if not isinstance(index, int) or not 0 <= index < len(candidates) or index in seen:
                    raise ValueError("invalid rerank index")
                if not isfinite(score) or not 0 <= score <= 1:
                    raise ValueError("invalid rerank score")
                seen.add(index)
                chunk = candidates[index].model_copy()
                chunk.relevance_score = score
                ranked.append(chunk)
        except (ValueError, TypeError, KeyError) as exc:
            raise ProviderError("Cohere returned an invalid rerank response", provider="cohere") from exc
        return ranked
