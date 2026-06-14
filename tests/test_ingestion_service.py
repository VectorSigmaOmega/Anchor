import asyncio
from datetime import date

from anchor.db.repository import DocumentVersion
from anchor.ingest.service import IngestionService
from anchor.schemas import DocumentRecord, Manifest


def active_doc() -> DocumentRecord:
    return DocumentRecord(
        doc_id="rbi_kyc_2016",
        title="Master Direction - Know Your Customer (KYC) Direction, 2016",
        regulator="RBI",
        doc_type="master_direction",
        source_url="https://www.rbi.org.in/commonman/English/scripts/Notification.aspx?Id=2607",
        published_at=date(2019, 5, 29),
        snapshot_date=date(2026, 5, 2),
        sha256="a" * 64,
        format="html",
        active=True,
    )


class FakeRepository:
    settings = object()

    def __init__(self) -> None:
        self.active_doc_ids: set[str] | None = None

    async def start_ingestion_run(self):
        return "run-id"

    async def deactivate_documents_not_in(self, active_doc_ids: set[str]) -> int:
        self.active_doc_ids = active_doc_ids
        return 2

    async def get_document_version(self, doc_id: str) -> DocumentVersion:
        return DocumentVersion(sha256="a" * 64, is_active=True, chunk_count=1)

    async def finish_ingestion_run(self, *args, **kwargs):
        self.finished = kwargs


class UnusedFetcher:
    pass


class UnusedEmbeddingProvider:
    pass


def test_ingestion_deactivates_docs_outside_active_manifest(monkeypatch) -> None:
    document = active_doc()
    monkeypatch.setattr(
        "anchor.ingest.service.load_manifest",
        lambda settings: Manifest(snapshot_date=document.snapshot_date, documents=[document]),
    )
    repository = FakeRepository()
    service = IngestionService(
        repository=repository,  # type: ignore[arg-type]
        fetcher=UnusedFetcher(),  # type: ignore[arg-type]
        embedding_provider=UnusedEmbeddingProvider(),  # type: ignore[arg-type]
    )

    summary = asyncio.run(service.run())

    assert repository.active_doc_ids == {"rbi_kyc_2016"}
    assert summary["docs_deactivated"] == 2
    assert summary["docs_changed"] == 2
    assert summary["docs_indexed"] == 0
