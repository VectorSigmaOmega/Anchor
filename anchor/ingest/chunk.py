"""Structure-aware packing with a hard word bound and complete-block overlap."""

from __future__ import annotations

import re
from hashlib import sha256

from anchor.schemas import ChunkRecord, ParsedBlock, ParsedDocument

CHUNKING_VERSION = "layout-structured-v2"
MAX_WORDS = 450
OVERLAP_WORDS = 75
CLAUSE = re.compile(r"^(\d{1,3})(?:\.(\d+(?:\.\d+)*))?[.)]?\s+")


def infer_heading_level(text: str) -> int:
    prefix = text.split(" ", 1)[0].rstrip(".)")
    if prefix and prefix[0].isdigit():
        return min(prefix.count(".") + 1, 4)
    return 2


def split_block(block: ParsedBlock, *, structured: bool) -> list[ParsedBlock]:
    limit = MAX_WORDS - OVERLAP_WORDS
    if len(block.text.split()) <= limit:
        return [block]
    if block.block_type == "table":
        rows = block.text.splitlines()
        header = rows[0]
        parts: list[str] = []
        current = [header]
        for row in rows[1:]:
            if len(" ".join([*current, row]).split()) > limit and len(current) > 1:
                parts.append("\n".join(current))
                current = [header]
            current.append(row)
        parts.append("\n".join(current))
    elif structured:
        sentences = re.split(r"(?<=[.;])\s+(?=[A-Z(\d])", block.text)
        parts = []
        current = []
        for sentence in sentences:
            if len(" ".join([*current, sentence]).split()) > limit and current:
                parts.append(" ".join(current))
                current = []
            current.append(sentence)
        if current:
            parts.append(" ".join(current))
    else:
        parts = [block.text]
    result = []
    for part in parts:
        words = part.split()
        for start in range(0, len(words), limit):
            result.append(block.model_copy(update={"text": " ".join(words[start : start + limit])}))
    return result


def build_variant(parsed: ParsedDocument, strategy: str) -> list[ChunkRecord]:
    if strategy not in {"fixed", "structured"}:
        raise ValueError(strategy)
    structured = strategy == "structured"
    chunks: list[ChunkRecord] = []
    headings = [parsed.document.title]
    buffer: list[ParsedBlock] = []

    def flush(overlap: bool = False) -> None:
        nonlocal buffer
        if not buffer:
            return
        text = "\n".join(b.text for b in buffer)
        chunks.append(
            ChunkRecord(
                chunk_id=f"{parsed.document.doc_id}::{strategy}_{len(chunks):04d}",
                doc_id=parsed.document.doc_id,
                chunk_index=len(chunks),
                section_path=" > ".join(headings[-4:]),
                page=buffer[0].page,
                text=text,
                content_sha256=sha256(text.encode()).hexdigest(),
            )
        )
        if not overlap:
            buffer = []
        elif structured:
            # Carry complete trailing blocks when possible; never cut a table
            # row or leave a sentence fragment as the sole overlap.
            carry: list[ParsedBlock] = []
            size = 0
            for block in reversed(buffer):
                if size + len(block.text.split()) > OVERLAP_WORDS:
                    break
                carry.insert(0, block)
                size += len(block.text.split())
            buffer = carry
        else:
            buffer = [buffer[-1].model_copy(update={"text": " ".join(text.split()[-OVERLAP_WORDS:])})]

    for original in parsed.blocks:
        if original.block_type == "heading":
            flush()
            level = infer_heading_level(original.text)
            if re.match(r"^(?:chapter|annexure|annex|appendix|part)\b", original.text, re.I):
                headings[:] = headings[:1]
            else:
                major = int(len(headings) > 1 and bool(re.match(
                    r"^(?:chapter|annexure|annex|appendix|part)\b", headings[1], re.I,
                )))
                headings[:] = headings[:level + major]
            headings.append(original.text)
        for block in split_block(original, structured=structured):
            size = sum(len(b.text.split()) for b in buffer)
            clause = CLAUSE.match(block.text)
            # Start a new top-level numbered clause when the current chunk is
            # substantial, keeping subclauses/conditions in their parent's group.
            if structured and clause and not clause.group(2) and size >= 150:
                flush()
                size = 0
            if size + len(block.text.split()) > MAX_WORDS:
                flush(overlap=True)
            buffer.append(block)
    flush()
    return chunks


def build_chunks(parsed: ParsedDocument) -> list[ChunkRecord]:
    return build_variant(parsed, "structured")
