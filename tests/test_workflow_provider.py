import json

import pytest

from anchor.config import Settings
from anchor.pipeline.workflow import AnswerReview
from anchor.providers.evidence import source_excerpts
from anchor.providers.gemini import MalformedModelOutputError
from anchor.providers.workflow import (
    GeminiWorkflowProvider,
    explicit_arithmetic_issues,
    focus_review_context,
    requested_answer_parts,
    source_limit_pairs,
)
from anchor.schemas import ModelQueryResponse, RetrievedChunk


def provider():
    return GeminiWorkflowProvider(Settings(_env_file=None, database_url="postgresql://test", gemini_api_key="test"))


def test_explicit_percentage_arithmetic_catches_wrong_amount_and_accepts_equivalent_units():
    assert explicit_arithmetic_issues("The 50% reimbursement on Rs 80 lakh is Rs 50 lakh [1].")
    assert explicit_arithmetic_issues("A 2% charge on Rs 10 crore equals Rs 30 lakh.")
    assert not explicit_arithmetic_issues("The 50% reimbursement on Rs 80 lakh is Rs 40 lakh [1].")
    assert not explicit_arithmetic_issues("A 2% charge on Rs 10 crore equals Rs 20 lakh.")
    assert not explicit_arithmetic_issues("Up to 50% of Rs 80 lakh is eligible, subject to a Rs 50 lakh cap.")


def test_draft_model_can_be_stronger_than_review_model():
    settings = Settings(_env_file=None, database_url="postgresql://test", gemini_api_key="test",
                        multipart_generation_model="gemini-3.5-flash-lite", workflow_draft_model="gemini-3.8-flash")
    current = GeminiWorkflowProvider(settings)
    assert current.model_for_context([]) == "gemini-3.8-flash"


async def test_workflow_uses_configured_retrieval_planner_model(monkeypatch):
    settings = Settings(_env_file=None, database_url="postgresql://test", gemini_api_key="test",
                        generation_model="gemini-3.8-flash", multipart_generation_model="gemini-3.8-flash",
                        retrieval_plan_model="gemini-3.5-flash-lite")
    current = GeminiWorkflowProvider(settings)
    calls = []

    async def post(path, payload):
        calls.append(path)
        return {"candidates": [{"content": {"parts": [{"text": json.dumps({
            "questions": ["Find the first rule", "Find the related condition"]
        })}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    questions = await current.plan_retrieval_questions("Compare the rule and condition")
    assert questions == ["Find the first rule", "Find the related condition"]
    assert calls == ["gemini-3.5-flash-lite:generateContent"]


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


async def test_recorded_source_gap_triggers_one_followup_when_reviewer_omits_search(monkeypatch):
    current = provider()
    calls = []

    async def post(path, payload):
        task = payload["systemInstruction"]["parts"][0]["text"]
        calls.append(task)
        if task.startswith("Decide whether"):
            full_context = json.loads(payload["contents"][0]["parts"][0]["text"])
            assert "amendment changes" in full_context["complete_excerpts"].lower()
            data = {"searches": ["Find the amendment effective date in its footnote"]}
        else:
            data = {"missing_searches": [],
                    "limitations": ["The requested effective date is absent from the supplied excerpts."],
                    "findings": [], "differences": []}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    review = await current.assess_evidence(
        "When does the amendment take effect?", ["Amendment effective date"],
        [review_chunk("amendment", "The amendment changes the applicable limit.", 1)],
    )

    assert review.missing_searches == ["Find the amendment effective date in its footnote"]
    assert len(calls) == 2


async def test_reported_gap_does_not_trigger_followup_when_full_context_covers_it(monkeypatch):
    current = provider()
    chunks = [review_chunk("rta", "The RTA must publish complaints by the seventh day of the next month.", 1),
              review_chunk("rta", "For March, the seventh day of April is the publication deadline.", 2)]
    calls = []

    async def post(path, payload):
        task = payload["systemInstruction"]["parts"][0]["text"]
        calls.append(task)
        if task.startswith("Decide whether"):
            data = {"searches": []}
        else:
            data = {"missing_searches": ["Find the March complaint publication deadline"],
                    "limitations": ["The reviewer did not see the March publication deadline."],
                    "findings": [], "differences": []}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    review = await current.assess_evidence("When must the RTA publish March complaints?",
                                           ["Find the March deadline"], chunks)
    assert review.missing_searches == []
    assert len(calls) == 2


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


async def test_sectioned_answer_treats_user_fact_label_as_provenance_not_source_citation(monkeypatch):
    current = provider()

    async def post(path, payload):
        data = {"status": "answered", "sections": [
            {"part_id": "P1", "answer": "The user proposes Rs 18,000 [User-supplied scenario facts]. The rule applies [E1]."},
            {"part_id": "P2", "answer": "The proposal exceeds the rule [E1]."},
        ]}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    result = await current.generate(question="(1) State the proposal. (2) Assess it.",
                                    context_chunks=[review_chunk("generic", "The maximum is Rs 10,000.", 1)])
    assert "[User-supplied" not in result.answer
    assert "Rs 18,000." in result.answer
    assert len(result.citations) == 1


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
    assert pairs[0][1][0] == 1


def test_differing_limits_in_two_documents_are_comparison_candidates():
    chunks = [review_chunk("original", "Service providers may charge client fees in advance for two months.", 1),
              review_chunk("amendment", "Service providers may charge client fees in advance for four months.", 2)]
    _, evidence = source_excerpts(chunks)
    pairs = source_limit_pairs("Compare service provider advance fee periods", chunks, evidence)
    assert pairs[0][0] == ("E1", "E2")


def test_cross_document_pair_survives_many_same_document_candidates():
    chunks = [review_chunk("first", f"Service providers may charge client fees in advance for {period} months.", index)
              for index, period in enumerate((2, 4, 6, 8), 1)]
    chunks.append(review_chunk("second", "Service providers may charge client fees in advance for 10 months.", 1))
    _, evidence = source_excerpts(chunks)
    pairs = source_limit_pairs("Compare service provider advance fee periods", chunks, evidence)
    by_chunk = {eid: item["chunk_id"] for eid, item in evidence.items()}
    assert any(by_chunk[a].split("-")[0] != by_chunk[b].split("-")[0] for (a, b), _ in pairs)


async def test_cross_document_scope_review_can_reject_a_false_conflict(monkeypatch):
    current = provider()
    chunks = [review_chunk("original", "Advisers may charge client service fees in advance for two months.", 1),
              review_chunk("other", "Researchers may charge client service fees in advance for four months.", 2)]
    calls = []

    async def post(path, payload):
        task = payload["systemInstruction"]["parts"][0]["text"]
        calls.append(task)
        return {"candidates": [{"content": {"parts": [{"text": json.dumps({
            "relationship": "distinct_scope", "explanation": "The limits govern different roles."
        })}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    review = await current.assess_evidence("Compare the rules for both roles",
                                           ["Compare advance client service fees"], chunks,
                                           review_topics=False)
    assert len(calls) == 1
    assert "different documents" in calls[0]
    assert review.differences == []


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


async def test_period_pair_is_compared_when_money_pairs_fill_other_slots(monkeypatch):
    current = provider()
    chunks = [review_chunk("first", "The fixed fee is Rs 100.", 1),
              review_chunk("first", "The fixed fee is Rs 200.", 2),
              review_chunk("second", "Advance fees are limited to one year.", 1),
              review_chunk("second", "Advance fees are limited to one quarter.", 2)]
    pairs = [(('E1', 'E2'), (1, 4, 8, 'rupees')),
             (('E1', 'E3'), (1, 3, 7, 'rupees')),
             (('E3', 'E4'), (1, 2, 6, 'months'))]
    monkeypatch.setattr("anchor.providers.workflow.source_limit_pairs", lambda *args: pairs)
    compared = []

    async def post(path, payload):
        content = json.loads(payload["contents"][0]["parts"][0]["text"])
        kind = content["candidate_quantity_kind"]
        compared.append(kind)
        data = ({"relationship": "unresolved_overlap", "explanation": "One year and one quarter differ."}
                if kind == "months" else
                {"relationship": "compatible", "explanation": "These money excerpts do not establish a conflict."})
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    review = await current.assess_evidence("Compare fixed fees and advance fee periods",
                                           ["Compare both limits"], chunks, review_topics=False)
    assert compared.count("months") == 1
    assert len(compared) == 3
    assert review.differences == ["Unresolved source comparison: One year and one quarter differ. [E3] [E4]"]


async def test_pair_review_sees_supersession_marker_outside_selected_excerpt(monkeypatch):
    current = provider()
    chunks = [review_chunk("ncs", "The current first-time deadline is three working days.", 1),
              review_chunk("ncs", "Prior to its substitution, the clause required five working days.", 2)]
    selected = {"E1": {"chunk_id": chunks[0].chunk_id, "quote": "three working days"},
                "E2": {"chunk_id": chunks[1].chunk_id, "quote": "five working days"}}
    monkeypatch.setattr("anchor.providers.workflow.source_excerpts", lambda unused: ("", selected))
    monkeypatch.setattr("anchor.providers.workflow.source_limit_pairs",
                        lambda *args: [(('E1', 'E2'), (1, 2, 3, 'months'))])

    async def post(path, payload):
        content = json.loads(payload["contents"][0]["parts"][0]["text"])
        assert content["source_b"]["quote"] == "five working days"
        assert "Prior to its substitution" in content["source_b"]["containing_chunk"]
        data = {"relationship": "superseded", "explanation": "Five days is explicitly prior to substitution."}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    review = await current.assess_evidence("Compare first-time notice periods", ["Deadline"], chunks,
                                           review_topics=False)
    assert review.differences == []


async def test_pair_only_review_preserves_source_difference_without_topic_calls(monkeypatch):
    current = provider()
    chunks = [review_chunk("generic", "Clients may pay service fees in advance for two months.", 1),
              review_chunk("generic", "Clients may pay service fees in advance for four months.", 2)]
    calls = []

    async def post(path, payload):
        task = payload["systemInstruction"]["parts"][0]["text"]
        calls.append(task)
        assert task.startswith("Two indexed excerpts")
        data = {"relationship": "unresolved_overlap", "explanation": "Two- and four-month periods differ."}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    review = await current.assess_evidence("Compare advance fees", ["Compare service fee periods"], chunks,
                                           review_topics=False)
    assert len(calls) == 1
    assert review.differences == ["Unresolved source comparison: Two- and four-month periods differ. [E1] [E2]"]


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


async def test_long_answer_checks_every_claim_in_bounded_batches(monkeypatch):
    current = provider()
    source = review_chunk("generic", "Each listed action is permitted when its stated condition holds.", 1)
    _, evidence = source_excerpts([source])
    draft = ModelQueryResponse(status="answered", answer=" ".join(f"Action {i} is permitted [1]." for i in range(13)),
                               citations=[{"chunk_id": source.chunk_id, "quote": evidence["E1"]["quote"]}])
    batch_sizes = []

    async def post(path, payload):
        body = json.loads(payload["contents"][0]["parts"][0]["text"])
        if "claims" not in body:
            data = {"issues": []}
        else:
            batch_sizes.append(len(body["claims"]))
            data = {"coverage_issues": [], "checks": [
                {"claim_id": claim_id, "evidence_ids": ["E1"], "source_wording": "permitted",
                 "source_strength": "discretionary", "claim_strength": "discretionary",
                 "supported": True, "issue": ""} for claim_id in body["claims"]
            ]}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    review = await current.verify_answer("Which actions are permitted?", ["List actions"], draft, [source])
    assert review.issues == []
    assert sorted(batch_sizes) == [1, 12]
    assert len(current.last_review_checks) == 13


async def test_section_numbers_are_not_reviewed_as_factual_claims(monkeypatch):
    current = provider()

    async def post(path, payload):
        claims = json.loads(payload["contents"][0]["parts"][0]["text"])["claims"]
        assert claims == {"C1": "First duty applies.", "C2": "Second duty applies."}
        data = {"coverage_issues": [], "checks": [
            {"claim_id": claim_id, "evidence_ids": [], "source_wording": "A duty applies.",
             "source_strength": "mandatory", "claim_strength": "mandatory", "supported": True, "issue": ""}
            for claim_id in claims
        ]}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    result = await current.verify_answer("What are the duties?", ["First", "Second"], ModelQueryResponse(
        status="answered", answer="1. First duty applies.\n\n2. Second duty applies."), [])
    assert result.issues == []


async def test_discretion_guard_accepts_maximum_eligible_calculation(monkeypatch):
    current = provider()

    async def post(path, payload):
        data = {"coverage_issues": [], "checks": [{"claim_id": "C1", "evidence_ids": [],
                "source_wording": "A reimbursement of up to half the cost may be granted.",
                "source_strength": "discretionary", "claim_strength": "mandatory", "supported": True, "issue": ""}]}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    result = await current.verify_answer("What is the maximum?", ["Maximum"], ModelQueryResponse(
        status="answered", answer="The maximum eligible reimbursement is half the cost."), [])
    assert result.issues == []


async def test_focused_reassessment_can_reverse_a_false_unsupported_judgment(monkeypatch):
    current = provider()
    source = review_chunk("generic", "Up to 100% of eligible expenditure may be reimbursed, subject to a ceiling of Rs 50 lakh.", 1)
    calls = []

    async def post(path, payload):
        task = payload["systemInstruction"]["parts"][0]["text"]
        calls.append(task)
        if task.startswith("Independently reassess"):
            data = {"supported": True, "evidence_ids": ["E1"], "issue": ""}
        elif task.startswith("Check the entire draft"):
            data = {"issues": []}
        else:
            data = {"coverage_issues": [], "checks": [{"claim_id": "C1", "evidence_ids": ["E1"],
                    "source_wording": "Up to 100% subject to a ceiling of Rs 50 lakh.",
                    "source_strength": "discretionary", "claim_strength": "descriptive", "supported": False,
                    "issue": "The ceiling was omitted."}]}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 2}}

    monkeypatch.setattr(current.client, "post", post)
    result = await current.verify_answer("What is the maximum eligible amount?", ["Maximum"], ModelQueryResponse(
        status="answered", answer="The maximum eligible reimbursement is Rs 50 lakh."), [source])
    assert result.issues == []
    assert len(calls) == 3
    assert current.last_review_checks[0]["reassessed_supported"] is True
    assert current.last_usage_metadata["promptTokenCount"] == 30


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


async def test_separate_coverage_can_flag_source_duty_omitted_from_supported_claims(monkeypatch):
    current = provider()
    source = review_chunk("generic", "The firm shall register and provide an undertaking.", 1)

    async def post(path, payload):
        task = payload["systemInstruction"]["parts"][0]["text"]
        if task.startswith("Check the entire draft"):
            data = {"issues": ["The draft omits the required undertaking."]}
        else:
            data = {"coverage_issues": [], "checks": [{"claim_id": "C1", "evidence_ids": ["E1"],
                    "source_wording": "The firm shall register.", "source_strength": "mandatory",
                    "claim_strength": "mandatory", "supported": True, "issue": ""}]}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    result = await current.verify_answer("What must the firm do?", ["Firm duties"], ModelQueryResponse(
        status="answered", answer="The firm shall register [1]."), [source])
    assert result.issues == ["The draft omits the required undertaking."]


async def test_mixed_sentence_reviews_discretion_and_automatic_penalty_separately(monkeypatch):
    current = provider()
    draft = ModelQueryResponse(status="answered", answer=(
        "Ordinary interest may not be charged, but instead a flat penalty of Rs 50,000 is incurred."
    ))
    source = review_chunk("generic", "Ordinary interest may not be charged. A flat penalty of Rs 50,000 may be levied.", 1)

    async def post(path, payload):
        if payload["systemInstruction"]["parts"][0]["text"].startswith("Check the entire draft"):
            data = {"issues": []}
            return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}
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
