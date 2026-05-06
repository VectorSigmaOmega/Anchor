from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QueryRequest(BaseModel):
    question: str = Field(min_length=1)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        return value.strip()


class ModelCitation(BaseModel):
    chunk_id: str


class ModelQueryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: Literal["answered", "refused"]
    answer: str
    refusal_reason: Literal[
        "not_in_corpus",
        "insufficient_support",
        "ambiguous_question",
        "rate_limited",
    ] | None = None
    citations: list[ModelCitation] = Field(default_factory=list)


class Citation(BaseModel):
    chunk_id: str
    doc_id: str
    doc_title: str
    regulator: Literal["SEBI", "RBI"]
    section_title: str
    page: int | None = None
    source_url: str
    quote: str


class QueryResponse(BaseModel):
    request_id: str
    status: Literal["answered", "refused"]
    answer: str
    refusal_reason: Literal[
        "not_in_corpus",
        "insufficient_support",
        "ambiguous_question",
        "rate_limited",
    ] | None = None
    citations: list[Citation]
    disclaimer: str
    latency_ms: int


class HealthResponse(BaseModel):
    status: str


class DocumentRecord(BaseModel):
    doc_id: str
    title: str
    regulator: Literal["SEBI", "RBI"]
    doc_type: Literal["master_circular", "master_direction"]
    source_url: str
    published_at: date | None = None
    snapshot_date: date
    sha256: str
    active: bool = True
    version_label: str | None = None
    topic_family: str | None = None
    notes: str | None = None
    format: Literal["pdf", "html"]


class Manifest(BaseModel):
    snapshot_date: date
    documents: list[DocumentRecord]


class ParsedBlock(BaseModel):
    text: str
    page: int | None = None
    block_type: Literal["paragraph", "heading", "table"] = "paragraph"


class ParsedDocument(BaseModel):
    document: DocumentRecord
    blocks: list[ParsedBlock]


class ChunkRecord(BaseModel):
    chunk_id: str
    doc_id: str
    chunk_index: int
    section_path: str
    page: int | None = None
    text: str
    content_sha256: str


class RetrievedChunk(BaseModel):
    chunk_id: str
    doc_id: str
    doc_title: str
    regulator: Literal["SEBI", "RBI"]
    topic_family: str | None = None
    section_path: str
    page: int | None = None
    text: str
    source_url: str
    lexical_score: float | None = None
    dense_score: float | None = None
    fused_score: float | None = None
    relevance_score: float | None = None


class EvalRow(BaseModel):
    id: str
    question: str
    expected_outcome: Literal["answer", "refusal"]
    reference_answer: str
    reference_citations: list[dict[str, str]] = Field(default_factory=list)
    regulator: Literal["SEBI", "RBI", "mixed", "none"]
    doc_ids: list[str] = Field(default_factory=list)
    difficulty: Literal["easy", "medium", "hard"]
    notes: str = ""


class QueryExecutionResult(BaseModel):
    response: QueryResponse
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    context_chunks: list[RetrievedChunk] = Field(default_factory=list)
