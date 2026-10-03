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
    "does",
    "must",
    "should",
    "can",
    "could",
    "please",
    "tell",
    "about",
    "under",
    "how",
    "explain",
    "when",
    "which",
    "with",
}
AMBIGUOUS_RE = re.compile(r"\b(this|that|these|those|it|latest|same)\b", re.IGNORECASE)
TAX_TOPIC_RE = re.compile(r"\b(gst|goods and services tax|income tax|capital gains tax|tax rate|tax filing)\b", re.IGNORECASE)
TAX_REQUEST_RE = re.compile(r"\b(rate|rates|filing|file|return|returns|deduct|deduction|taxable|payable)\b", re.IGNORECASE)


def is_out_of_scope_question(question: str) -> bool:
    # Incidental GST mentions in SEBI fee disclosures are still in scope.
    return bool(TAX_TOPIC_RE.search(question) and TAX_REQUEST_RE.search(question))


def is_ambiguous_question(question: str) -> bool:
    lowered = question.lower()
    if "latest one" in lowered or "this rule" in lowered or "that circular" in lowered:
        return True
    # A pronoun inside an otherwise specific question often refers to its
    # explicit subject: "the annual RA fee limit ... does it apply to ...?".
    if re.search(r"\bit\b", lowered) and len(significant_terms(question) - {"it"}) >= 5:
        return False
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
        words = significant_terms(chunk.retrieval_text())
        if len(keywords & words) >= min(2, len(keywords)):
            return True
    return False


def refusal_reason_for_context(
    question: str,
    reranked_chunks: list[RetrievedChunk],
    context_chunks: list[RetrievedChunk],
    settings: Settings,
    *,
    ambiguity_question: str | None = None,
) -> str | None:
    if is_out_of_scope_question(ambiguity_question or question):
        return "not_in_corpus"
    if is_ambiguous_question(ambiguity_question or question):
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
    support_question = ambiguity_question or question
    if not has_direct_support(support_question, context_chunks) and not has_direct_support(question, context_chunks):
        return "insufficient_support"
    return None
