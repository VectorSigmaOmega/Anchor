"""Prepare isolated experimental indexes and resumable embedding caches."""

import argparse
import asyncio
import json
import os
from collections import Counter
from hashlib import sha256
from pathlib import Path
from statistics import median
from urllib.parse import urlparse

from psycopg import connect, sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from anchor.config import Settings
from anchor.db.migrate import MIGRATIONS_DIR
from anchor.db.pool import Database
from anchor.db.repository import AnchorRepository
from anchor.ingest.manifest import active_documents, load_manifest
from anchor.providers.gemini import GeminiEmbeddingProvider
from anchor.schemas import ChunkRecord
from scripts.chunking_variants import build_variant, parse_layout

ROOT = Path(os.environ.get("CHUNKING_ARTIFACT_DIR", ".benchmarks/chunking"))


def experiment_settings(base: Settings, strategy: str) -> Settings:
    if strategy not in {"fixed", "structured"}:
        raise ValueError(strategy)
    details = conninfo_to_dict(base.database_url)
    if details.get("host") not in {"127.0.0.1", "localhost"}:
        raise ValueError("Chunking experiments require a loopback database")
    details["dbname"] = "anchor_chunking_" + strategy
    return base.model_copy(update={"database_url": make_conninfo(**details)})


def provision(base: Settings, strategy: str) -> Settings:
    current = experiment_settings(base, strategy)
    name = conninfo_to_dict(current.database_url)["dbname"]
    with connect(base.database_url, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    with connect(current.database_url, autocommit=True) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT NOW())")
        applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name not in applied:
                conn.execute(path.read_text().replace("{{EMBEDDING_DIMENSION}}", str(current.embedding_dimension)))
                conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,))
    return current


def stats(chunks: list[ChunkRecord]) -> dict:
    sizes = [len(c.text.split()) for c in chunks]
    return {"chunks": len(chunks), "words": sum(sizes), "median_words": median(sizes), "max_words": max(sizes)}


def prepare(base: Settings) -> None:
    documents = active_documents(load_manifest(base))
    variants = {name: [] for name in ["fixed", "structured"]}
    summaries = []
    for document in documents:
        path = ROOT / "raw" / (document.doc_id + ".pdf")
        if sha256(path.read_bytes()).hexdigest() != document.sha256:
            raise ValueError("PDF checksum mismatch: " + document.doc_id)
        parsed_path = ROOT / (document.doc_id + ".parsed.json")
        parsed = parse_layout(document, path)
        parsed_path.write_text(parsed.model_dump_json())
        record = {
            "doc_id": document.doc_id,
            "blocks": len(parsed.blocks),
            "headings": sum(b.block_type == "heading" for b in parsed.blocks),
        }
        for strategy in variants:
            chunks = build_variant(parsed, strategy)
            # Every parsed block word must survive chunk construction. Overlap
            # and repeated table headers can add words but cannot remove any.
            before = Counter(" ".join(b.text for b in parsed.blocks).split())
            after = Counter(" ".join(c.text for c in chunks).split())
            lost = before - after
            if lost or any(len(c.text.split()) > 450 for c in chunks):
                raise ValueError(f"Content/budget failure {strategy}/{document.doc_id}: {lost}")
            variants[strategy].extend(chunks)
            record[strategy] = stats(chunks)
        summaries.append(record)
        print(json.dumps(record), flush=True)
    for strategy, chunks in variants.items():
        (ROOT / (strategy + ".chunks.jsonl")).write_text("".join(c.model_dump_json() + "\n" for c in chunks))
    (ROOT / "chunk-stats.json").write_text(
        json.dumps({"documents": summaries, "totals": {s: stats(c) for s, c in variants.items()}}, indent=2)
    )


async def index(base: Settings, strategy: str) -> None:
    current = provision(base, strategy)
    provider = GeminiEmbeddingProvider(current)
    cache_path = ROOT / "embedding-cache.jsonl"
    cache = {}
    if cache_path.exists():
        cache = {row["key"]: row["vector"] for row in map(json.loads, cache_path.read_text().splitlines())}
    database = Database(current)
    await database.open()
    try:
        repository = AnchorRepository(database, current)
        documents = {d.doc_id: d for d in active_documents(load_manifest(base))}
        all_chunks = [ChunkRecord.model_validate_json(line) for line in (ROOT / (strategy + ".chunks.jsonl")).read_text().splitlines()]
        new_embeddings = 0
        for document in documents.values():
            chunks = [c for c in all_chunks if c.doc_id == document.doc_id]
            texts = [c.retrieval_text() for c in chunks]
            keys = [
                sha256((current.embedding_model + ":" + str(current.embedding_dimension) + ":" + t).encode()).hexdigest() for t in texts
            ]
            missing = list(dict.fromkeys(k for k in keys if k not in cache))
            by_key = dict(zip(keys, texts, strict=True))
            with cache_path.open("a") as output:
                for start in range(0, len(missing), current.embedding_batch_size):
                    batch = missing[start : start + current.embedding_batch_size]
                    vectors = await provider.embed_documents([by_key[k] for k in batch])
                    for key, vector in zip(batch, vectors, strict=True):
                        cache[key] = vector
                        output.write(json.dumps({"key": key, "vector": vector}) + "\n")
                    output.flush()
                    new_embeddings += len(batch)
                    print(json.dumps({"strategy": strategy, "doc": document.doc_id, "embedded": new_embeddings}), flush=True)
                    await asyncio.sleep(0.5)
            await repository.upsert_document_chunks(document, chunks, [cache[k] for k in keys])
        async with database.connection() as conn:
            await conn.execute("ANALYZE chunks")
            await conn.commit()
        print(json.dumps({"strategy": strategy, "chunks": len(all_chunks), "new_embeddings": new_embeddings}), flush=True)
    finally:
        await database.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["prepare", "index"])
    parser.add_argument("--strategy", choices=["fixed", "structured"])
    args = parser.parse_args()
    base = Settings()
    base.langfuse_public_key = ""
    base.langfuse_secret_key = ""
    base.embedding_batch_pause_seconds = 0
    base.gemini_max_retries = 4
    base.gemini_retry_base_seconds = 3
    if urlparse(base.database_url).hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("Local database required")
    ROOT.mkdir(parents=True, exist_ok=True)
    if args.mode == "prepare":
        prepare(base)
    else:
        if not args.strategy:
            parser.error("--strategy required for indexing")
        asyncio.run(index(base, args.strategy))


if __name__ == "__main__":
    main()
