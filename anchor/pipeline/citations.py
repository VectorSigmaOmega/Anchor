from __future__ import annotations

import re

from anchor.pipeline.refusal import significant_terms
from anchor.schemas import Citation, ModelQueryResponse, RetrievedChunk


def render_quote(text: str, max_chars: int = 240, *, focus: str = "") -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    start = 0
    if focus:
        keywords = significant_terms(focus)
        candidates = [0, *(match.end() for match in re.finditer(r"[.;:]\s+", compact))]
        start = max(candidates, key=lambda offset: len(keywords & significant_terms(compact[offset : offset + max_chars - 2])))
    excerpt = compact[start : start + max_chars - 2].rstrip()
    return ("…" if start else "") + excerpt + ("…" if start + max_chars - 2 < len(compact) else "")


def citation_quote_text(chunk: RetrievedChunk) -> str:
    section_title = chunk.section_path.split(" > ")[-1]
    return f"{section_title} {chunk.text}".strip()


def is_plain_text_answer(answer: str) -> bool:
    if "<" in answer and ">" in answer:
        return False
    return not ("\n|" in answer or answer.strip().startswith("|"))


def verified_quote(quote: str, source: str) -> str | None:
    quote = re.sub(r"\s+", " ", quote).strip()
    source = re.sub(r"\s+", " ", source).strip()
    if quote and quote in source:
        return quote
    # Recover an abridged quotation only when every substantial fragment is
    # verbatim and occurs in order. Return the actual contiguous source span,
    # including intervening conditions, rather than displaying model ellipses.
    parts = [part.strip() for part in re.split(r"\.{3,}|…", quote) if part.strip()]
    if len(parts) < 2 or any(len(part) < 30 for part in parts):
        return None
    start = -1
    end = 0
    for part in parts:
        position = source.find(part, end)
        if position < 0:
            return None
        if start < 0:
            start = position
        end = position + len(part)
    return source[start:end] if end - start <= 1600 else None


def validate_and_hydrate_citations(
    model_response: ModelQueryResponse,
    context_chunks: list[RetrievedChunk],
    *,
    max_rendered: int,
) -> tuple[bool, list[Citation]]:
    chunk_map = {chunk.chunk_id: chunk for chunk in context_chunks}
    if model_response.status == "refused":
        is_valid = (
            len(model_response.citations) == 0
            and bool(model_response.refusal_reason)
            and model_response.answer == ""
        )
        return (is_valid, [])
    if (
        not model_response.answer.strip()
        or model_response.refusal_reason is not None
        or not model_response.citations
        or len(model_response.citations) > max_rendered
        or not is_plain_text_answer(model_response.answer)
    ):
        return False, []

    citations: list[Citation] = []
    seen: set[str] = set()
    for item in model_response.citations:
        if item.chunk_id in seen:
            return False, []
        chunk = chunk_map.get(item.chunk_id)
        if not chunk:
            return False, []
        quote = verified_quote(item.quote, chunk.retrieval_text())
        if quote is None:
            return False, []
        citations.append(
            Citation(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                doc_title=chunk.doc_title,
                regulator=chunk.regulator,
                section_title=chunk.section_path.split(" > ")[-1],
                page=chunk.page,
                source_url=chunk.source_url,
                quote=quote,
            )
        )
        seen.add(item.chunk_id)
    markers = [int(marker) for marker in re.findall(r"\[(\d+)\]", model_response.answer)]
    if any(marker < 1 or marker > len(citations) for marker in markers):
        return False, []
    return bool(citations), citations
