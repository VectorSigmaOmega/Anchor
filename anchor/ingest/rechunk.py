"""Build and atomically install a new chunk index from checksum-verified sources.

Readers continue using the old index until commit. A prepared JSONL bundle can
reuse evaluated vectors; its chunks must exactly match a fresh parse. The deploy
workflow saves a corpus-only pg_dump for rollback before invoking this command.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from pathlib import Path

from anchor.config import get_settings
from anchor.db.pool import Database
from anchor.db.repository import to_pgvector
from anchor.ingest.chunk import CHUNKING_VERSION, build_chunks
from anchor.ingest.fetch import DocumentFetcher, file_sha256
from anchor.ingest.manifest import active_documents, load_manifest
from anchor.ingest.parse import parse_document
from anchor.providers.factory import build_embedding_provider


def checked_bundle(path, settings, documents, chunks):
    records = [json.loads(line) for line in Path(path).read_text().splitlines()]
    expected = {
        "chunking_version": CHUNKING_VERSION,
        "provider": settings.embedding_provider,
        "model": settings.embedding_model,
        "dimension": settings.embedding_dimension,
        "documents": {d.doc_id: d.sha256 for d in documents},
    }
    if not records or records[0] != expected or len(records) != len(chunks) + 1:
        raise ValueError("Prepared index profile, source hashes or chunk count differ")
    vectors = []
    for chunk, row in zip(chunks, records[1:], strict=True):
        vector = row["vector"]
        if row["chunk"] != chunk.model_dump() or len(vector) != settings.embedding_dimension:
            raise ValueError("Prepared index does not match freshly parsed chunks")
        if any(not isinstance(v, (float, int)) or not math.isfinite(v) for v in vector):
            raise ValueError("Prepared index contains invalid vectors")
        if not any(vector):
            raise ValueError("Prepared index contains a zero vector")
        vectors.append(vector)
    return vectors


async def run(prepared_index: Path | None = None) -> None:
    settings = get_settings()
    settings.validate_ingest_runtime()
    documents = active_documents(load_manifest(settings))
    chunks = []
    fetcher = DocumentFetcher(settings)
    for document in documents:
        path = await fetcher.fetch(document)
        if file_sha256(path) != document.sha256:
            raise ValueError(f"Source checksum mismatch: {document.doc_id}")
        parsed = await asyncio.to_thread(parse_document, document, path)
        built = build_chunks(parsed)
        if not built or file_sha256(path) != document.sha256:
            raise ValueError(f"Empty index or changed source: {document.doc_id}")
        chunks.extend(built)
        print(json.dumps({"parsed": document.doc_id, "chunks": len(built)}), flush=True)
    vectors = checked_bundle(prepared_index, settings, documents, chunks) if prepared_index else None
    db = Database(settings)
    await db.open()
    try:
        async with db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT pg_advisory_xact_lock(hashtext('anchor_embedding_maintenance'))")
            await cur.execute("SELECT doc_id, sha256 FROM documents WHERE is_active ORDER BY doc_id")
            snapshot = await cur.fetchall()
            expected = sorted(({"doc_id": d.doc_id, "sha256": d.sha256} for d in documents), key=lambda d: d["doc_id"])
            if snapshot != expected:
                raise ValueError("Rechunk requires the same active source snapshot as the manifest; ingest source changes separately")
            await cur.execute("SELECT provider, model, dimension FROM corpus_embedding_profile WHERE singleton")
            profile = await cur.fetchone()
            if profile != {"provider": settings.embedding_provider, "model": settings.embedding_model,
                           "dimension": settings.embedding_dimension}:
                raise ValueError("Rechunk requires the existing embedding profile; re-embed model changes separately")
            await cur.execute("CREATE TEMP TABLE chunk_stage (LIKE chunks INCLUDING DEFAULTS) ON COMMIT DROP")
            provider = build_embedding_provider(settings) if vectors is None else None
            size = max(1, settings.embedding_batch_size)
            for start in range(0, len(chunks), size):
                batch = chunks[start:start + size]
                embeddings = vectors[start:start + size] if vectors is not None else await provider.embed_documents(
                    [chunk.retrieval_text() for chunk in batch]
                )
                await cur.executemany(
                    """INSERT INTO chunk_stage
                    (chunk_id, doc_id, chunk_index, section_path, page, text, text_tsv, embedding, content_sha256)
                    VALUES (%s,%s,%s,%s,%s,%s,to_tsvector('english',%s),%s::vector,%s)""",
                    [(c.chunk_id, c.doc_id, c.chunk_index, c.section_path, c.page, c.text,
                      c.retrieval_text(), to_pgvector(v), c.content_sha256) for c, v in zip(batch, embeddings, strict=True)],
                )
                print(json.dumps({"staged": min(start + size, len(chunks)), "total": len(chunks)}), flush=True)
                if vectors is None and start + size < len(chunks) and settings.embedding_batch_pause_seconds > 0:
                    await asyncio.sleep(settings.embedding_batch_pause_seconds)
            # Short final lock. Query transactions sharing the profile finish
            # before replacement; subsequent readers see the entire new index.
            await cur.execute("SELECT provider,model,dimension FROM corpus_embedding_profile WHERE singleton FOR UPDATE")
            if await cur.fetchone() != profile:
                raise ValueError("Embedding profile changed; preserving the old index")
            await cur.execute("LOCK TABLE documents, chunks IN SHARE ROW EXCLUSIVE MODE")
            await cur.execute("SELECT doc_id, sha256 FROM documents WHERE is_active ORDER BY doc_id")
            if await cur.fetchall() != snapshot:
                raise ValueError("Source snapshot changed; preserving the old index")
            await cur.execute("DELETE FROM chunks")
            await cur.execute("INSERT INTO chunks SELECT * FROM chunk_stage")
            await cur.execute("UPDATE documents SET chunking_version=%s, updated_at=NOW() WHERE is_active", (CHUNKING_VERSION,))
            await conn.commit()
        print(json.dumps({"status": "succeeded", "documents": len(documents), "chunks": len(chunks),
                          "chunking_version": CHUNKING_VERSION}), flush=True)
    finally:
        await db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared-index", type=Path)
    asyncio.run(run(parser.parse_args().prepared_index))


if __name__ == "__main__":
    main()
