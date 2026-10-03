"""Experimental PDF parsing/chunking. Production ingestion is unchanged.

Budgets explicitly count whitespace words, matching the existing index's budget.
Both variants share the same layout parser; only packing/overlap differs.
"""

from __future__ import annotations

import re
from collections import Counter
from hashlib import sha256
from pathlib import Path

import fitz

from anchor.ingest.chunk import infer_heading_level
from anchor.ingest.parse import normalize_text
from anchor.schemas import ChunkRecord, DocumentRecord, ParsedBlock, ParsedDocument

MAX_WORDS = 450
OVERLAP_WORDS = 75
HEADING_WORDS = 18
OBLIGATION = re.compile(r"\b(?:shall|must|may|should|means|include[sd]?|provided|exceed[sd]?|required)\b", re.I)
CLAUSE = re.compile(r"^(\d{1,3})(?:\.(\d+(?:\.\d+)*))?[.)]?\s+")


def layout_heading(text: str, spans: list[dict], body_size: float) -> bool:
    if len(text) > 160 or len(text.split()) > HEADING_WORDS or not re.search(r"[A-Za-z]", text):
        return False
    if text.endswith((".", ";", ":")) or OBLIGATION.search(text):
        return False
    characters = sum(len(s["text"].strip()) for s in spans) or 1
    bold = sum(len(s["text"].strip()) for s in spans if s["flags"] & 16) / characters
    larger = sum(len(s["text"].strip()) for s in spans if s["size"] > body_size + 0.7) / characters
    return bold > 0.65 or larger > 0.65 or (text.isupper() and len(text) > 4)


def table_text(rows: list[list[str | None]]) -> str:
    # Empty cells retain their positions, unlike the production serializer.
    return "\n".join(" | ".join(normalize_text(c) for c in row) for row in rows if any(normalize_text(c) for c in row))


def parse_layout(document: DocumentRecord, path: Path) -> ParsedDocument:
    blocks: list[ParsedBlock] = []
    with fitz.open(path) as pdf:
        sizes: Counter = Counter()
        for page in pdf:
            for b in page.get_text("dict")["blocks"]:
                for line in b.get("lines", []):
                    for span in line["spans"]:
                        sizes[round(span["size"], 1)] += len(span["text"].strip())
        body_size = sizes.most_common(1)[0][0]
        for page_number, page in enumerate(pdf, 1):
            items: list[tuple[float, float, ParsedBlock]] = []
            raw_blocks = page.get_text("dict", sort=True)["blocks"]
            raw_spans = [s for b in raw_blocks for line in b.get("lines", []) for s in line["spans"]]
            try:
                tables = page.find_tables().tables
            except Exception:
                tables = []
            table_regions: list[tuple[fitz.Rect, bool]] = []
            for table in tables:
                text = table_text(table.extract())
                if text:
                    rect = fitz.Rect(table.bbox)
                    original = " ".join(
                        s["text"]
                        for s in raw_spans
                        if rect.contains(fitz.Rect(s["bbox"]).tl + (fitz.Rect(s["bbox"]).br - fitz.Rect(s["bbox"]).tl) / 2)
                    )
                    before = Counter(c.lower() for c in original if c.isalnum())
                    after = Counter(c.lower() for c in text if c.isalnum())
                    table_regions.append((rect, not bool(before - after)))
                    items.append((rect.y0, rect.x0, ParsedBlock(text=text, page=page_number, block_type="table")))

            def represented_in_table(span: dict, regions=table_regions) -> bool:
                rect = fitz.Rect(span["bbox"])
                containing = [complete for table_rect, complete in regions if table_rect.contains(rect.tl + (rect.br - rect.tl) / 2)]
                return bool(containing) and all(containing)

            for b in raw_blocks:
                # Remove only spans inside an already serialized table. A PDF
                # block can contain both its section heading and table cells.
                original_spans = [s for line in b.get("lines", []) for s in line["spans"]]
                spans = [s for s in original_spans if not represented_in_table(s)]
                partial_table = any(
                    r.contains(fitz.Rect(s["bbox"]).tl + (fitz.Rect(s["bbox"]).br - fitz.Rect(s["bbox"]).tl) / 2) and s["text"].strip()
                    for s in spans
                    for r, _ in table_regions
                )
                # Preserve incomplete tables' original text intact. Keeping only
                # missing fragments can detach a value from its row label/unit.
                if partial_table:
                    spans = original_spans
                text = normalize_text(" ".join(s["text"] for s in spans))
                if not text:
                    continue
                kind = "heading" if not partial_table and layout_heading(text, spans, body_size) else "paragraph"
                items.append((b["bbox"][1], b["bbox"][0], ParsedBlock(text=text, page=page_number, block_type=kind)))
            blocks.extend(item[2] for item in sorted(items, key=lambda x: (x[0], x[1])))
    return ParsedDocument(document=document, blocks=blocks)


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
            headings[:] = headings[:level]
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
