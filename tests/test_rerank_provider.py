from anchor.providers.rerank import format_rerank_document
from anchor.schemas import RetrievedChunk


def test_rerank_document_includes_section_heading() -> None:
    chunk = RetrievedChunk(
        chunk_id="sebi_research_analysts_2026::chunk_005",
        doc_id="sebi_research_analysts_2026",
        doc_title="Master Circular for Research Analysts",
        regulator="SEBI",
        section_path="Master Circular for Research Analysts > issued under Section 11(1)",
        text="of the Securities and Exchange Board of India Act, 1992.",
        source_url="https://example.com",
    )

    document = format_rerank_document(chunk)

    assert "Section 11(1)" in document
    assert "Securities and Exchange Board of India Act" in document
