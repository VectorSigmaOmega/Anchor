from __future__ import annotations

import logging

from anchor.db.repository import AnchorRepository
from anchor.ingest.chunk import build_chunks
from anchor.ingest.fetch import DocumentFetcher, file_sha256
from anchor.ingest.manifest import active_documents, load_manifest
from anchor.ingest.parse import parse_document
from anchor.logging import log_extra
from anchor.providers.vertex import EmbeddingProvider

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(
        self,
        repository: AnchorRepository,
        fetcher: DocumentFetcher,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.repository = repository
        self.fetcher = fetcher
        self.embedding_provider = embedding_provider

    async def run(self) -> dict[str, int | str]:
        manifest = load_manifest(self.repository.settings)
        run_id = await self.repository.start_ingestion_run()
        docs_seen = 0
        docs_changed = 0
        docs_indexed = 0
        try:
            for document in active_documents(manifest):
                docs_seen += 1
                version = await self.repository.get_document_version(document.doc_id)
                if version and version.sha256 == document.sha256 and version.chunk_count > 0:
                    continue

                path = await self.fetcher.fetch(document)
                if file_sha256(path) != document.sha256:
                    raise ValueError(f"hash mismatch before parse for {document.doc_id}")
                parsed = parse_document(document, path)
                chunks = build_chunks(parsed)
                if file_sha256(path) != document.sha256:
                    raise ValueError(f"hash mismatch before upsert for {document.doc_id}")
                texts = [chunk.text for chunk in chunks]
                embeddings = await self.embedding_provider.embed_documents(texts)
                await self.repository.upsert_document_chunks(document, chunks, embeddings)
                docs_changed += 1
                docs_indexed += 1
                log_extra(
                    logger,
                    logging.INFO,
                    "document_indexed",
                    doc_id=document.doc_id,
                    chunk_count=len(chunks),
                )
            await self.repository.finish_ingestion_run(
                run_id,
                docs_seen=docs_seen,
                docs_changed=docs_changed,
                docs_indexed=docs_indexed,
                status="succeeded",
            )
        except Exception as exc:
            await self.repository.finish_ingestion_run(
                run_id,
                docs_seen=docs_seen,
                docs_changed=docs_changed,
                docs_indexed=docs_indexed,
                status="failed",
                error_message=str(exc),
            )
            raise
        return {
            "run_id": str(run_id),
            "docs_seen": docs_seen,
            "docs_changed": docs_changed,
            "docs_indexed": docs_indexed,
        }
