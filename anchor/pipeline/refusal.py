from __future__ import annotations

import re

from anchor.config import Settings
from anchor.schemas import RetrievedChunk

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "do",
    "for",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "when",
    "which",
    "with",
}
AMBIGUOUS_RE = re.compile(r"\b(this|that|these|those|it|latest|same)\b", re.IGNORECASE)


def is_ambiguous_question(question: str) -> bool:
    lowered = question.lower()
    if "latest one" in lowered or "this rule" in lowered or "that circular" in lowered:
        return True
    return bool(AMBIGUOUS_RE.search(question)) and not any(
        marker in lowered for marker in ("rbi", "sebi", "kyc", "master direction", "master circular")
    )


def significant_terms(question: str) -> set[str]:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", question.lower())
    return {token for token in cleaned.split() if len(token) > 2 and token not in STOPWORDS}


def has_direct_support(question: str, chunks: list[RetrievedChunk]) -> bool:
    keywords = significant_terms(question)
    if not keywords:
        return True
    for chunk in chunks:
        words = significant_terms(chunk.text)
        if len(keywords & words) >= min(2, len(keywords)):
            return True
    return False


def refusal_reason_for_context(
    question: str, reranked_chunks: list[RetrievedChunk], context_chunks: list[RetrievedChunk], settings: Settings
) -> str | None:
    if is_ambiguous_question(question):
        return "ambiguous_question"
    if not reranked_chunks:
        return "not_in_corpus"
    if max((chunk.relevance_score or 0.0) for chunk in reranked_chunks) < settings.rerank_min_top_score:
        return "not_in_corpus"
    support_count = sum(
        1 for chunk in reranked_chunks if (chunk.relevance_score or 0.0) >= settings.rerank_min_support_score
    )
    if support_count < settings.rerank_min_support_count:
        return "insufficient_support"
    if not has_direct_support(question, context_chunks):
        return "insufficient_support"
    return None
