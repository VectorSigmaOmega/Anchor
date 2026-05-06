from __future__ import annotations

import re
from hashlib import sha256

from anchor.schemas import ChunkRecord, ParsedDocument

TARGET_TOKENS = 450
OVERLAP_TOKENS = 75
WORD_RE = re.compile(r"\S+")


def estimate_tokens(text: str) -> int:
    return len(WORD_RE.findall(text))


def tail_overlap(text: str, max_tokens: int) -> str:
    words = WORD_RE.findall(text)
    if len(words) <= max_tokens:
        return text
    return " ".join(words[-max_tokens:])


def infer_heading_level(text: str) -> int:
    prefix = text.split(" ", 1)[0].rstrip(".)")
    if prefix and prefix[0].isdigit():
        return min(prefix.count(".") + 1, 4)
    if prefix.isupper():
        return 2
    return 2


def emit_chunk(
    chunks: list[ChunkRecord],
    document_id: str,
    section_path: str,
    buffer: list[str],
    page: int | None,
) -> str:
    text = " ".join(part.strip() for part in buffer if part.strip()).strip()
    if not text:
        return ""
    content_hash = sha256(text.encode("utf-8")).hexdigest()
    chunk = ChunkRecord(
        chunk_id=f"{document_id}::chunk_{len(chunks):03d}",
        doc_id=document_id,
        chunk_index=len(chunks),
        section_path=section_path,
        page=page,
        text=text,
        content_sha256=content_hash,
    )
    chunks.append(chunk)
    return text


def build_chunks(parsed: ParsedDocument) -> list[ChunkRecord]:
    headings = [parsed.document.title]
    chunks: list[ChunkRecord] = []
    buffer: list[str] = []
    buffer_tokens = 0
    buffer_page: int | None = None

    def current_section_path() -> str:
        return " > ".join(headings[-4:])

    def flush(*, carry_overlap: bool) -> None:
        nonlocal buffer, buffer_tokens, buffer_page
        text = emit_chunk(
            chunks=chunks,
            document_id=parsed.document.doc_id,
            section_path=current_section_path(),
            buffer=buffer,
            page=buffer_page,
        )
        if carry_overlap and text:
            overlap = tail_overlap(text, OVERLAP_TOKENS)
            buffer = [overlap]
            buffer_tokens = estimate_tokens(overlap)
        else:
            buffer = []
            buffer_tokens = 0
        buffer_page = None

    for block in parsed.blocks:
        if block.block_type == "heading":
            if buffer:
                flush(carry_overlap=False)
            level = infer_heading_level(block.text)
            headings[:] = headings[:level]
            headings.append(block.text)
            continue

        block_tokens = estimate_tokens(block.text)
        if not buffer:
            buffer_page = block.page
        if buffer and buffer_tokens + block_tokens > TARGET_TOKENS:
            flush(carry_overlap=True)
            if buffer and buffer_page is None:
                buffer_page = block.page
        buffer.append(block.text)
        buffer_tokens += block_tokens

    if buffer:
        flush(carry_overlap=False)
    return chunks

