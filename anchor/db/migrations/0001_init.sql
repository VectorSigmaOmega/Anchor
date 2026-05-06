CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    regulator TEXT NOT NULL CHECK (regulator IN ('SEBI', 'RBI')),
    doc_type TEXT NOT NULL CHECK (doc_type IN ('master_circular', 'master_direction')),
    source_url TEXT NOT NULL,
    published_at DATE,
    snapshot_date DATE NOT NULL,
    sha256 TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    version_label TEXT,
    topic_family TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS documents_active_sha256_idx
    ON documents (sha256)
    WHERE is_active = TRUE;

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    section_path TEXT NOT NULL,
    page INTEGER,
    text TEXT NOT NULL,
    text_tsv TSVECTOR NOT NULL,
    embedding VECTOR({{EMBEDDING_DIMENSION}}) NOT NULL,
    content_sha256 TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (doc_id, chunk_index, content_sha256)
);

CREATE INDEX IF NOT EXISTS chunks_text_tsv_idx
    ON chunks
    USING GIN (text_tsv);

CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON chunks
    USING HNSW (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS chunks_doc_chunk_idx
    ON chunks (doc_id, chunk_index);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id UUID PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    docs_seen INTEGER NOT NULL DEFAULT 0,
    docs_changed INTEGER NOT NULL DEFAULT 0,
    docs_indexed INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS daily_usage (
    usage_day DATE NOT NULL,
    ip_hash TEXT NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (usage_day, ip_hash)
);
