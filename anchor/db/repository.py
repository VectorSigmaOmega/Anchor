from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from anchor.config import Settings
from anchor.db.pool import Database
from anchor.schemas import ChatConversation, ChatMessage, ChunkRecord, ConversationTurn, DocumentRecord, QueryResponse, RetrievedChunk
from anchor.services.chat_sessions import chat_title_from_question


def to_pgvector(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


@dataclass(slots=True)
class DocumentVersion:
    sha256: str
    is_active: bool
    chunk_count: int


@dataclass(slots=True)
class ChatQueryStart:
    user_message_id: UUID
    assistant_message_id: UUID
    history: list[ConversationTurn]


@dataclass(slots=True)
class ChatRetryStart:
    question: str
    history: list[ConversationTurn]


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

    async def deactivate_documents_not_in(self, active_doc_ids: set[str]) -> int:
        async with self.db.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE documents
                    SET is_active = FALSE,
                        updated_at = NOW()
                    WHERE is_active = TRUE
                      AND NOT (doc_id = ANY(%s))
                    RETURNING doc_id
                    """,
                    (list(active_doc_ids),),
                )
                rows = await cur.fetchall()
                deactivated_doc_ids = [row["doc_id"] for row in rows]
                if deactivated_doc_ids:
                    await cur.execute(
                        """
                        DELETE FROM chunks
                        WHERE doc_id = ANY(%s)
                        """,
                        (deactivated_doc_ids,),
                    )
            await conn.commit()
        return len(deactivated_doc_ids)

    async def touch_chat_session(self, session_hash: str) -> None:
        async with self.db.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO chat_sessions (session_hash, last_seen_at)
                    VALUES (%s, NOW())
                    ON CONFLICT (session_hash) DO UPDATE SET
                        last_seen_at = NOW()
                    """,
                    (session_hash,),
                )
            await conn.commit()

    async def create_chat_conversation(self, session_hash: str) -> ChatConversation:
        conversation_id = uuid4()
        async with self.db.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO chat_sessions (session_hash, last_seen_at)
                    VALUES (%s, NOW())
                    ON CONFLICT (session_hash) DO UPDATE SET
                        last_seen_at = NOW()
                    """,
                    (session_hash,),
                )
                await cur.execute(
                    """
                    INSERT INTO chat_conversations (
                        conversation_id, session_hash, title, created_at, updated_at
                    ) VALUES (
                        %s, %s, 'New question', NOW(), NOW()
                    )
                    """,
                    (conversation_id, session_hash),
                )
            await conn.commit()
        conversation = await self.get_chat_conversation(session_hash, conversation_id)
        if conversation is None:
            raise RuntimeError("created chat conversation could not be loaded")
        return conversation

    async def list_chat_conversations(
        self,
        session_hash: str,
        *,
        limit: int = 20,
    ) -> list[ChatConversation]:
        await self.touch_chat_session(session_hash)
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                SELECT conversation_id AS id, title, created_at, updated_at
                FROM chat_conversations
                WHERE session_hash = %s
                ORDER BY updated_at DESC, created_at DESC
                LIMIT %s
                """,
                (session_hash, limit),
            )
            conversation_rows = await cur.fetchall()
            if not conversation_rows:
                return []
            conversation_ids = [row["id"] for row in conversation_rows]
            await cur.execute(
                """
                SELECT
                    message_id AS id,
                    conversation_id,
                    role,
                    content,
                    status,
                    response,
                    error,
                    created_at
                FROM chat_messages
                WHERE conversation_id = ANY(%s)
                ORDER BY message_order
                """,
                (conversation_ids,),
            )
            message_rows = await cur.fetchall()
        messages_by_conversation: dict[UUID, list[ChatMessage]] = {conversation_id: [] for conversation_id in conversation_ids}
        for row in message_rows:
            messages_by_conversation[row["conversation_id"]].append(self._chat_message_from_row(row))
        return [
            ChatConversation(
                id=row["id"],
                title=row["title"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                messages=messages_by_conversation[row["id"]],
            )
            for row in conversation_rows
        ]

    async def get_chat_conversation(
        self,
        session_hash: str,
        conversation_id: UUID,
    ) -> ChatConversation | None:
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                SELECT conversation_id AS id, title, created_at, updated_at
                FROM chat_conversations
                WHERE session_hash = %s AND conversation_id = %s
                """,
                (session_hash, conversation_id),
            )
            conversation_row = await cur.fetchone()
            if not conversation_row:
                return None
            await cur.execute(
                """
                SELECT
                    message_id AS id,
                    conversation_id,
                    role,
                    content,
                    status,
                    response,
                    error,
                    created_at
                FROM chat_messages
                WHERE conversation_id = %s
                ORDER BY message_order
                """,
                (conversation_id,),
            )
            message_rows = await cur.fetchall()
        return ChatConversation(
            id=conversation_row["id"],
            title=conversation_row["title"],
            created_at=conversation_row["created_at"],
            updated_at=conversation_row["updated_at"],
            messages=[self._chat_message_from_row(row) for row in message_rows],
        )

    async def delete_chat_conversation(self, session_hash: str, conversation_id: UUID) -> bool:
        async with self.db.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    DELETE FROM chat_conversations
                    WHERE session_hash = %s AND conversation_id = %s
                    RETURNING conversation_id
                    """,
                    (session_hash, conversation_id),
                )
                deleted = await cur.fetchone()
            await conn.commit()
        return deleted is not None

    async def append_chat_query(
        self,
        session_hash: str,
        conversation_id: UUID,
        question: str,
        *,
        user_message_id: UUID | None = None,
        assistant_message_id: UUID | None = None,
    ) -> ChatQueryStart | None:
        user_id = user_message_id or uuid4()
        assistant_id = assistant_message_id or uuid4()
        async with self.db.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT conversation_id
                    FROM chat_conversations
                    WHERE session_hash = %s AND conversation_id = %s
                    FOR UPDATE
                    """,
                    (session_hash, conversation_id),
                )
                if not await cur.fetchone():
                    return None
                await cur.execute(
                    """
                    SELECT role, content, status, response, message_order
                    FROM chat_messages
                    WHERE conversation_id = %s
                    ORDER BY message_order
                    """,
                    (conversation_id,),
                )
                prior_message_rows = await cur.fetchall()
                history = self._api_history_from_rows(prior_message_rows)
                now = datetime.now(UTC)
                await cur.execute(
                    """
                    INSERT INTO chat_messages (
                        message_id, conversation_id, role, content, status, created_at
                    ) VALUES (
                        %s, %s, 'user', %s, 'complete', %s
                    )
                    """,
                    (user_id, conversation_id, question, now),
                )
                await cur.execute(
                    """
                    INSERT INTO chat_messages (
                        message_id, conversation_id, role, content, status, created_at
                    ) VALUES (
                        %s, %s, 'assistant', '', 'pending', %s
                    )
                    """,
                    (assistant_id, conversation_id, now),
                )
                title = (
                    chat_title_from_question(question)
                    if not any(row["role"] == "user" for row in prior_message_rows)
                    else None
                )
                if title is None:
                    await cur.execute(
                        """
                        UPDATE chat_conversations
                        SET updated_at = %s
                        WHERE conversation_id = %s
                        """,
                        (now, conversation_id),
                    )
                else:
                    await cur.execute(
                        """
                        UPDATE chat_conversations
                        SET title = %s,
                            updated_at = %s
                        WHERE conversation_id = %s
                        """,
                        (title, now, conversation_id),
                    )
            await conn.commit()
        return ChatQueryStart(
            user_message_id=user_id,
            assistant_message_id=assistant_id,
            history=history,
        )

    async def prepare_chat_retry(
        self,
        session_hash: str,
        conversation_id: UUID,
        assistant_message_id: UUID,
    ) -> ChatRetryStart | None:
        async with self.db.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT m.message_order
                    FROM chat_messages m
                    JOIN chat_conversations c ON c.conversation_id = m.conversation_id
                    WHERE c.session_hash = %s
                      AND m.conversation_id = %s
                      AND m.message_id = %s
                      AND m.role = 'assistant'
                      AND m.status IN ('error', 'stopped')
                    FOR UPDATE OF m
                    """,
                    (session_hash, conversation_id, assistant_message_id),
                )
                assistant_row = await cur.fetchone()
                if not assistant_row:
                    return None
                await cur.execute(
                    """
                    SELECT message_order, content
                    FROM chat_messages
                    WHERE conversation_id = %s
                      AND role = 'user'
                      AND message_order < %s
                    ORDER BY message_order DESC
                    LIMIT 1
                    """,
                    (conversation_id, assistant_row["message_order"]),
                )
                user_row = await cur.fetchone()
                if not user_row:
                    return None
                await cur.execute(
                    """
                    SELECT role, content, status, response, message_order
                    FROM chat_messages
                    WHERE conversation_id = %s
                      AND message_order < %s
                    ORDER BY message_order
                    """,
                    (conversation_id, user_row["message_order"]),
                )
                prior_message_rows = await cur.fetchall()
                history = self._api_history_from_rows(prior_message_rows)
                now = datetime.now(UTC)
                await cur.execute(
                    """
                    UPDATE chat_messages
                    SET content = '',
                        status = 'pending',
                        response = NULL,
                        error = NULL,
                        created_at = %s
                    WHERE message_id = %s
                    """,
                    (now, assistant_message_id),
                )
                await cur.execute(
                    """
                    UPDATE chat_conversations
                    SET updated_at = %s
                    WHERE conversation_id = %s
                    """,
                    (now, conversation_id),
                )
            await conn.commit()
        return ChatRetryStart(question=user_row["content"], history=history)

    async def complete_chat_assistant_message(
        self,
        conversation_id: UUID,
        assistant_message_id: UUID,
        *,
        content: str,
        response: QueryResponse,
    ) -> None:
        async with self.db.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE chat_messages
                    SET content = %s,
                        status = 'complete',
                        response = %s,
                        error = NULL
                    WHERE conversation_id = %s AND message_id = %s
                    """,
                    (
                        content,
                        Jsonb(response.model_dump(mode="json")),
                        conversation_id,
                        assistant_message_id,
                    ),
                )
                await cur.execute(
                    """
                    UPDATE chat_conversations
                    SET updated_at = NOW()
                    WHERE conversation_id = %s
                    """,
                    (conversation_id,),
                )
            await conn.commit()

    async def fail_chat_assistant_message(
        self,
        conversation_id: UUID,
        assistant_message_id: UUID,
        *,
        error: str,
    ) -> None:
        async with self.db.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE chat_messages
                    SET status = 'error',
                        error = %s
                    WHERE conversation_id = %s AND message_id = %s
                    """,
                    (error, conversation_id, assistant_message_id),
                )
                await cur.execute(
                    """
                    UPDATE chat_conversations
                    SET updated_at = NOW()
                    WHERE conversation_id = %s
                    """,
                    (conversation_id,),
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

    @staticmethod
    def _chat_message_from_row(row: dict) -> ChatMessage:
        return ChatMessage(
            id=row["id"],
            role=row["role"],
            content=row["content"],
            created_at=row["created_at"],
            status=row["status"],
            response=row["response"],
            error=row["error"],
        )

    @staticmethod
    def _api_history_from_rows(rows: list[dict]) -> list[ConversationTurn]:
        history: list[ConversationTurn] = []
        for row in rows:
            if row["role"] == "user" and row["status"] == "complete":
                history.append(ConversationTurn(role="user", content=row["content"]))
            elif row["role"] == "assistant" and row["status"] == "complete":
                response = row["response"]
                if isinstance(response, dict) and response.get("status") == "answered" and row["content"]:
                    history.append(ConversationTurn(role="assistant", content=row["content"]))
        return history[-6:]
