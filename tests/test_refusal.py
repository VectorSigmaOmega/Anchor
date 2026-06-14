from anchor.config import Settings
from anchor.pipeline.refusal import is_ambiguous_question, refusal_reason_for_context
from anchor.schemas import RetrievedChunk


def settings() -> Settings:
    return Settings.model_validate(
        {
            "database_url": "postgresql://anchor:anchor@localhost:5432/anchor",
            "gemini_api_key": "key",
            "cohere_api_key": "key",
        }
    )


def chunk(score: float, text: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"chunk-{score}",
        doc_id="rbi_kyc_2016",
        doc_title="Master Direction - Know Your Customer (KYC) Direction, 2016",
        regulator="RBI",
        section_path="Master Direction - Know Your Customer (KYC) Direction, 2016 > Customer Due Diligence (CDD) Procedure",
        text=text,
        source_url="https://example.com",
        relevance_score=score,
    )


def test_ambiguous_question_detection() -> None:
    assert is_ambiguous_question("What does this circular require?")
    assert not is_ambiguous_question("What does the RBI KYC direction require for customer due diligence?")


def test_refusal_threshold_not_in_corpus() -> None:
    reason = refusal_reason_for_context(
        "What does the RBI KYC direction require for customer due diligence?",
        [chunk(0.2, "generic text"), chunk(0.18, "generic text")],
        [chunk(0.2, "generic text")],
        settings(),
    )
    assert reason == "not_in_corpus"


def test_refusal_threshold_insufficient_support() -> None:
    reason = refusal_reason_for_context(
        "What does the RBI KYC direction require for customer due diligence?",
        [chunk(0.82, "generic text"), chunk(0.1, "generic text")],
        [chunk(0.82, "generic text")],
        settings(),
    )
    assert reason == "insufficient_support"
