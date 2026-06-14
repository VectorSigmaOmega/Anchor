from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from typing import Any, Protocol

import httpx
from pydantic import ValidationError

from anchor.config import Settings
from anchor.schemas import ModelQueryResponse, RetrievedChunk


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, provider: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code


class MalformedModelOutputError(RuntimeError):
    pass


class EmbeddingProvider(Protocol):
    last_usage_metadata: dict[str, Any]

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class GenerationProvider(Protocol):
    last_usage_metadata: dict[str, Any]

    async def generate(
        self,
        *,
        question: str,
        context_chunks: Sequence[RetrievedChunk],
        retry_note: str | None = None,
    ) -> ModelQueryResponse: ...


def _model_resource(model: str) -> str:
    return model if model.startswith("models/") else f"models/{model}"


def _extract_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise MalformedModelOutputError("Gemini response did not contain candidates")
    parts = candidates[0].get("content", {}).get("parts") or []
    texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
    text = "\n".join(item for item in texts if item).strip()
    if not text:
        raise MalformedModelOutputError("Gemini response did not contain text")
    return text


def format_context(chunks: Sequence[RetrievedChunk]) -> str:
    rendered: list[str] = []
    for chunk in chunks:
        rendered.append(
            "\n".join(
                [
                    f"[chunk_id={chunk.chunk_id}]",
                    f"Document: {chunk.doc_title}",
                    f"Regulator: {chunk.regulator}",
                    f"Section: {chunk.section_path}",
                    f"Page: {chunk.page or 'n/a'}",
                    chunk.text,
                ]
            )
        )
    return "\n\n".join(rendered)


class GeminiAPIClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = settings.gemini_api_base_url.rstrip("/")
        self.api_key = settings.gemini_api_key

    async def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            raise ProviderError(
                "GEMINI_API_KEY is required for Gemini API calls",
                provider="gemini",
            )
        response: httpx.Response | None = None
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            for attempt in range(1, 6):
                try:
                    response = await client.post(
                        f"{self.base_url}/{path.lstrip('/')}",
                        headers={
                            "Content-Type": "application/json",
                            "x-goog-api-key": self.api_key,
                        },
                        json=payload,
                    )
                except httpx.HTTPError as exc:
                    if attempt == 5:
                        raise ProviderError(
                            f"Gemini API request failed: {exc}",
                            provider="gemini",
                        ) from exc
                    await asyncio.sleep(2 * attempt)
                    continue
                if response.status_code not in {429, 500, 502, 503, 504}:
                    break
                if attempt == 5:
                    break
                retry_after = response.headers.get("retry-after")
                delay = float(retry_after) if retry_after and retry_after.isdecimal() else min(60.0, 5.0 * attempt)
                await asyncio.sleep(delay)
        if response is None:
            raise ProviderError(
                "Gemini API request failed before receiving a response",
                provider="gemini",
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"Gemini API request failed with status {response.status_code}",
                provider="gemini",
                status_code=response.status_code,
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError(
                "Gemini API response was not valid JSON",
                provider="gemini",
                status_code=response.status_code,
            ) from exc


class GeminiEmbeddingProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = GeminiAPIClient(settings)
        self.last_usage_metadata: dict[str, Any] = {}

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        batch_size = max(1, self.settings.embedding_batch_size)
        for start in range(0, len(texts), batch_size):
            embeddings.extend(
                await self._embed_batch(
                    texts[start : start + batch_size],
                    task_type="RETRIEVAL_DOCUMENT",
                )
            )
        return embeddings

    async def embed_query(self, text: str) -> list[float]:
        return await self._embed(text, task_type="RETRIEVAL_QUERY")

    async def _embed_batch(self, texts: Sequence[str], *, task_type: str) -> list[list[float]]:
        if not texts:
            return []
        model = _model_resource(self.settings.embedding_model)
        payload = await self.client.post(
            f"{self.settings.embedding_model}:batchEmbedContents",
            {
                "requests": [
                    {
                        "model": model,
                        "content": {"parts": [{"text": text}]},
                        "embedContentConfig": {
                            "taskType": task_type,
                            "outputDimensionality": self.settings.embedding_dimension,
                        },
                    }
                    for text in texts
                ]
            },
        )
        self.last_usage_metadata = payload.get("usageMetadata") or {}
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list):
            raise MalformedModelOutputError("Gemini batch embedding response did not contain embeddings")
        if len(embeddings) != len(texts):
            raise MalformedModelOutputError(
                f"Gemini batch embedding count mismatch: expected {len(texts)}, got {len(embeddings)}"
            )
        return [self._parse_embedding(embedding) for embedding in embeddings]

    async def _embed(self, text: str, *, task_type: str) -> list[float]:
        payload = await self.client.post(
            f"{self.settings.embedding_model}:embedContent",
            {
                "model": _model_resource(self.settings.embedding_model),
                "content": {"parts": [{"text": text}]},
                "embedContentConfig": {
                    "taskType": task_type,
                    "outputDimensionality": self.settings.embedding_dimension,
                },
            },
        )
        self.last_usage_metadata = payload.get("usageMetadata") or {}
        return self._parse_embedding(payload.get("embedding"))

    def _parse_embedding(self, embedding_payload: Any) -> list[float]:
        values = embedding_payload.get("values") if isinstance(embedding_payload, dict) else None
        if not isinstance(values, list):
            raise MalformedModelOutputError("Gemini embedding response did not contain values")
        embedding = [float(value) for value in values]
        if len(embedding) != self.settings.embedding_dimension:
            raise MalformedModelOutputError(
                f"Gemini embedding dimension mismatch: expected {self.settings.embedding_dimension}, got {len(embedding)}"
            )
        return embedding

class GeminiGenerationProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = GeminiAPIClient(settings)
        self.last_usage_metadata: dict[str, Any] = {}

    async def generate(
        self,
        *,
        question: str,
        context_chunks: Sequence[RetrievedChunk],
        retry_note: str | None = None,
    ) -> ModelQueryResponse:
        payload = await self.client.post(
            f"{self.settings.generation_model}:generateContent",
            self._payload(question=question, context_chunks=context_chunks, retry_note=retry_note),
        )
        self.last_usage_metadata = payload.get("usageMetadata") or {}
        raw_text = _extract_text(payload)
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise MalformedModelOutputError("Gemini output was not valid JSON") from exc
        try:
            return ModelQueryResponse.model_validate(data)
        except ValidationError as exc:
            raise MalformedModelOutputError("Gemini output did not match response schema") from exc

    def _payload(
        self,
        *,
        question: str,
        context_chunks: Sequence[RetrievedChunk],
        retry_note: str | None,
    ) -> dict[str, Any]:
        instructions = (
            "You answer only from the supplied regulatory context. "
            "Return JSON only. If the context is insufficient, out of corpus, or ambiguous, refuse. "
            "Answers must be plain text only with no markdown tables or HTML. "
            "Citations must contain chunk_id values from the allowed chunk IDs only."
        )
        user_prompt = "\n\n".join(
            [
                f"Question:\n{question}",
                "Allowed chunk IDs:\n" + ", ".join(chunk.chunk_id for chunk in context_chunks),
                "Context:\n" + format_context(context_chunks),
                retry_note or "",
            ]
        ).strip()
        return {
            "systemInstruction": {"parts": [{"text": instructions}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": self.settings.max_completion_tokens,
                "responseFormat": {
                    "text": {
                        "mimeType": "application/json",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "status": {"type": "string", "enum": ["answered", "refused"]},
                                "answer": {"type": "string"},
                                "refusal_reason": {
                                    "type": "string",
                                    "enum": [
                                        "not_in_corpus",
                                        "insufficient_support",
                                        "ambiguous_question",
                                        "rate_limited",
                                    ],
                                },
                                "citations": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "chunk_id": {"type": "string"},
                                        },
                                        "required": ["chunk_id"],
                                        "additionalProperties": False,
                                    },
                                },
                            },
                            "required": ["status", "answer", "citations"],
                            "additionalProperties": False,
                        },
                    }
                },
            },
        }
