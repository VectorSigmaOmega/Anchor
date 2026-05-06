from anchor.pipeline.citations import validate_and_hydrate_citations
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
            citations=[ModelCitation(chunk_id="chunk-001")],
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
            citations=[ModelCitation(chunk_id="chunk-999")],
        ),
        [context_chunk()],
        max_rendered=4,
    )
    assert valid is False
    assert citations == []

