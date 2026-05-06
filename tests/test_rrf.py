from anchor.pipeline.rrf import fuse_ranked_chunks
from anchor.schemas import RetrievedChunk


def make_chunk(chunk_id: str, *, lexical_score: float | None = None, dense_score: float | None = None) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        doc_id="doc",
        doc_title="Document",
        regulator="RBI",
        section_path="Document",
        text="sample text",
        source_url="https://example.com",
        lexical_score=lexical_score,
        dense_score=dense_score,
    )


def test_rrf_fuses_and_preserves_scores() -> None:
    lexical = [
        make_chunk("chunk-a", lexical_score=0.9),
        make_chunk("chunk-b", lexical_score=0.7),
    ]
    dense = [
        make_chunk("chunk-b", dense_score=0.88),
        make_chunk("chunk-c", dense_score=0.82),
    ]

    fused = fuse_ranked_chunks(lexical, dense, constant=60)

    assert [chunk.chunk_id for chunk in fused] == ["chunk-b", "chunk-a", "chunk-c"]
    assert fused[0].lexical_score == 0.7
    assert fused[0].dense_score == 0.88

