from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from anchor.config import Settings
from anchor.db.pool import Database
from anchor.schemas import ChunkRecord, DocumentRecord, RetrievedChunk


def to_pgvector(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


@dataclass(slots=True)
class DocumentVersion:
    sha256: str
    is_active: bool
    chunk_count: int


class AnchorRepository:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    async def healthcheck(self) -> bool:
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT 1")
            row = await cur.fetchone()
            return bool(row)

    async def start_ingestion_run(self) -> UUID:
        run_id = uuid4()
        async with self.db.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO ingestion_runs (
                        run_id, started_at, status
                    ) VALUES (%s, %s, 'running')
                    """,
                    (run_id, datetime.now(UTC)),
                )
            await conn.commit()
        return run_id

    async def finish_ingestion_run(
        self,
        run_id: UUID,
        *,
        docs_seen: int,
        docs_changed: int,
        docs_indexed: int,
        status: str,
        error_message: str | None = None,
    ) -> None:
        async with self.db.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE ingestion_runs
                    SET ended_at = %s,
                        docs_seen = %s,
                        docs_changed = %s,
                        docs_indexed = %s,
                        status = %s,
                        error_message = %s
                    WHERE run_id = %s
                    """,
                    (
                        datetime.now(UTC),
                        docs_seen,
                        docs_changed,
                        docs_indexed,
                        status,
                        error_message,
                        run_id,
                    ),
                )
            await conn.commit()

    async def get_document_version(self, doc_id: str) -> DocumentVersion | None:
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                    SELECT d.sha256, d.is_active, COUNT(c.chunk_id) AS chunk_count
                    FROM documents d
                    LEFT JOIN chunks c ON c.doc_id = d.doc_id
                    WHERE d.doc_id = %s
                    GROUP BY d.sha256, d.is_active
                    """,
                (doc_id,),
            )
            row = await cur.fetchone()
            if not row:
                return None
            return DocumentVersion(
                sha256=row["sha256"],
                is_active=row["is_active"],
                chunk_count=row["chunk_count"],
            )

    async def upsert_document_chunks(
        self,
        document: DocumentRecord,
        chunks: list[ChunkRecord],
        embeddings: list[list[float]],
    ) -> None:
        async with self.db.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO documents (
                        doc_id, title, regulator, doc_type, source_url,
                        published_at, snapshot_date, sha256, is_active,
                        version_label, topic_family, notes, updated_at
                    ) VALUES (
                        %(doc_id)s, %(title)s, %(regulator)s, %(doc_type)s, %(source_url)s,
                        %(published_at)s, %(snapshot_date)s, %(sha256)s, %(active)s,
                        %(version_label)s, %(topic_family)s, %(notes)s, NOW()
                    )
                    ON CONFLICT (doc_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        regulator = EXCLUDED.regulator,
                        doc_type = EXCLUDED.doc_type,
                        source_url = EXCLUDED.source_url,
                        published_at = EXCLUDED.published_at,
                        snapshot_date = EXCLUDED.snapshot_date,
                        sha256 = EXCLUDED.sha256,
                        is_active = EXCLUDED.is_active,
                        version_label = EXCLUDED.version_label,
                        topic_family = EXCLUDED.topic_family,
                        notes = EXCLUDED.notes,
                        updated_at = NOW()
                    """,
                    document.model_dump(),
                )
                await cur.execute("DELETE FROM chunks WHERE doc_id = %s", (document.doc_id,))
                for chunk, embedding in zip(chunks, embeddings, strict=True):
                    await cur.execute(
                        """
                        INSERT INTO chunks (
                            chunk_id, doc_id, chunk_index, section_path, page,
                            text, text_tsv, embedding, content_sha256
                        ) VALUES (
                            %s, %s, %s, %s, %s,
                            %s, to_tsvector('english', %s), %s::vector, %s
                        )
                        """,
                        (
                            chunk.chunk_id,
                            chunk.doc_id,
                            chunk.chunk_index,
                            chunk.section_path,
                            chunk.page,
                            chunk.text,
                            chunk.text,
                            to_pgvector(embedding),
                            chunk.content_sha256,
                        ),
                    )
            await conn.commit()

    async def increment_daily_usage(self, ip_hash: str) -> int:
        usage_day = datetime.now(UTC).date()
        async with self.db.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO daily_usage (usage_day, ip_hash, request_count)
                    VALUES (%s, %s, 0)
                    ON CONFLICT (usage_day, ip_hash) DO NOTHING
                    """,
                    (usage_day, ip_hash),
                )
                await cur.execute(
                    """
                    SELECT request_count
                    FROM daily_usage
                    WHERE usage_day = %s AND ip_hash = %s
                    FOR UPDATE
                    """,
                    (usage_day, ip_hash),
                )
                row = await cur.fetchone()
                request_count = int(row["request_count"]) + 1
                await cur.execute(
                    """
                    UPDATE daily_usage
                    SET request_count = %s
                    WHERE usage_day = %s AND ip_hash = %s
                    """,
                    (request_count, usage_day, ip_hash),
                )
            await conn.commit()
        return request_count

    async def lexical_search(self, question: str, limit: int) -> list[RetrievedChunk]:
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                    WITH query AS (
                        SELECT websearch_to_tsquery('english', %s) AS q
                    )
                    SELECT
                        c.chunk_id,
                        c.doc_id,
                        d.title AS doc_title,
                        d.regulator,
                        d.topic_family,
                        c.section_path,
                        c.page,
                        c.text,
                        d.source_url,
                        ts_rank_cd(c.text_tsv, query.q) AS lexical_score
                    FROM chunks c
                    JOIN documents d ON d.doc_id = c.doc_id
                    CROSS JOIN query
                    WHERE d.is_active = TRUE
                      AND c.text_tsv @@ query.q
                    ORDER BY lexical_score DESC, c.doc_id, c.chunk_index
                    LIMIT %s
                    """,
                (question, limit),
            )
            rows = await cur.fetchall()
        return [RetrievedChunk(**row) for row in rows]

    async def dense_search(self, embedding: list[float], limit: int) -> list[RetrievedChunk]:
        vector = to_pgvector(embedding)
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                    SELECT
                        c.chunk_id,
                        c.doc_id,
                        d.title AS doc_title,
                        d.regulator,
                        d.topic_family,
                        c.section_path,
                        c.page,
                        c.text,
                        d.source_url,
                        1 - (c.embedding <=> %s::vector) AS dense_score
                    FROM chunks c
                    JOIN documents d ON d.doc_id = c.doc_id
                    WHERE d.is_active = TRUE
                    ORDER BY c.embedding <=> %s::vector, c.doc_id, c.chunk_index
                    LIMIT %s
                    """,
                (vector, vector, limit),
            )
            rows = await cur.fetchall()
        return [RetrievedChunk(**row) for row in rows]

    async def hash_ip(self, ip_address: str) -> str:
        return sha256(ip_address.encode("utf-8")).hexdigest()
