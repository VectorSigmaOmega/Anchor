from scripts.analyze_chunking import evidence_checks


def test_evidence_matching_preserves_regex_quantifiers_and_normalizes_amounts():
    facts = [{"fact": "deposit", "doc_id": "ia", "pattern": r"151 to 300 clients.{0,25}2 lakh"}]
    chunks = [{"chunk_id": "c", "doc_id": "ia", "text": "151 to 300 clients | ₹ 2 lakh"}]
    assert evidence_checks(facts, chunks)[0]["present"]


def test_one_documents_deadline_cannot_substitute_for_another():
    facts = [{"fact": "IAdeadline", "doc_id": "ia", "pattern": "30th April"}]
    chunks = [{"chunk_id": "c", "doc_id": "ra", "text": "latest by 30th April"}]
    assert not evidence_checks(facts, chunks)[0]["present"]
