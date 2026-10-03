import asyncio
import os
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from anchor.config import Settings
from anchor.ingest import reembed

TEST_DATABASE_URL = os.getenv("ANCHOR_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="requires a dedicated PostgreSQL/pgvector test database")
OLD_VECTOR = "[" + ",".join(["1"] + ["0"] * 767) + "]"
NEW_VECTOR = "[" + ",".join(["0", "1"] + ["0"] * 766) + "]"


@pytest.fixture
def corpus(monkeypatch):
    assert conninfo_to_dict(TEST_DATABASE_URL)["dbname"].endswith("_test"), "Use a dedicated *_test database"
    with psycopg.connect(TEST_DATABASE_URL) as conn, conn.cursor() as cur:
        for path in sorted(Path("anchor/db/migrations").glob("*.sql")):
            cur.execute(path.read_text().replace("{{EMBEDDING_DIMENSION}}", "768"))
        cur.execute("TRUNCATE documents CASCADE")
        cur.execute("DELETE FROM corpus_embedding_profile")
        cur.execute(
            """INSERT INTO documents (doc_id,title,regulator,doc_type,source_url,snapshot_date,sha256)
               VALUES ('fixture','Fixture','RBI','master_direction','https://example.invalid',CURRENT_DATE,'hash')"""
        )
        for index in range(2):
            cur.execute(
                """INSERT INTO chunks (chunk_id,doc_id,chunk_index,section_path,text,text_tsv,embedding,content_sha256)
                   VALUES (%s,'fixture',%s,'Scope','Source text','source'::tsvector,%s::vector,'hash')""",
                (str(index), index, OLD_VECTOR),
            )
        cur.execute("INSERT INTO corpus_embedding_profile (provider,model,dimension) VALUES ('gemini','gemini-embedding-2',768)")
    settings = Settings(
        _env_file=None, database_url=TEST_DATABASE_URL, embedding_provider="openai", openai_api_key="test-key",
        embedding_dimension=768, embedding_batch_size=1, embedding_batch_pause_seconds=0,
    )
    monkeypatch.setattr(reembed, "get_settings", lambda: settings)
    yield
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        conn.execute("TRUNCATE documents CASCADE")
        conn.execute("DELETE FROM corpus_embedding_profile")


class FakeEmbeddings:
    def __init__(self, *, fail: bool = False):
        self.calls = 0
        self.fail = fail

    async def embed_documents(self, texts):
        self.calls += 1
        if self.fail and self.calls == 2:
            raise RuntimeError("simulated provider outage")
        return [[0.0, 1.0] + [0.0] * 766 for _ in texts]


async def test_failed_batch_preserves_every_vector_and_profile(corpus, monkeypatch):
    monkeypatch.setattr(reembed, "build_embedding_provider", lambda settings: FakeEmbeddings(fail=True))
    with pytest.raises(RuntimeError, match="provider outage"):
        await reembed.run()
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        assert conn.execute("SELECT embedding::text FROM chunks").fetchall() == [(OLD_VECTOR,), (OLD_VECTOR,)]
        assert conn.execute("SELECT provider,model FROM corpus_embedding_profile").fetchone() == ("gemini", "gemini-embedding-2")


async def test_successful_migration_replaces_every_vector_and_profile(corpus, monkeypatch):
    monkeypatch.setattr(reembed, "build_embedding_provider", lambda settings: FakeEmbeddings())
    await reembed.run()
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        assert conn.execute("SELECT embedding::text FROM chunks").fetchall() == [(NEW_VECTOR,), (NEW_VECTOR,)]
        assert conn.execute("SELECT provider,model FROM corpus_embedding_profile").fetchone() == ("openai", "text-embedding-3-small")


async def test_queries_can_read_old_index_while_replacement_is_generated(corpus, monkeypatch):
    generating = asyncio.Event()
    continue_generation = asyncio.Event()

    class PausedEmbeddings(FakeEmbeddings):
        async def embed_documents(self, texts):
            generating.set()
            await continue_generation.wait()
            return await super().embed_documents(texts)

    monkeypatch.setattr(reembed, "build_embedding_provider", lambda settings: PausedEmbeddings())
    migration = asyncio.create_task(reembed.run())
    try:
        await asyncio.wait_for(generating.wait(), timeout=5)
        async with await psycopg.AsyncConnection.connect(TEST_DATABASE_URL, options="-c statement_timeout=1000") as conn:
            cursor = await conn.execute("SELECT provider, model FROM corpus_embedding_profile FOR SHARE")
            assert await cursor.fetchone() == ("gemini", "gemini-embedding-2")
            cursor = await conn.execute("SELECT embedding::text FROM chunks")
            assert await cursor.fetchall() == [(OLD_VECTOR,), (OLD_VECTOR,)]
    finally:
        continue_generation.set()
        await migration
