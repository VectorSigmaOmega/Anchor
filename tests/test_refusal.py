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


def chunk(
    score: float,
    text: str,
    *,
    section_path: str = "Master Direction - Know Your Customer (KYC) Direction, 2016 > Customer Due Diligence (CDD) Procedure",
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"chunk-{score}",
        doc_id="rbi_kyc_2016",
        doc_title="Master Direction - Know Your Customer (KYC) Direction, 2016",
        regulator="RBI",
        section_path=section_path,
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


def test_refusal_uses_current_question_for_ambiguity_detection() -> None:
    contextual_question = "\n".join(
        [
            "Prior conversation (use only to resolve the current question):",
            "Assistant: Research analysts must ensure that the Investor Charter is brought to clients' notice.",
            "",
            "Current question: what is the Investor Charter?",
        ]
    )

    reason = refusal_reason_for_context(
        contextual_question,
        [
            chunk(
                0.92,
                "All research analysts are required to bring the investor charter to the notice of their clients.",
                section_path="Master Circular for Research Analysts > 7. Investor Charter for Research Analysts",
            ),
            chunk(
                0.82,
                "Research Analysts must disclose the Investor Charter on websites and mobile applications.",
                section_path="Master Circular for Research Analysts > 7.2 Investor Charter for Research Analysts",
            ),
        ],
        [
            chunk(
                0.92,
                "All research analysts are required to bring the investor charter to the notice of their clients.",
                section_path="Master Circular for Research Analysts > 7. Investor Charter for Research Analysts",
            )
        ],
        settings(),
        ambiguity_question="what is the Investor Charter?",
    )

    assert reason is None


def test_direct_support_uses_section_heading_text() -> None:
    section_path = (
        "Master Circular for Research Analysts > 5. This Master Circular is issued "
        "in exercise of powers conferred under Section 11(1)"
    )
    reason = refusal_reason_for_context(
        "Master Circular is issued in exercise of powers conferred under which section?",
        [
            chunk(
                0.91,
                "of the Securities and Exchange Board of India Act, 1992.",
                section_path=section_path,
            ),
            chunk(
                0.83,
                "to protect the interests of investors in securities.",
                section_path=section_path,
            ),
        ],
        [
            chunk(
                0.91,
                "of the Securities and Exchange Board of India Act, 1992.",
                section_path=section_path,
            )
        ],
        settings(),
    )

    assert reason is None
