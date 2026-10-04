"""Bounded multipart retrieval and verification, with request-local graph state."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from anchor.pipeline.citations import validate_and_hydrate_citations
from anchor.providers.gemini import MalformedModelOutputError
from anchor.schemas import ModelQueryResponse, RetrievedChunk


class EvidenceReview(BaseModel):
    missing_searches: list[str] = Field(max_length=2)
    limitations: list[str] = Field(max_length=6)
    findings: list[str] = Field(max_length=48)
    differences: list[str] = Field(default_factory=list, max_length=12)


class AnswerReview(BaseModel):
    issues: list[str] = Field(max_length=8)


class WorkflowState(TypedDict, total=False):
    question: str
    requirements: list[str]
    reranked: list[RetrievedChunk]
    context: list[RetrievedChunk]
    missing_searches: list[str]
    limitations: list[str]
    findings: list[str]
    differences: list[str]
    followup_done: bool
    draft: ModelQueryResponse
    issues: list[str]
    repaired: bool
    verified: bool
    malformed: bool


PROPOSAL_RE = re.compile(r"\b(?:propos(?:e|es|ed)|plans?|wants?|intends?)\b", re.I)
MONEY_RE = re.compile(r"(?:Rs\.?|₹)\s*(\d[\d,]*(?:\.\d+)?)\s*(crore|lakh|thousand)?\b", re.I)
PERIOD_RE = re.compile(r"\b(\d+(?:\.\d+)?|one|two|three|four|five|six|twelve|eighteen)\s*[- ]\s*"
                       r"(working\s+days?|days?|months?|quarters?|years?)\b", re.I)
PERCENT_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:%|per\s*cent|percent)\b", re.I)
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "twelve": 12, "eighteen": 18}


def quantity_mentions(text: str) -> dict[tuple[str, Decimal], str]:
    found = {}
    for match in MONEY_RE.finditer(text):
        scale = {None: 1, "thousand": 1000, "lakh": 100000, "crore": 10000000}[match[2].lower() if match[2] else None]
        found[("rupees", Decimal(match[1].replace(",", "")) * scale)] = match[0]
    for match in PERIOD_RE.finditer(text):
        number = NUMBER_WORDS.get(match[1].lower())
        number = Decimal(number if number is not None else match[1])
        unit = match[2].lower().replace("working ", "").rstrip("s")
        kind, value = ("days", number) if unit == "day" else (
            "months", number * {"month": 1, "quarter": 3, "year": 12}[unit])
        found[(kind, value)] = match[0]
    for match in PERCENT_RE.finditer(text):
        found[("percent", Decimal(match[1]))] = match[0]
    return found


def missing_proposal_values(question: str, answer: str) -> list[str]:
    current = question.rsplit("Current question:", 1)[-1]
    proposals = {}
    for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", current):
        if PROPOSAL_RE.search(sentence):
            proposals.update(quantity_mentions(sentence))
    answered = quantity_mentions(answer)
    return [label for value, label in proposals.items() if value not in answered]


class MultipartWorkflow:
    def __init__(
        self, *,
        plan: Callable[[str], Awaitable[list[str]]],
        retrieve: Callable[[list[str], list[RetrievedChunk]], Awaitable[tuple[list[RetrievedChunk], list[RetrievedChunk]]]],
        coverage: Callable[[str, list[str], list[RetrievedChunk]], Awaitable[EvidenceReview]],
        generate: Callable[[str, list[RetrievedChunk], str | None], Awaitable[ModelQueryResponse]],
        verify: Callable[[str, list[str], ModelQueryResponse, list[RetrievedChunk], list[str], list[str]], Awaitable[AnswerReview]],
        max_citations: int,
    ):
        self.plan = plan
        self.retrieve = retrieve
        self.coverage = coverage
        self.generate = generate
        self.verify = verify
        self.max_citations = max_citations
        builder = StateGraph(WorkflowState)
        for name in ["planning", "retrieval", "coverage_check", "targeted_retrieval", "drafting", "verification", "repair"]:
            builder.add_node(name, getattr(self, name))
        builder.add_edge(START, "planning")
        builder.add_edge("planning", "retrieval")
        builder.add_edge("retrieval", "coverage_check")
        builder.add_conditional_edges(
            "coverage_check",
            lambda s: "targeted_retrieval" if s["missing_searches"] and not s.get("followup_done") else "drafting",
            {"targeted_retrieval": "targeted_retrieval", "drafting": "drafting"},
        )
        builder.add_edge("targeted_retrieval", "coverage_check")
        builder.add_edge("drafting", "verification")
        builder.add_conditional_edges("verification", lambda s: "repair" if s["issues"] and not s["repaired"] else END,
                                      {"repair": "repair", END: END})
        builder.add_edge("repair", "verification")
        self.graph = builder.compile()

    async def run(self, question: str) -> WorkflowState:
        return await self.graph.ainvoke({"question": question, "repaired": False, "followup_done": False}, config={"recursion_limit": 12})

    async def planning(self, state: WorkflowState):
        return {"requirements": await self.plan(state["question"])}

    async def retrieval(self, state: WorkflowState):
        reranked, context = await self.retrieve(state["requirements"], [])
        return {"reranked": reranked, "context": context}

    async def coverage_check(self, state: WorkflowState):
        if not state["context"]:
            return {"missing_searches": [], "limitations": [], "findings": [], "differences": []}
        review = await self.coverage(state["question"], state["requirements"], state["context"])
        return {"missing_searches": review.missing_searches, "limitations": review.limitations,
                "findings": review.findings, "differences": review.differences}

    async def targeted_retrieval(self, state: WorkflowState):
        reranked, context = await self.retrieve(state["missing_searches"], state["context"])
        return {"reranked": reranked, "context": context, "followup_done": True}

    def drafting_note(self, state: WorkflowState, *, include_findings: bool = True) -> str:
        note = "Requested parts to cover (search questions are not regulatory facts):\n" + "\n".join(state["requirements"])
        if include_findings and state.get("findings"):
            note += "\nSource-linked findings for the requested tasks (verify every detail against the excerpts):\n"
            note += "\n".join(state["findings"])
        if include_findings and state.get("differences"):
            note += "\nPotential differences between provisions (compare scope; do not invent precedence):\n"
            note += "\n".join(state["differences"])
        if state.get("limitations"):
            note += "\nEvidence gaps identified before follow-up retrieval (check the current evidence again):\n"
            note += "\n".join(state["limitations"])
        return note

    async def drafting(self, state: WorkflowState):
        return await self.draft(state, self.drafting_note(state))

    async def verification(self, state: WorkflowState):
        draft = state["draft"]
        valid, _ = validate_and_hydrate_citations(draft, state["context"], max_rendered=self.max_citations)
        if state.get("malformed") or not valid:
            issues = ["Invalid source citations or response format. Use only the supplied excerpt references; keep refusals empty."]
        elif not state["context"]:
            issues = []
        elif draft.status == "answered" and (missing := missing_proposal_values(state["question"], draft.answer)):
            issues = ["Assess the user's proposed amount or period explicitly, naming it and giving a supported verdict: "
                      + value for value in missing[:8]]
        else:
            try:
                review = await self.verify(state["question"], state["requirements"], draft, state["context"],
                                           state.get("findings", []), state.get("differences", []))
                issues = review.issues
            except MalformedModelOutputError:
                issues = ["The claim review could not be validated. Recheck each claim against the current official evidence."]
        return {"issues": issues, "verified": not issues}

    async def repair(self, state: WorkflowState):
        note = self.drafting_note(state, include_findings=False)
        note += "\nThe draft failed verification. Correct these issues using the current evidence:\n"
        note += "\n".join(state["issues"])
        note += (
            "\nUse source 'may' wording explicitly for discretionary outcomes. A calculated 'up to' limit is a maximum "
            "eligible amount, not a guaranteed amount received. Disclose both incompatible explicit source requirements. "
            "If a claim is unsupported, remove it or explicitly state that the relevant part cannot be established."
        )
        return {**await self.draft(state, note), "repaired": True}

    async def draft(self, state: WorkflowState, note: str):
        refusal = ModelQueryResponse(status="refused", answer="", refusal_reason="insufficient_support", citations=[])
        if not state["context"]:
            return {"draft": refusal, "malformed": False}
        try:
            return {"draft": await self.generate(state["question"], state["context"], note), "malformed": False}
        except MalformedModelOutputError:
            return {"draft": refusal, "malformed": True}
