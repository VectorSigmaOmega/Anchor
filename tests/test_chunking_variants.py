from collections import Counter
from types import SimpleNamespace

import fitz
import pytest

from anchor.schemas import DocumentRecord, ParsedBlock, ParsedDocument
from scripts.chunking_variants import build_variant, layout_heading, parse_layout, table_text


def document():
    return DocumentRecord(
        doc_id="test",
        title="Test circular",
        regulator="RBI",
        doc_type="master_direction",
        source_url="https://example.com/test.pdf",
        snapshot_date="2026-05-02",
        sha256="test",
        format="pdf",
    )


def test_numbered_obligation_and_footnote_are_not_headings():
    spans = [{"text": "7. Banks shall repay within twelve months.", "flags": 0, "size": 11}]
    assert not layout_heading(spans[0]["text"], spans, 11)
    spans = [{"text": "42 Inserted by circular dated February 9, 2026.", "flags": 0, "size": 8}]
    assert not layout_heading(spans[0]["text"], spans, 11)
    spans = [{"text": "4.1 Collateral", "flags": 16, "size": 11}]
    assert layout_heading(spans[0]["text"], spans, 11)


def test_table_empty_cells_retain_column_positions():
    assert table_text([["Bank", "Target", "Basis"], ["SFB", None, "ANBC"]]) == "Bank | Target | Basis\nSFB |  | ANBC"


@pytest.mark.parametrize("strategy", ["fixed", "structured"])
def test_oversized_blocks_keep_all_words_and_bound_chunks(strategy):
    words = [f"word{i}" for i in range(1200)]
    parsed = ParsedDocument(document=document(), blocks=[ParsedBlock(text=" ".join(words), page=3)])
    chunks = build_variant(parsed, strategy)
    assert not (Counter(words) - Counter(" ".join(c.text for c in chunks).split()))
    assert all(len(c.text.split()) <= 450 for c in chunks)
    assert all(c.page == 3 for c in chunks)


@pytest.mark.parametrize("strategy", ["fixed", "structured"])
def test_heading_and_condition_remain_in_searchable_text(strategy):
    parsed = ParsedDocument(
        document=document(),
        blocks=[
            ParsedBlock(text="4.1 Collateral", block_type="heading", page=4),
            ParsedBlock(text="Banks shall waive collateral for eligible loans.", page=4),
            ParsedBlock(text="Provided that the voluntary gold exception applies.", page=4),
        ],
    )
    chunks = build_variant(parsed, strategy)
    assert len(chunks) == 1
    assert "4.1 Collateral" in chunks[0].text
    assert "Provided that" in chunks[0].text


@pytest.mark.parametrize("omit_cell", [False, True])
def test_pdf_table_is_interleaved_and_not_extracted_twice(tmp_path, monkeypatch, omit_cell):
    path = tmp_path / "table.pdf"
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((50, 40), "4.1 Deposit limits", fontname="hebo", fontsize=12)
    for y in [60, 90, 120, 150]:
        page.draw_line((50, y), (350, y))
    for x in [50, 200, 350]:
        page.draw_line((x, 60), (x, 150))
    for x, y, text in [
        (60, 80, "Category"),
        (210, 80, "Amount"),
        (60, 110, "Eligible"),
        (210, 110, "50000"),
        (60, 140, "Eligible"),
        (210, 140, "50000"),
    ]:
        page.insert_text((x, y), text, fontsize=11)
    page.insert_text((50, 180), "9. Banks shall review the limits annually.", fontsize=11)
    pdf.save(path)
    pdf.close()
    if omit_cell:
        original = fitz.Page.find_tables

        def incomplete_table(page):
            found = original(page)
            tables = []
            for table in found.tables:
                rows = table.extract()
                rows[-1][-1] = ""
                tables.append(SimpleNamespace(bbox=table.bbox, extract=lambda rows=rows: rows))
            return SimpleNamespace(tables=tables)

        monkeypatch.setattr(fitz.Page, "find_tables", incomplete_table)
    parsed = parse_layout(document(), path)
    assert parsed.blocks[0].block_type == "heading"
    assert parsed.blocks[1].block_type == "table"
    assert parsed.blocks[-1].block_type == "paragraph"
    text = " ".join(b.text for b in parsed.blocks)
    if omit_cell:
        assert text.count("50000") >= 2
    else:
        assert text.count("50000") == 2
    if omit_cell:
        assert text.count("Eligible") >= 2
    else:
        assert text.count("Eligible") == 2
