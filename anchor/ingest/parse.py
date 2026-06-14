from __future__ import annotations

import re
from pathlib import Path

import fitz
from bs4 import BeautifulSoup

from anchor.schemas import DocumentRecord, ParsedBlock, ParsedDocument

HEADING_RE = re.compile(r"^((\d+(\.\d+)*)|([IVXLC]+))[.)]?\s+\S+")


def normalize_text(text: str | None) -> str:
    if text is None:
        return ""
    return " ".join(text.replace("\u00a0", " ").split())


def looks_like_heading(text: str) -> bool:
    if len(text) > 140:
        return False
    if HEADING_RE.match(text):
        return True
    if text.isupper() and 4 < len(text) < 100:
        return True
    return bool(text.istitle() and len(text.split()) <= 12)


def serialize_table(rows: list[list[str | None]]) -> str:
    rendered_rows = []
    for row in rows:
        cleaned = [normalize_text(cell) for cell in row if normalize_text(cell)]
        if cleaned:
            rendered_rows.append(" | ".join(cleaned))
    return "\n".join(rendered_rows)


def parse_pdf(document: DocumentRecord, path: Path) -> ParsedDocument:
    blocks: list[ParsedBlock] = []
    with fitz.open(path) as pdf:
        for page_index, page in enumerate(pdf, start=1):
            try:
                tables = page.find_tables()
            except Exception:
                tables = None
            if tables:
                for table in tables.tables:
                    table_text = serialize_table(table.extract())
                    if table_text:
                        blocks.append(
                            ParsedBlock(text=table_text, page=page_index, block_type="table")
                        )
            for raw_block in page.get_text("blocks", sort=True):
                text = normalize_text(raw_block[4])
                if not text:
                    continue
                block_type = "heading" if looks_like_heading(text) else "paragraph"
                blocks.append(ParsedBlock(text=text, page=page_index, block_type=block_type))
    return ParsedDocument(document=document, blocks=blocks)


def parse_html(document: DocumentRecord, path: Path) -> ParsedDocument:
    html = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")
    container = soup.find("main") or soup.find("article") or soup.body or soup
    blocks: list[ParsedBlock] = []
    for node in container.find_all(["h1", "h2", "h3", "h4", "p", "li", "table"]):
        if node.name == "table":
            rows: list[list[str]] = []
            for tr in node.find_all("tr"):
                rows.append([cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])])
            table_text = serialize_table(rows)
            if table_text:
                blocks.append(ParsedBlock(text=table_text, block_type="table"))
            continue
        text = normalize_text(node.get_text(" ", strip=True))
        if not text:
            continue
        block_type = "heading" if node.name.startswith("h") else "paragraph"
        blocks.append(ParsedBlock(text=text, block_type=block_type))
    return ParsedDocument(document=document, blocks=blocks)


def parse_document(document: DocumentRecord, path: Path) -> ParsedDocument:
    if document.format == "pdf":
        return parse_pdf(document, path)
    return parse_html(document, path)
