from __future__ import annotations

from collections.abc import Sequence

from anchor.schemas import RetrievedChunk


def fuse_ranked_chunk_lists(
    ranked_lists: Sequence[tuple[list[RetrievedChunk], str]],
    *,
    constant: int,
) -> list[RetrievedChunk]:
    fused: dict[str, RetrievedChunk] = {}
    scores: dict[str, float] = {}

    def absorb(chunks: list[RetrievedChunk], score_attr: str) -> None:
        seen_in_list: set[str] = set()
        for index, chunk in enumerate(chunks, start=1):
            if chunk.chunk_id in seen_in_list:
                continue
            seen_in_list.add(chunk.chunk_id)
            candidate = fused.get(chunk.chunk_id)
            if not candidate:
                candidate = chunk.model_copy()
                fused[chunk.chunk_id] = candidate
            else:
                if getattr(chunk, score_attr) is not None:
                    setattr(candidate, score_attr, getattr(chunk, score_attr))
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + (1.0 / (constant + index))

    for chunks, score_attr in ranked_lists:
        absorb(chunks, score_attr)
    ranked = list(fused.values())
    for chunk in ranked:
        chunk.fused_score = scores[chunk.chunk_id]
    ranked.sort(key=lambda item: (item.fused_score or 0.0), reverse=True)
    return ranked


def fuse_ranked_chunks(
    lexical_chunks: list[RetrievedChunk],
    dense_chunks: list[RetrievedChunk],
    *,
    constant: int,
) -> list[RetrievedChunk]:
    return fuse_ranked_chunk_lists(
        [
            (lexical_chunks, "lexical_score"),
            (dense_chunks, "dense_score"),
        ],
        constant=constant,
    )
