from __future__ import annotations

import re

from anchor.schemas import Citation, ModelQueryResponse, RetrievedChunk


def render_quote(text: str, max_chars: int = 240) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "…"


def is_plain_text_answer(answer: str) -> bool:
    if "<" in answer and ">" in answer:
        return False
    return not ("\n|" in answer or answer.strip().startswith("|"))


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
    if not model_response.citations or not is_plain_text_answer(model_response.answer):
        return False, []

    citations: list[Citation] = []
    seen: set[str] = set()
    for item in model_response.citations:
        if item.chunk_id in seen:
            continue
        chunk = chunk_map.get(item.chunk_id)
        if not chunk:
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
                quote=render_quote(chunk.text),
            )
        )
        seen.add(item.chunk_id)
        if len(citations) >= max_rendered:
            break
    return bool(citations), citations
