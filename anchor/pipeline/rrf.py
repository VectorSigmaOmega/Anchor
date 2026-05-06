from __future__ import annotations

from anchor.schemas import RetrievedChunk


def fuse_ranked_chunks(
    lexical_chunks: list[RetrievedChunk],
    dense_chunks: list[RetrievedChunk],
    *,
    constant: int,
) -> list[RetrievedChunk]:
    fused: dict[str, RetrievedChunk] = {}
    scores: dict[str, float] = {}

    def absorb(chunks: list[RetrievedChunk], score_attr: str) -> None:
        for index, chunk in enumerate(chunks, start=1):
            candidate = fused.get(chunk.chunk_id)
            if not candidate:
                candidate = chunk.model_copy()
                fused[chunk.chunk_id] = candidate
            else:
                if getattr(chunk, score_attr) is not None:
                    setattr(candidate, score_attr, getattr(chunk, score_attr))
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + (1.0 / (constant + index))

    absorb(lexical_chunks, "lexical_score")
    absorb(dense_chunks, "dense_score")
    ranked = list(fused.values())
    for chunk in ranked:
        chunk.fused_score = scores[chunk.chunk_id]
    ranked.sort(key=lambda item: (item.fused_score or 0.0), reverse=True)
    return ranked
