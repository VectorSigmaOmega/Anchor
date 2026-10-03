"""Replace corpus embeddings atomically, without fetching or reparsing sources.

Configure the target EMBEDDING_PROVIDER, EMBEDDING_MODEL and API key, then run
`python -m anchor.ingest.reembed`. Existing queries can read the old index until
the final transaction commits. Any provider or validation failure rolls back.
"""

import asyncio
import json

from anchor.config import get_settings
from anchor.db.pool import Database
from anchor.db.repository import to_pgvector
from anchor.providers.factory import build_embedding_provider
from anchor.schemas import RetrievedChunk


async def run() -> None:
    settings = get_settings()
    settings.validate_ingest_runtime()
    provider = build_embedding_provider(settings)
    db = Database(settings)
    await db.open()
    try:
        async with db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT pg_advisory_xact_lock(hashtext('anchor_embedding_maintenance'))")
            await cur.execute("SELECT provider, model, dimension FROM corpus_embedding_profile WHERE singleton = TRUE")
            profile = await cur.fetchone()
            if profile and profile["dimension"] != settings.embedding_dimension:
                raise ValueError(
                    "Re-embedding requires the current vector dimension; changing dimensions needs a separate schema migration"
                )
            await cur.execute(
                """
                SELECT c.chunk_id, c.content_sha256, c.doc_id, d.title AS doc_title,
                       d.regulator, c.section_path, c.page, c.text, d.source_url
                FROM chunks c JOIN documents d ON d.doc_id = c.doc_id
                ORDER BY c.doc_id, c.chunk_index
                """
            )
            rows = await cur.fetchall()
            if not rows:
                raise ValueError("The corpus is empty; run ingestion first")
            # LIKE retains the exact vector type of the existing index.
            await cur.execute("CREATE TEMP TABLE embedding_stage (LIKE chunks INCLUDING DEFAULTS) ON COMMIT DROP")
            batch_size = max(1, settings.embedding_batch_size)
            for start in range(0, len(rows), batch_size):
                batch = rows[start : start + batch_size]
                chunks = [RetrievedChunk.model_validate(row) for row in batch]
                vectors = await provider.embed_documents([chunk.retrieval_text() for chunk in chunks])
                await cur.executemany(
                    """
                    INSERT INTO embedding_stage (chunk_id, doc_id, chunk_index, section_path, text, text_tsv, embedding, content_sha256)
                    VALUES (%s, %s, 0, '', '', ''::tsvector, %s::vector, %s)
                    """,
                    [(row["chunk_id"], row["doc_id"], to_pgvector(vector), row["content_sha256"])
                     for row, vector in zip(batch, vectors, strict=True)],
                )
                print(json.dumps({"embedded": min(start + batch_size, len(rows)), "total": len(rows)}), flush=True)
                if start + batch_size < len(rows) and settings.embedding_batch_pause_seconds > 0:
                    await asyncio.sleep(settings.embedding_batch_pause_seconds)
            # Query transactions lock the profile before reading vectors. Take
            # that lock only for the final swap so readers can use the old
            # index while the provider builds the replacement.
            await cur.execute("SELECT provider, model, dimension FROM corpus_embedding_profile WHERE singleton = TRUE FOR UPDATE")
            if await cur.fetchone() != profile:
                raise ValueError("The embedding profile changed during re-embedding; the old embeddings have been preserved")
            await cur.execute("LOCK TABLE chunks IN SHARE ROW EXCLUSIVE MODE")
            await cur.execute(
                """
                SELECT COUNT(*) AS mismatches FROM chunks c FULL JOIN embedding_stage s ON s.chunk_id = c.chunk_id
                WHERE c.chunk_id IS NULL OR s.chunk_id IS NULL OR c.content_sha256 != s.content_sha256
                """
            )
            if (await cur.fetchone())["mismatches"]:
                raise ValueError("The corpus changed during re-embedding; the old embeddings have been preserved")
            await cur.execute("UPDATE chunks c SET embedding = s.embedding FROM embedding_stage s WHERE c.chunk_id = s.chunk_id")
            await cur.execute(
                """
                INSERT INTO corpus_embedding_profile (singleton, provider, model, dimension)
                VALUES (TRUE, %s, %s, %s) ON CONFLICT (singleton) DO UPDATE
                SET provider = EXCLUDED.provider, model = EXCLUDED.model,
                    dimension = EXCLUDED.dimension, updated_at = NOW()
                """,
                (settings.embedding_provider, settings.embedding_model, settings.embedding_dimension),
            )
            await conn.commit()
            print(json.dumps({"status": "succeeded", "chunks": len(rows), "provider": settings.embedding_provider,
                              "model": settings.embedding_model, "dimension": settings.embedding_dimension}))
    finally:
        await db.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
