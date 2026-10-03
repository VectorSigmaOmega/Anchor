"""Layout-aware PDF extraction with conservative table preservation."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import fitz

from anchor.schemas import DocumentRecord, ParsedBlock, ParsedDocument


def normalize_text(text: str | None) -> str:
    return " ".join((text or "").replace("\u00a0", " ").split())


HEADING_WORDS = 18
OBLIGATION = re.compile(r"\b(?:shall|must|may|should|means|include[sd]?|provided|exceed[sd]?|required)\b", re.I)


def layout_heading(text: str, spans: list[dict], body_size: float) -> bool:
    """Font size is a hint, never sufficient to classify a rule as a title."""
    if len(text) > 160 or len(text.split()) > HEADING_WORDS or not re.search(r"[A-Za-z]", text):
        return False
    if text.endswith((".", ";", ":")) or OBLIGATION.search(text):
        return False
    characters = sum(len(s["text"].strip()) for s in spans) or 1
    bold = sum(len(s["text"].strip()) for s in spans if s["flags"] & 16) / characters
    normal_size = sum(len(s["text"].strip()) for s in spans if s["size"] >= body_size - 0.7) / characters
    # Exclude small footnotes and sentence continuations. Keep their text as
    # paragraphs, including amounts/conditions printed in a different font.
    return normal_size > 0.65 and (bold > 0.65 or (text.isupper() and len(text) > 4))


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
        body_size = sizes.most_common(1)[0][0] if sizes else 11.0
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
                if partial_table:
                    text = normalize_text(" ".join(s["text"] for s in spans))
                    if text:
                        items.append((b["bbox"][1], b["bbox"][0], ParsedBlock(text=text, page=page_number)))
                    continue
                # A block can start with a chapter heading and continue with
                # body text. Classify lines, then join adjacent body lines so
                # formatting changes cannot split a sentence or its amount.
                pending: list[str] = []
                pending_position: tuple[float, float] | None = None

                def flush_paragraph(position, pending=pending, items=items, page_number=page_number) -> None:
                    if pending and position:
                        items.append((*position, ParsedBlock(text=normalize_text(" ".join(pending)), page=page_number)))
                        pending.clear()

                for line in b.get("lines", []):
                    line_spans = [s for s in line["spans"] if not represented_in_table(s)]
                    text = normalize_text(" ".join(s["text"] for s in line_spans))
                    if not text:
                        continue
                    position = (line["bbox"][1], line["bbox"][0])
                    if layout_heading(text, line_spans, body_size):
                        flush_paragraph(pending_position)
                        items.append((*position, ParsedBlock(text=text, page=page_number, block_type="heading")))
                    else:
                        if not pending:
                            pending_position = position
                        pending.append(text)
                flush_paragraph(pending_position)
            blocks.extend(item[2] for item in sorted(items, key=lambda x: (x[0], x[1])))
    return ParsedDocument(document=document, blocks=blocks)

