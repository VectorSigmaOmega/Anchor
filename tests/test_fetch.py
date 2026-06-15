from datetime import date
from hashlib import sha256

import httpx
import pytest
import respx

from anchor.config import Settings
from anchor.ingest import fetch
from anchor.ingest.fetch import DocumentFetcher
from anchor.schemas import DocumentRecord


def fetch_doc(digest: str) -> DocumentRecord:
    return DocumentRecord(
        doc_id="sebi_test",
        title="SEBI Test",
        regulator="SEBI",
        doc_type="master_circular",
        source_url="https://www.sebi.gov.in/sebi_data/attachdocs/test.pdf",
        published_at=date(2026, 1, 1),
        snapshot_date=date(2026, 5, 2),
        sha256=digest,
        format="pdf",
        active=True,
    )


@pytest.mark.asyncio
@respx.mock
async def test_fetch_retries_hash_mismatch(tmp_path, monkeypatch) -> None:
    async def no_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(fetch.asyncio, "sleep", no_sleep)
    expected = b"valid pdf bytes"
    digest = sha256(expected).hexdigest()
    route = respx.get("https://www.sebi.gov.in/sebi_data/attachdocs/test.pdf")
    route.side_effect = [
        httpx.Response(200, content=b"incomplete"),
        httpx.Response(200, content=expected),
    ]
    settings = Settings.model_validate(
        {
            "database_url": "postgresql://anchor:anchor@localhost:5432/anchor",
            "raw_corpus_dir": tmp_path,
        }
    )

    path = await DocumentFetcher(settings).fetch(fetch_doc(digest))

    assert path.read_bytes() == expected
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_fetch_hash_mismatch_reports_diagnostics(tmp_path, monkeypatch) -> None:
    async def no_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(fetch.asyncio, "sleep", no_sleep)
    expected_digest = sha256(b"expected").hexdigest()
    actual = b"bad download"
    actual_digest = sha256(actual).hexdigest()
    route = respx.get("https://www.sebi.gov.in/sebi_data/attachdocs/test.pdf").mock(
        return_value=httpx.Response(
            200,
            content=actual,
            headers={"content-type": "application/pdf"},
        )
    )
    settings = Settings.model_validate(
        {
            "database_url": "postgresql://anchor:anchor@localhost:5432/anchor",
            "raw_corpus_dir": tmp_path,
        }
    )

    with pytest.raises(ValueError) as exc_info:
        await DocumentFetcher(settings).fetch(fetch_doc(expected_digest))

    message = str(exc_info.value)
    assert "hash mismatch for sebi_test" in message
    assert f"expected={expected_digest}" in message
    assert f"actual={actual_digest}" in message
    assert "bytes=12" in message
    assert "content_type=application/pdf" in message
    assert "final_url=https://www.sebi.gov.in/sebi_data/attachdocs/test.pdf" in message
    assert route.call_count == 4
