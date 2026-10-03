from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup

from anchor.ingest.layout import normalize_text, parse_layout, table_text
from anchor.schemas import DocumentRecord, ParsedBlock, ParsedDocument

HEADING_RE = re.compile(r"^((\d+(\.\d+)*)|([IVXLC]+))[.)]?\s+\S+")


def looks_like_heading(text: str) -> bool:
    if len(text) > 140:
        return False
    if HEADING_RE.match(text):
        return True
    if text.isupper() and 4 < len(text) < 100:
        return True
    return bool(text.istitle() and len(text.split()) <= 12)


def serialize_table(rows: list[list[str | None]]) -> str:
    return table_text(rows)


def parse_pdf(document: DocumentRecord, path: Path) -> ParsedDocument:
    return parse_layout(document, path)


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
