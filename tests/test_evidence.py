import pytest

from anchor.pipeline.citations import validate_and_hydrate_citations, verified_quote
from anchor.providers.evidence import hydrate_selected_excerpts, source_excerpts
from anchor.providers.gemini import MalformedModelOutputError
from anchor.schemas import ModelQueryResponse, RetrievedChunk


def chunk(identifier, text):
    return RetrievedChunk(chunk_id=identifier, doc_id=identifier, doc_title=identifier,
                          regulator="SEBI", section_path="Requirements", text=text, source_url="https://example.com")


def test_selected_excerpts_preserve_table_text_and_reference_the_correct_document():
    chunks = [chunk("ia", "IA deposit.\n151 to 300 clients | ₹ 2 lakh"),
              chunk("ra", "RA deposit.\n301 to 1,000 clients | ₹ 5 lakhs")]
    _, evidence = source_excerpts(chunks)
    data = hydrate_selected_excerpts({
        "status": "answered", "answer": "RA: five lakh [E2]. IA: two lakh [E1,E2].",
        "citations": [{"evidence_id": "E2"}, {"evidence_id": "E1"}],
    }, evidence)
    assert data["answer"] == "RA: five lakh [1]. IA: two lakh [2][1]."
    assert data["citations"][0]["chunk_id"] == "ra"
    assert "301 to 1,000 clients | ₹ 5 lakhs" in data["citations"][0]["quote"]
    assert validate_and_hydrate_citations(ModelQueryResponse(**data), chunks, max_rendered=24)[0]


@pytest.mark.parametrize("citations,answer", [
    ([{"evidence_id": "invented"}], "Claim [invented]."),
    ([{"evidence_id": "E1"}], "Claim [E2]."),
    ([{"evidence_id": "E1"}, {"evidence_id": "E1"}], "Claim [E1]."),
])
def test_unknown_unselected_and_duplicate_evidence_is_rejected(citations, answer):
    _, evidence = source_excerpts([chunk("ia", "A valid source passage.")])
    with pytest.raises(MalformedModelOutputError):
        hydrate_selected_excerpts({"status": "answered", "answer": answer, "citations": citations}, evidence)


def test_long_excerpts_remain_contiguous_and_do_not_lose_unbroken_text():
    source = chunk("long", ("A connected condition. " * 100) + ("x" * 2500))
    _, evidence = source_excerpts([source])
    assert len(evidence) > 3
    assert all(verified_quote(e["quote"], source.retrieval_text()) for e in evidence.values())
    assert all(len(e["quote"]) <= 1000 for e in evidence.values())
    assert evidence[list(evidence)[-1]]["quote"].endswith("x" * 100)


def test_distinct_supporting_excerpts_from_one_chunk_can_both_be_cited():
    source = chunk("ia", "The annual ceiling is 151000. The advance limit is one year.")
    response = ModelQueryResponse(status="answered", answer="Two separate requirements [1][2].", citations=[
        {"chunk_id": "ia", "quote": "The annual ceiling is 151000."},
        {"chunk_id": "ia", "quote": "The advance limit is one year."},
    ])
    assert validate_and_hydrate_citations(response, [source], max_rendered=24)[0]
    response.citations[1] = response.citations[0]
    assert not validate_and_hydrate_citations(response, [source], max_rendered=24)[0]


def test_citations_are_constructed_from_first_use_without_a_redundant_model_array():
    _, evidence = source_excerpts([chunk("ia", "IA facts."), chunk("ra", "RA facts.")])
    data = hydrate_selected_excerpts({"status": "answered", "answer": "RA [E2]. IA [E1]. RA again [E2]."}, evidence)
    assert data["answer"] == "RA [1]. IA [2]. RA again [1]."
    assert [c["chunk_id"] for c in data["citations"]] == ["ra", "ia"]
    with pytest.raises(MalformedModelOutputError):
        hydrate_selected_excerpts({"status": "answered", "answer": "Invented [E999]."}, evidence)


@pytest.mark.parametrize("answer", [None, 42, ["A claim"]])
def test_invalid_answer_types_use_the_malformed_output_retry_path(answer):
    with pytest.raises(MalformedModelOutputError):
        hydrate_selected_excerpts({"status": "answered", "answer": answer}, {})
