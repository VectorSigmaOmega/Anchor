from __future__ import annotations

from typing import Protocol

import httpx

from anchor.config import Settings
from anchor.schemas import RetrievedChunk


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
        documents = [chunk.text for chunk in candidates]
        async with httpx.AsyncClient(timeout=20.0) as client:
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
            response.raise_for_status()
        payload = response.json()
        ranked: list[RetrievedChunk] = []
        for item in payload.get("results", []):
            chunk = candidates[item["index"]].model_copy()
            chunk.relevance_score = float(item["relevance_score"])
            ranked.append(chunk)
        return ranked
