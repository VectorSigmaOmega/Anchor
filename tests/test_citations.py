import pytest

from anchor.pipeline.citations import render_quote, validate_and_hydrate_citations, verified_quote
from anchor.schemas import ModelCitation, ModelQueryResponse, RetrievedChunk


def context_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="chunk-001",
        doc_id="rbi_kyc_2016",
        doc_title="Master Direction - Know Your Customer (KYC) Direction, 2016",
        regulator="RBI",
        section_path="Master Direction - Know Your Customer (KYC) Direction, 2016 > Customer Due Diligence (CDD) Procedure",
        page=14,
        text="Banks should perform customer due diligence before opening accounts.",
        source_url="https://example.com",
    )


def test_citation_validation_success() -> None:
    valid, citations = validate_and_hydrate_citations(
        ModelQueryResponse(
            status="answered",
            answer="Banks should perform customer due diligence before opening accounts.",
            refusal_reason=None,
            citations=[ModelCitation(chunk_id="chunk-001", quote=context_chunk().text)],
        ),
        [context_chunk()],
        max_rendered=4,
    )
    assert valid is True
    assert citations[0].doc_id == "rbi_kyc_2016"


def test_citation_validation_rejects_unknown_chunk() -> None:
    valid, citations = validate_and_hydrate_citations(
        ModelQueryResponse(
            status="answered",
            answer="Unsupported answer.",
            refusal_reason=None,
            citations=[ModelCitation(chunk_id="chunk-999", quote="Unsupported answer.")],
        ),
        [context_chunk()],
        max_rendered=4,
    )
    assert valid is False
    assert citations == []


def test_citation_returns_the_supporting_quote_instead_of_the_chunk_prefix() -> None:
    chunk = context_chunk()
    chunk.text = "An unrelated introduction. Banks must verify a new address within two months."
    response = ModelQueryResponse(
        status="answered", answer="Verify the address within two months. [1]",
        citations=[ModelCitation(chunk_id=chunk.chunk_id, quote="Banks must verify a new address within two months.")],
    )

    valid, citations = validate_and_hydrate_citations(response, [chunk], max_rendered=4)

    assert valid
    assert citations[0].quote == "Banks must verify a new address within two months."


@pytest.mark.parametrize("quote", ["Banks may open anonymous accounts.", "Banks should perform identification before opening accounts."])
def test_fabricated_or_paraphrased_quotes_are_rejected(quote: str) -> None:
    response = ModelQueryResponse(
        status="answered", answer="An answer. [1]",
        citations=[ModelCitation(chunk_id="chunk-001", quote=quote)],
    )
    assert validate_and_hydrate_citations(response, [context_chunk()], max_rendered=4) == (False, [])


@pytest.mark.parametrize("answer", ["", "Unsupported marker. [2]", "Unsupported marker. [0]"])
def test_empty_answers_and_unresolved_citation_markers_are_rejected(answer: str) -> None:
    response = ModelQueryResponse(
        status="answered", answer=answer,
        citations=[ModelCitation(chunk_id="chunk-001", quote=context_chunk().text)],
    )
    assert validate_and_hydrate_citations(response, [context_chunk()], max_rendered=4) == (False, [])


def test_every_citation_is_checked_even_after_the_render_limit() -> None:
    response = ModelQueryResponse(
        status="answered", answer="Supported answer. [1]",
        citations=[ModelCitation(chunk_id="chunk-001", quote=context_chunk().text)]
        + [ModelCitation(chunk_id=f"unknown-{i}", quote="Invented.") for i in range(4)],
    )
    assert validate_and_hydrate_citations(response, [context_chunk()], max_rendered=4) == (False, [])


def test_abridged_quote_recovers_the_actual_intervening_source_conditions() -> None:
    first = "Banks must waive collateral up to twenty lakh."
    exception = "The requirement applies from April 2026."
    last = "Banks may extend this waiver to twenty-five lakh."
    source = f"{first} {exception} {last}"
    assert verified_quote(f"{first} ... {last}", source) == source
    assert verified_quote(f"{last} ... {first}", source) is None
    assert verified_quote("Banks ... waive", source) is None
def test_validation_checks_citations_beyond_the_display_limit() -> None:
    response = ModelQueryResponse(status="answered", answer="Supported answer.",
                                  citations=[ModelCitation(chunk_id="chunk-001", quote=context_chunk().text),
                                             ModelCitation(chunk_id="invented", quote="invented")])
    assert validate_and_hydrate_citations(response, [context_chunk()], max_rendered=1) == (False, [])


@pytest.mark.parametrize("answer,reason", [("", None), ("   ", None), ("Supported answer.", "insufficient_support")])
def test_answered_output_cannot_be_empty_or_have_a_refusal_reason(answer, reason) -> None:
    response = ModelQueryResponse(status="answered", answer=answer, refusal_reason=reason,
                                  citations=[ModelCitation(chunk_id="chunk-001", quote=context_chunk().text)])
    assert validate_and_hydrate_citations(response, [context_chunk()], max_rendered=4) == (False, [])


def test_quote_prefers_the_supporting_clause_over_a_long_introduction() -> None:
    text = "General introductory material. " * 20 + "Annual credits must not exceed one lakh. Monthly withdrawals are limited."
    quote = render_quote(text, max_chars=100, focus="Annual credits must not exceed one lakh.")
    assert "Annual credits must not exceed one lakh." in quote
    assert len(quote) <= 100
