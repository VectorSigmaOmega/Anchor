"""Give models source excerpts to select, rather than quotations to reconstruct."""

import re
from collections.abc import Sequence

from anchor.providers.gemini import MalformedModelOutputError
from anchor.schemas import RetrievedChunk


def advance_fee_differences(evidence: dict[str, dict[str, str]], chunks: Sequence[RetrievedChunk]) -> str:
    """Surface differing advance periods in one document without deciding precedence."""
    documents = {c.chunk_id: c for c in chunks}
    findings: dict[str, dict[str, str]] = {}
    pattern = re.compile(
        r"(?:such advance|advance fees|fees in advance)[^.!?]{0,220}?"
        r"\b(one year|one quarter|12 months|twelve months)\b", re.IGNORECASE,
    )
    for evidence_id, item in evidence.items():
        match = pattern.search(item["quote"])
        if match:
            period = match.group(1).lower()
            period = "one year" if period in {"12 months", "twelve months"} else period
            doc_id = documents[item["chunk_id"]].doc_id
            findings.setdefault(doc_id, {}).setdefault(period, evidence_id)
    notes = []
    for periods in findings.values():
        if len(periods) > 1:
            notes.append("Advance-fee passages in the same document differ: " +
                         "; ".join(f"[{eid}] says {period}" for period, eid in periods.items()) +
                         ". Compare their scope and explicitly explain any unresolved inconsistency.")
    return "\n".join(notes)


def source_excerpts(chunks: Sequence[RetrievedChunk]) -> tuple[str, dict[str, dict[str, str]]]:
    evidence: dict[str, dict[str, str]] = {}
    rendered = []
    for chunk in chunks:
        lines = [f"Document: {chunk.doc_title}", f"Section: {chunk.section_path}", f"Page: {chunk.page or 'n/a'}"]
        # All excerpts are contiguous substrings of indexed text. Retain table
        # separators and footnotes; do not synthesize cleaner regulatory wording.
        text = re.sub(r"\s+", " ", chunk.text).strip()
        start = 0
        while start < len(text):
            end = min(start + 1000, len(text))
            if end < len(text):
                boundary = text.rfind(" ", start, end)
                end = boundary if boundary > start else end
            quote = text[start:end].strip()
            evidence_id = f"E{len(evidence) + 1}"
            evidence[evidence_id] = {"chunk_id": chunk.chunk_id, "quote": quote}
            lines.append(f"[{evidence_id}] {quote}")
            if end == len(text):
                break
            # Overlap retains conditions near a boundary without editing text.
            boundary = text.find(" ", max(start + 1, end - 200), end)
            start = boundary + 1 if boundary >= 0 else end
        rendered.append("\n".join(lines))
    return "\n\n".join(rendered), evidence


def hydrate_selected_excerpts(data: dict, evidence: dict[str, dict[str, str]]) -> dict:
    if not isinstance(data, dict):
        raise MalformedModelOutputError("Gemini returned an invalid answer object")
    if not isinstance(data.get("answer"), str):
        raise MalformedModelOutputError("Gemini returned invalid answer text")
    if "citations" not in data:
        references = re.findall(r"\[([^\[\]\n]+)\]", data.get("answer", ""))
        ids = list(dict.fromkeys(item.strip() for ref in references for item in ref.split(",")))
        data = {**data, "citations": [{"evidence_id": item} for item in ids]}
    citations = data.get("citations", [])
    if not isinstance(citations, list) or any(not isinstance(c, dict) for c in citations):
        raise MalformedModelOutputError("Gemini returned invalid evidence citations")
    # Legacy provider test fixtures still supply quotes. They remain subject to
    # the same downstream source validation as every generated response.
    if citations and "evidence_id" not in citations[0]:
        return data
    selected: dict[str, int] = {}
    hydrated = []
    try:
        for citation in citations:
            evidence_id = citation["evidence_id"]
            if evidence_id in selected:
                raise ValueError("duplicate excerpt")
            hydrated.append(evidence[evidence_id])
            selected[evidence_id] = len(hydrated)

        def reference(match: re.Match) -> str:
            ids = [item.strip() for item in match.group(1).split(",")]
            if not all(item in selected for item in ids):
                raise ValueError("answer references an unselected excerpt")
            return "".join(f"[{selected[item]}]" for item in ids)

        answer = re.sub(r"\[([^\[\]\n]+)\]", reference, data.get("answer", ""))
        return {**data, "answer": answer, "citations": hydrated}
    except (KeyError, TypeError, ValueError) as exc:
        raise MalformedModelOutputError("Gemini returned invalid evidence references") from exc
