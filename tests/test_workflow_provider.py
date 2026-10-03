import json

import pytest

from anchor.config import Settings
from anchor.pipeline.workflow import AnswerReview
from anchor.providers.gemini import MalformedModelOutputError
from anchor.providers.workflow import GeminiWorkflowProvider
from anchor.schemas import ModelQueryResponse


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


async def test_coverage_review_rejects_more_than_two_followup_searches(monkeypatch):
    current = provider()

    async def post(path, payload):
        data = {"missing_searches": ["one", "two", "three"], "limitations": [], "findings": []}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(data)}]}}]}

    monkeypatch.setattr(current.client, "post", post)
    with pytest.raises(MalformedModelOutputError, match="coverage review"):
        await current.assess_evidence("Question", ["Part"], [])


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
