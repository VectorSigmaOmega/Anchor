import asyncio

from anchor.pipeline.workflow import AnswerReview, EvidenceReview, MultipartWorkflow
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

    async def plan(self, question):
        return ["Identify customers", "Account-opening duties"]

    async def retrieve(self, questions, seeds):
        self.searches.append((questions, seeds))
        return [chunk()], [chunk()]

    async def coverage(self, question, requirements, context):
        return EvidenceReview(missing_searches=["Target missing rule"] if self.gap else [], limitations=[], findings=[])

    async def generate(self, question, context, note):
        self.notes.append(note)
        return answer("Identification is mandatory", "Fabricated quote" if self.invalid else None)

    async def verify(self, question, requirements, draft, context):
        self.verifications += 1
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
