from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from langchain_core.prompts import ChatPromptTemplate
from langchain_google_vertexai import ChatVertexAI, VertexAIEmbeddings

from anchor.config import Settings
from anchor.schemas import ModelQueryResponse, RetrievedChunk


class EmbeddingProvider(Protocol):
    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class GenerationProvider(Protocol):
    async def generate(
        self,
        *,
        question: str,
        context_chunks: Sequence[RetrievedChunk],
        retry_note: str | None = None,
    ) -> ModelQueryResponse: ...


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


class VertexEmbeddingProvider:
    def __init__(self, settings: Settings) -> None:
        self.model = VertexAIEmbeddings(
            model_name=settings.embedding_model,
            project=settings.vertex_project_id,
            location=settings.vertex_location,
        )

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [list(vector) for vector in await self.model.aembed_documents(list(texts))]

    async def embed_query(self, text: str) -> list[float]:
        vector = await self.model.aembed_query(text)
        return list(vector)


class VertexGenerationProvider:
    def __init__(self, settings: Settings) -> None:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "You answer only from the supplied regulatory context. "
                        "Return structured JSON that matches the schema exactly. "
                        "If the context is insufficient, out of corpus, or ambiguous, refuse. "
                        "Answer in plain text only. Citations must contain chunk_id values from context only."
                    ),
                ),
                (
                    "human",
                    (
                        "Question:\n{question}\n\n"
                        "Allowed chunk IDs:\n{allowed_chunk_ids}\n\n"
                        "Context:\n{context}\n\n"
                        "{retry_note}"
                    ),
                ),
            ]
        )
        llm = ChatVertexAI(
            model_name=settings.generation_model,
            project=settings.vertex_project_id,
            location=settings.vertex_location,
            temperature=0,
            max_output_tokens=512,
        )
        self.chain = prompt | llm.with_structured_output(ModelQueryResponse)

    async def generate(
        self,
        *,
        question: str,
        context_chunks: Sequence[RetrievedChunk],
        retry_note: str | None = None,
    ) -> ModelQueryResponse:
        result = await self.chain.ainvoke(
            {
                "question": question,
                "allowed_chunk_ids": ", ".join(chunk.chunk_id for chunk in context_chunks),
                "context": format_context(context_chunks),
                "retry_note": retry_note or "",
            }
        )
        if isinstance(result, ModelQueryResponse):
            return result
        if isinstance(result, dict):
            return ModelQueryResponse.model_validate(result)
        return ModelQueryResponse.model_validate(result.model_dump())
