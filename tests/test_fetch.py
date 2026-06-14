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
