import asyncio

from anchor.pipeline.workflow import (
    UNRESOLVED_DISCLOSURE_RE,
    AnswerReview,
    EvidenceReview,
    MultipartWorkflow,
    append_unresolved_comparisons,
    missing_proposal_values,
    soften_discretionary_claims,
)
from anchor.schemas import ModelCitation, ModelQueryResponse, RetrievedChunk


def chunk(text="Banks shall identify customers before opening accounts."):
    return RetrievedChunk(chunk_id="c1", doc_id="kyc", doc_title="KYC Direction", regulator="RBI",
                          section_path="CDD", page=1, text=text, source_url="https://example.invalid")


def answer(text, quote=None):
    return ModelQueryResponse(status="answered", answer=text + " [1]",
                              citations=[ModelCitation(chunk_id="c1", quote=quote or chunk().text)])


class Steps:
    def __init__(self, *, gap=False, invalid=False, issues=()):
        self.gap = gap
        self.invalid = invalid
        self.issues = list(issues)
        self.searches = []
        self.notes = []
        self.verifications = 0
        self.coverage_calls = 0
        self.review_inputs = []

    async def plan(self, question):
        return ["Identify customers", "Account-opening duties"]

    async def retrieve(self, questions, seeds):
        self.searches.append((questions, seeds))
        return [chunk()], [chunk()]

    async def coverage(self, question, requirements, context):
        self.coverage_calls += 1
        return EvidenceReview(missing_searches=["Target missing rule"] if self.gap else [], limitations=[], findings=[])

    async def generate(self, question, context, note):
        self.notes.append(note)
        return answer("Identification is mandatory", "Fabricated quote" if self.invalid else None)

    async def verify(self, question, requirements, draft, context, findings, differences):
        self.verifications += 1
        self.review_inputs.append((findings, differences))
        return AnswerReview(issues=self.issues.pop(0) if self.issues else [])

    def workflow(self):
        return MultipartWorkflow(plan=self.plan, retrieve=self.retrieve, coverage=self.coverage, generate=self.generate,
                                 verify=self.verify, max_citations=24)


async def test_coverage_gap_triggers_only_one_targeted_retrieval_with_existing_context():
    steps = Steps(gap=True)
    result = await steps.workflow().run("What are the duties?")
    assert result["verified"]
    assert len(steps.searches) == 2
    assert steps.searches[1] == (["Target missing rule"], [chunk()])
    assert steps.coverage_calls == 2
    assert len(steps.notes) == 1


async def test_claim_support_failure_repairs_then_verifies_again():
    steps = Steps(issues=[["Draft reverses a mandatory obligation."], []])
    result = await steps.workflow().run("What are the duties?")
    assert result["verified"] and result["repaired"]
    assert steps.verifications == 2
    assert len(steps.notes) == 2
    assert "mandatory obligation" in steps.notes[1]


async def test_persistent_claim_failure_stops_after_one_repair():
    steps = Steps(issues=[["Unsupported amount"], ["Unsupported amount"]])
    result = await steps.workflow().run("What are the duties?")
    assert not result["verified"]
    assert len(steps.notes) == 2
    assert steps.verifications == 2


def test_modal_softening_changes_only_the_disputed_claim():
    text = "The ordinary rate applies. A flat penalty is levied [1]."
    issue = "Preserve the source's discretion instead of stating an automatic outcome: A flat penalty is levied [1]."
    assert soften_discretionary_claims(text, [issue]) == "The ordinary rate applies. A flat penalty may be levied [1]."
    assert soften_discretionary_claims(text, [issue, "Unsupported amount"]) is None


def test_unresolved_fallback_adds_both_server_held_citations():
    first = chunk("Clients may pay fees in advance for one year.")
    second = first.model_copy(update={"chunk_id": "c2", "text": "Clients may pay fees in advance for one quarter."})
    draft = ModelQueryResponse(status="answered", answer="An advance fee is possible [1].",
                               citations=[ModelCitation(chunk_id="c1", quote=first.text)])
    revised = append_unresolved_comparisons(draft, ["Unresolved source comparison: periods differ [E1] [E2]"],
                                             [first, second], 24)
    assert revised is not None
    assert "does not establish which provision controls" in revised.answer
    assert "one year" in revised.answer and "one quarter" in revised.answer
    assert "[1] Compared with:" in revised.answer and "[2]. The available material" in revised.answer
    assert len(revised.citations) == 2


async def test_persistent_modal_error_gets_one_checked_source_strength_fallback():
    class ModalSteps(Steps):
        async def generate(self, question, context, note):
            self.notes.append(note)
            return answer("A flat penalty is levied")

        async def verify(self, question, requirements, draft, context, findings, differences):
            self.verifications += 1
            return AnswerReview(issues=[] if "may be levied" in draft.answer else [
                "Preserve the source's discretion instead of stating an automatic outcome: "
                "A flat penalty is levied [1]",
            ])

    steps = ModalSteps()
    result = await steps.workflow().run("What may happen?")
    assert result["verified"]
    assert "may be levied" in result["draft"].answer
    assert steps.verifications == 3
    assert len(steps.notes) == 2


async def test_invalid_quotes_cannot_pass_semantic_verification():
    steps = Steps(invalid=True)
    result = await steps.workflow().run("What are the duties?")
    assert not result["verified"]
    assert len(steps.notes) == 2
    assert steps.verifications == 0


async def test_concurrent_requests_do_not_share_graph_state():
    steps = Steps()
    workflow = steps.workflow()
    a, b = await asyncio.gather(workflow.run("Question A"), workflow.run("Question B"))
    assert a["question"] == "Question A"
    assert b["question"] == "Question B"


async def test_malformed_claim_review_cannot_publish_unverified_draft():
    from anchor.providers.gemini import MalformedModelOutputError

    class MalformedReview(Steps):
        async def verify(self, *args):
            raise MalformedModelOutputError("Invalid review")

    steps = MalformedReview()
    result = await steps.workflow().run("What are the duties?")
    assert not result["verified"]
    assert len(steps.notes) == 2


async def test_repair_discards_preliminary_ledger_that_may_contain_the_error():
    class FaultyLedger(Steps):
        async def coverage(self, *args):
            return EvidenceReview(missing_searches=[], limitations=[], findings=["Unchecked ledger summary"])

    steps = FaultyLedger(issues=[["Incorrect rule strength"], []])
    result = await steps.workflow().run("What are the duties?")
    assert result["verified"]
    assert "Unchecked ledger summary" in steps.notes[0]
    assert "Unchecked ledger summary" not in steps.notes[1]


async def test_draft_and_verifier_receive_source_findings_and_differences():
    class ComparedEvidence(Steps):
        async def coverage(self, *args):
            return EvidenceReview(missing_searches=[], limitations=[],
                                  findings=["A signed declaration is required [E1]"],
                                  differences=["Two periods need comparison [E1] [E2]"])

    steps = ComparedEvidence()
    result = await steps.workflow().run("What is required?")
    assert result["verified"]
    assert "signed declaration" in steps.notes[0]
    assert "Two periods" in steps.notes[0]
    assert steps.review_inputs == [(["A signed declaration is required [E1]"],
                                   ["Two periods need comparison [E1] [E2]"])]


async def test_unresolved_source_difference_requires_explicit_disclosure_before_verification():
    class DifferingRules(Steps):
        async def coverage(self, *args):
            return EvidenceReview(missing_searches=[], limitations=[], findings=[],
                                  differences=["Unresolved source comparison: two periods differ [E1] [E2]"])

    steps = DifferingRules()
    result = await steps.workflow().run("What is the advance period?")
    assert not result["verified"]
    assert steps.verifications == 0
    assert "unresolved comparison" in steps.notes[1]


def test_unresolved_disclosure_accepts_plural_source_wording():
    assert UNRESOLVED_DISCLOSURE_RE.search("The supplied excerpts do not establish which provision controls.")


async def test_repair_receives_proposal_and_unresolved_difference_issues_together():
    class DifferingRules(Steps):
        async def coverage(self, *args):
            return EvidenceReview(missing_searches=[], limitations=[], findings=[],
                                  differences=["Unresolved source comparison: two periods differ [E1] [E2]"])

    steps = DifferingRules()
    await steps.workflow().run("The firm proposes Rs 18,000. What is the advance period?")
    assert len(steps.notes) == 2
    assert "Rs 18,000" in steps.notes[1]
    assert "unresolved comparison" in steps.notes[1]


def test_proposal_check_requires_scenario_values_but_accepts_equivalent_rupee_notation():
    question = ("A firm proposes Rs 160,000 in fees. It wants to collect 18 months in advance "
                "and retain three months on termination. Explain the rules.")
    answer = "The proposed Rs 1.6 lakh fee is above the ceiling; advance collection is limited to one year."
    assert missing_proposal_values(question, answer) == ["18 months", "three months"]


async def test_missing_proposal_values_trigger_repair_before_expensive_model_review():
    steps = Steps()
    result = await steps.workflow().run("A firm proposes Rs 18,000 in fees. What is the rule?")
    assert not result["verified"]
    assert steps.verifications == 0
    assert len(steps.notes) == 2
    assert "Rs 18,000" in steps.notes[1]
