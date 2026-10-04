import json

import pytest

from anchor.config import Settings
from anchor.pipeline.workflow import AnswerReview
from anchor.providers.evidence import source_excerpts
from anchor.providers.gemini import MalformedModelOutputError
from anchor.providers.workflow import GeminiWorkflowProvider, focus_review_context, requested_answer_parts, source_limit_pairs
from anchor.schemas import ModelQueryResponse, RetrievedChunk


def provider():
    return GeminiWorkflowProvider(Settings(_env_file=None, database_url="postgresql://test", gemini_api_key="test"))


async def test_empty_verifier_object_cannot_be_treated_as_pass(monkeypatch):
    current = provider()

    async def post(path, payload):
        return {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    with pytest.raises(MalformedModelOutputError, match="answer review"):
        await current.verify_answer("Question", ["Part"], ModelQueryResponse(status="refused", answer=""), [])


async def test_verification_uses_existing_multipart_model_and_preserves_draft(monkeypatch):
    current = provider()
    calls = []
    draft = ModelQueryResponse(status="answered", answer="A supplied scenario amount.", citations=[])

    async def post(path, payload):
        calls.append((path, payload))
        data = {"coverage_issues": [], "checks": [{"claim_id": "C1", "evidence_ids": [], "source_wording": "",
                                                 "source_strength": "descriptive",
                            "claim_strength": "descriptive", "supported": False, "issue": "Unsupported claim"}]}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    result = await current.verify_answer("Question", ["Part"], draft, [])
    assert result == AnswerReview(issues=["Unsupported claim"])
    path, payload = calls[0]
    assert path == current.settings.multipart_generation_model + ":generateContent"
    assert json.loads(payload["contents"][0]["parts"][0]["text"])["draft"] == draft.model_dump()


async def test_topic_review_rejects_more_than_one_followup_search(monkeypatch):
    current = provider()

    async def post(path, payload):
        data = {"missing_searches": ["one", "two"], "limitations": [], "findings": [], "differences": []}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    with pytest.raises(MalformedModelOutputError, match="topic review"):
        await current.assess_evidence("Question", ["Part"], [])


def review_chunk(doc_id, text, page):
    return RetrievedChunk(chunk_id=f"{doc_id}-{page}", doc_id=doc_id, doc_title=doc_id, regulator="SEBI",
                          section_path="Rules", page=page, text=text, source_url="https://example.invalid")


def test_numbered_user_requests_become_answer_parts():
    question = "A firm proposes Rs 18 lakh. Explain (1) the applicable limit; (2) whether the proposal complies."
    assert requested_answer_parts(question) == ["the applicable limit;", "whether the proposal complies."]


async def test_sectioned_answer_keeps_every_requested_part_and_source_reference(monkeypatch):
    current = provider()

    async def post(path, payload):
        schema = payload["generationConfig"]["responseJsonSchema"]
        assert len(schema["properties"]["sections"]["items"]["properties"]["part_id"]["enum"]) == 2
        data = {"status": "answered", "sections": [
            {"part_id": "P2", "answer": "The proposed action is allowed [E1]."},
            {"part_id": "P1", "answer": "The rule applies to the firm [E1]."},
        ]}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    result = await current.generate(question="(1) Which rule applies? (2) Assess the action.",
                                    context_chunks=[review_chunk("ra", "The rule applies to the firm. The proposed action is allowed.", 1)])
    assert result.answer.startswith("1. The rule applies to the firm [1].\n\n2. The proposed action is allowed [1].")
    assert len(result.citations) == 1


async def test_sectioned_answer_rejects_missing_requested_part(monkeypatch):
    current = provider()

    async def post(path, payload):
        data = {"status": "answered", "sections": [{"part_id": "P1", "answer": "Only one part [E1]."}]}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    with pytest.raises(MalformedModelOutputError, match="sectioned workflow answer"):
        await current.generate(question="(1) First? (2) Second?", context_chunks=[review_chunk("ra", "Some text.", 1)])


def test_topic_selection_keeps_related_provisions_from_both_documents():
    chunks = [review_chunk("ia", f"Unrelated background {index}", index) for index in range(7)]
    chunks += [review_chunk("ia", "Investment advisers may collect advance fees for one year.", 9),
               review_chunk("ra", "Research analysts may collect advance fees for one year.", 13),
               review_chunk("ra", "Research analyst client terms say advance fees one quarter.", 59)]
    selected = focus_review_context("Compare advance fee periods for investment advisers and research analysts", chunks)
    assert {chunk.page for chunk in selected} >= {9, 13, 59}
    assert len(selected) <= 6


async def test_topic_review_discards_nonexistent_source_reference(monkeypatch):
    current = provider()

    async def post(path, payload):
        data = {"missing_searches": [], "limitations": [], "findings": [
            {"statement": "Supported duty", "evidence_ids": ["E1"]},
            {"statement": "Unsupported evidence ID", "evidence_ids": ["E999"]},
        ], "differences": []}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    review = await current.assess_evidence("What is required?", ["Requirements"],
                                           [review_chunk("ra", "A bank must provide a declaration.", 1)])
    assert review.findings == ["Supported duty [E1]"]
    assert review.limitations == ["A source-review finding was discarded because its evidence reference "
                                  "was outside the excerpts supplied for that task."]


async def test_distinct_scopes_do_not_become_unresolved_conflicts(monkeypatch):
    current = provider()

    async def post(path, payload):
        data = {"missing_searches": [], "limitations": [], "findings": [],
                "differences": [
                    {"statement": "Different bank types have different targets", "evidence_ids": ["E1"],
                     "scope_relation": "distinct"},
                    {"statement": "Two provisions give different advance periods", "evidence_ids": ["E1"],
                     "scope_relation": "unclear"},
                ]}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    review = await current.assess_evidence("Compare the rules", ["Compare periods and targets"],
                                           [review_chunk("ra", "Different applicable periods.", 1)])
    assert review.differences == ["Potential source comparison; check whether scope overlaps: "
                                  "Two provisions give different advance periods [E1]"]


def test_similar_actions_with_different_periods_receive_pair_review():
    chunks = [review_chunk("generic", "If agreed, the client may pay service fees in advance for two months.", 1),
              review_chunk("generic", "If agreed, the client may pay service fees in advance for four months.", 2)]
    _, evidence = source_excerpts(chunks)
    pairs = source_limit_pairs("Compare advance service fee periods", chunks, evidence)
    assert pairs[0][0] == ("E1", "E2")


async def test_pair_review_surfaces_unresolved_same_activity_difference(monkeypatch):
    current = provider()
    chunks = [review_chunk("generic", "If agreed, the client may pay service fees in advance for two months.", 1),
              review_chunk("generic", "If agreed, the client may pay service fees in advance for four months.", 2)]
    calls = []

    async def post(path, payload):
        task = payload["systemInstruction"]["parts"][0]["text"]
        if task.startswith("Two indexed excerpts"):
            calls.append("comparison")
            data = {"relationship": "unresolved_overlap", "explanation": "Two-month and four-month limits differ."}
        else:
            calls.append("topic")
            data = {"missing_searches": [], "limitations": [], "findings": [], "differences": []}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    review = await current.assess_evidence("Compare the periods", ["Compare advance service fee periods"], chunks)
    assert calls == ["topic", "comparison"]
    assert review.differences == ["Unresolved source comparison: Two-month and four-month limits differ. [E1] [E2]"]


async def test_every_exact_draft_claim_must_receive_a_check(monkeypatch):
    current = provider()

    async def post(path, payload):
        data = {"coverage_issues": [], "checks": [{"claim_id": "C1", "evidence_ids": [], "source_wording": "Rule",
                "source_strength": "descriptive", "claim_strength": "descriptive", "supported": True, "issue": ""}]}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    draft = ModelQueryResponse(status="answered", answer="First claim. Second claim.")
    with pytest.raises(MalformedModelOutputError, match="answer review"):
        await current.verify_answer("Question", ["Part"], draft, [])


async def test_discretion_mismatch_overrides_verifier_supported_boolean(monkeypatch):
    current = provider()

    async def post(path, payload):
        claims = json.loads(payload["contents"][0]["parts"][0]["text"])["claims"]
        assert claims == {"C1": "A penalty is automatically levied."}
        data = {"coverage_issues": [], "checks": [{"claim_id": "C1", "evidence_ids": [], "source_wording": "A penalty may be levied.",
                "source_strength": "discretionary", "claim_strength": "mandatory", "supported": True, "issue": ""}]}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    result = await current.verify_answer("Question", ["Part"], ModelQueryResponse(
        status="answered", answer="A penalty is automatically levied.",
    ), [])
    assert len(result.issues) == 1
    assert "automatic outcome" in result.issues[0]


async def test_mixed_sentence_reviews_discretion_and_automatic_penalty_separately(monkeypatch):
    current = provider()
    draft = ModelQueryResponse(status="answered", answer=(
        "Ordinary interest may not be charged, but instead a flat penalty of Rs 50,000 is incurred."
    ))
    source = review_chunk("generic", "Ordinary interest may not be charged. A flat penalty of Rs 50,000 may be levied.", 1)

    async def post(path, payload):
        claims = json.loads(payload["contents"][0]["parts"][0]["text"])["claims"]
        assert list(claims) == ["C1", "C2"]
        assert claims["C2"].startswith("but instead a flat penalty")
        data = {"coverage_issues": [], "checks": [
            {"claim_id": "C1", "evidence_ids": ["E1"], "source_wording": "Interest may not be charged.",
             "source_strength": "discretionary", "claim_strength": "discretionary", "supported": True, "issue": ""},
            {"claim_id": "C2", "evidence_ids": ["E1"], "source_wording": "A flat penalty may be levied.",
             "source_strength": "discretionary", "claim_strength": "mandatory", "supported": True, "issue": ""},
        ]}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    result = await current.verify_answer("What may happen?", ["Interest and penalty"], draft, [source])
    assert len(result.issues) == 1
    assert "automatic outcome" in result.issues[0]


async def test_conditional_source_does_not_override_a_supported_claim_with_its_condition(monkeypatch):
    current = provider()

    async def post(path, payload):
        data = {"coverage_issues": [], "checks": [{"claim_id": "C1", "evidence_ids": [],
                "source_wording": "If the amount changes, it shall be updated by April 30.",
                "source_strength": "conditional", "claim_strength": "mandatory", "supported": True, "issue": ""}]}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    result = await current.verify_answer("What happens if it changes?", ["Update deadline"], ModelQueryResponse(
        status="answered", answer="If the amount changes, it must be updated by April 30."), [])
    assert result == AnswerReview(issues=[])
