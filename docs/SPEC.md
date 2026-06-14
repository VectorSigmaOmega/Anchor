# Anchor - Implementation Spec

This document is the implementation contract for MVP. If `PRD.md` explains *what* Anchor is, this file fixes *how* the service behaves.

## 1. Model Roles

Default model assignments:

- `GENERATION_MODEL=gemini-2.5-flash`
- `EMBEDDING_MODEL=gemini-embedding-2`
- `RERANK_MODEL=rerank-v4.0-pro`
- `EMBEDDING_DIMENSION=768`

Rules:

- defaults must point to stable models only
- the generation default intentionally uses the stable alias `gemini-2.5-flash`
- model ids are environment-configurable
- changing a model id is a config change plus service restart, not a code change

Implementation note:

- Gemini API calls use first-party application adapters backed by developer environment secrets.
- Retrieval SQL, RRF fusion, rerank orchestration, refusal rules, and citation validation remain first-party application code.

## 2. Public API Contract

### `POST /query`

Request:

```json
{
  "question": "What are the KYC requirements for small accounts?"
}
```

Validation rules:

- `question` is required
- trimmed length must be between `1` and `MAX_QUERY_CHARS`
- no additional fields are required in MVP

Success response:

```json
{
  "request_id": "uuid",
  "status": "answered",
  "answer": "Grounded plain-text answer.",
  "refusal_reason": null,
  "citations": [
    {
      "chunk_id": "chunk_001",
      "doc_id": "rbi_kyc_md_2026",
      "doc_title": "Master Direction - Know Your Customer (KYC) Direction, 2016",
      "regulator": "RBI",
      "section_title": "Customer Due Diligence",
      "page": 14,
      "source_url": "https://www.rbi.org.in/...",
      "quote": "Short supporting excerpt."
    }
  ],
  "disclaimer": "Demo only. Not legal or financial advice.",
  "latency_ms": 1800
}
```

Refusal response:

```json
{
  "request_id": "uuid",
  "status": "refused",
  "answer": "",
  "refusal_reason": "insufficient_support",
  "citations": [],
  "disclaimer": "Demo only. Not legal or financial advice.",
  "latency_ms": 900
}
```

Allowed `status` values:

- `answered`
- `refused`

Allowed `refusal_reason` values:

- `not_in_corpus`
- `insufficient_support`
- `ambiguous_question`
- `rate_limited`

### Model Output Contract

The generation model must be asked to return JSON only.

Expected model-side JSON shape before server validation:

```json
{
  "status": "answered",
  "answer": "Grounded plain-text answer.",
  "refusal_reason": null,
  "citations": [
    {
      "chunk_id": "chunk_001"
    }
  ]
}
```

Rules:

- `status` must be either `answered` or `refused`
- `answer` must be plain text, no markdown tables or HTML
- citations returned by the model contain `chunk_id` only
- user-facing citation metadata is hydrated server-side from retrieved chunks
- if `status=refused`, `citations` must be an empty list
- if `status=answered`, `citations` must contain at least one item
- additional properties from the model are ignored

## 3. Retrieval Defaults

MVP defaults are fixed unless evaluation justifies a change:

- lexical candidate count: `30`
- dense candidate count: `30`
- fusion method: `RRF`
- RRF constant: `60`
- rerank candidate pool after dedupe: top `20`
- rerank top subset: `8`
- final generation context: top `5`
- maximum rendered citations in UI: `4`

Search implementation defaults:

- lexical search uses PostgreSQL full-text search over `text_tsv`
- dense search uses cosine distance over pgvector embeddings
- embedding dimensionality is fixed by config and must match the pgvector column definition
- dedupe key is `chunk_id`
- final context order follows rerank order
- each generation prompt includes chunk ids inline so citations can be validated deterministically

## 4. Refusal Policy

Anchor refuses by default when support is weak.

Answer only if all of the following are true:

- at least one chunk directly supports the answer
- final context is topically aligned with the question
- generated citations map to retrieved chunks
- response parses against the output schema

Refuse when any of the following is true:

- retrieval returns no meaningful support
- the question asks for material outside the indexed corpus
- the question is too ambiguous to answer from supplied context
- citation validation fails and no supported answer remains

Partial answers are allowed only when the supported part is cleanly separable and explicitly framed as partial.

### Threshold Rules

MVP refusal thresholds are fixed as follows:

- if no reranked chunk has `relevance_score >= 0.35`, refuse with `not_in_corpus`
- if fewer than `2` reranked chunks have `relevance_score >= 0.20`, refuse with `insufficient_support`
- if the top reranked chunk is from a topically related document family but the selected context does not directly answer the question, refuse with `insufficient_support`
- if the question contains unresolved referents such as "this rule", "that circular", or "latest one" without enough context, refuse with `ambiguous_question`
- if model output cites any `chunk_id` not present in the provided context and a single retry still fails validation, refuse with `insufficient_support`

These thresholds are starting values, not tuning suggestions. Do not change them during MVP implementation unless the evaluation report justifies the change and the spec is updated.

## 5. Corpus Manifest Contract

`corpus/manifest.yaml` is the only source of truth for corpus membership.

Each manifest entry shall contain:

- `doc_id`
- `title`
- `regulator` (`SEBI` or `RBI`)
- `doc_type` (`master_circular` or `master_direction`)
- `source_url`
- `published_at`
- `snapshot_date`
- `sha256`
- `format` (`pdf` or `html`)
- `active` (`true` or `false`)

Recommended additional fields:

- `version_label`
- `topic_family`
- `notes`

### Initial Manifest Requirements

The first implementation pass must ship with a non-empty allowlist.

Minimum initial manifest requirements:

- at least `16` active documents total
- at least `8` RBI Master Directions
- at least `8` SEBI Master Circulars
- one shared `snapshot_date` for the initial corpus release
- every entry must have a verified source URL and SHA-256 hash

The implementation should not block waiting for the "perfect" corpus. Start with the minimum allowlist above and expand only after eval coverage exists.

## 6. Data Model Contract

Minimum tables:

### `documents`

- `doc_id TEXT PRIMARY KEY`
- `title TEXT NOT NULL`
- `regulator TEXT NOT NULL`
- `doc_type TEXT NOT NULL`
- `source_url TEXT NOT NULL`
- `published_at DATE`
- `snapshot_date DATE NOT NULL`
- `sha256 TEXT NOT NULL`
- `is_active BOOLEAN NOT NULL DEFAULT TRUE`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

Constraints:

- `regulator IN ('SEBI', 'RBI')`
- `doc_type IN ('master_circular', 'master_direction')`
- `sha256` must be unique per active document version

### `chunks`

- `chunk_id TEXT PRIMARY KEY`
- `doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE`
- `chunk_index INTEGER NOT NULL`
- `section_path TEXT NOT NULL`
- `page INTEGER`
- `text TEXT NOT NULL`
- `text_tsv TSVECTOR NOT NULL`
- `embedding VECTOR(EMBEDDING_DIMENSION) NOT NULL`
- `content_sha256 TEXT NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

Unique constraint:

- `(doc_id, chunk_index, content_sha256)`

Indexes:

- GIN index on `text_tsv`
- HNSW index on `embedding`
- B-tree index on `(doc_id, chunk_index)`

### `ingestion_runs`

- `run_id UUID PRIMARY KEY`
- `started_at TIMESTAMPTZ NOT NULL`
- `ended_at TIMESTAMPTZ`
- `docs_seen INTEGER NOT NULL DEFAULT 0`
- `docs_changed INTEGER NOT NULL DEFAULT 0`
- `docs_indexed INTEGER NOT NULL DEFAULT 0`
- `status TEXT NOT NULL`
- `error_message TEXT`

Allowed `status` values:

- `running`
- `succeeded`
- `failed`

### `daily_usage`

- `usage_day DATE NOT NULL`
- `ip_hash TEXT NOT NULL`
- `request_count INTEGER NOT NULL DEFAULT 0`
- `PRIMARY KEY (usage_day, ip_hash)`

## 7. Chunking Policy

- target size: `400-500` tokens
- overlap: `75` tokens
- do not cross major heading boundaries unless necessary
- preserve heading path in metadata
- tables should be normalized into deterministic text and chunked separately when useful

## 8. Evaluation Dataset Contract

Each row in `eval/golden.jsonl` shall contain:

- `id`
- `question`
- `expected_outcome` (`answer` or `refusal`)
- `reference_answer`
- `reference_citations`
- `regulator`
- `doc_ids`
- `difficulty`
- `notes`

Dataset composition target:

- `>=100` total rows
- `>=20` refusal rows
- `>=10` ambiguity / edge-case rows

Reference citation rules:

- `reference_citations` must contain `chunk_id` or `(doc_id, section_path)` targets from the indexed corpus
- every answerable row must have at least one verified citation
- every refusal row must have an empty citation list

## 9. Evaluation Policy

### PR CI

- run unit tests
- run integration tests
- run schema and citation-validator tests
- run smoke benchmark on a fixed `15`-question subset

### Full Eval

- run manually or on schedule
- write summary metrics to `docs/EVAL.md`
- compare current implementation against previous tracked results

Primary metrics:

- retrieval Recall@5
- citation validity
- faithfulness / groundedness
- refusal precision
- latency

### CI Pass Criteria

PR smoke eval fails if any of the following are true:

- citation validity < `1.00`
- retrieval Recall@5 < `0.75`
- refusal precision < `0.80`
- more than `1` smoke question returns malformed output

Full eval target thresholds:

- retrieval Recall@5 >= `0.88`
- citation validity = `1.00`
- refusal precision >= `0.90`
- faithfulness / groundedness >= `0.85`

### Smoke Set Composition

The fixed 15-question smoke set shall include:

- `8` answerable lookup questions
- `4` out-of-corpus refusal questions
- `3` ambiguity / edge-case questions

The smoke set must be versioned alongside the golden set and should change rarely.

## 10. Environment Variables

Required for all database-backed commands:

- `DATABASE_URL`

Required for ingestion:

- `GEMINI_API_KEY`
- `EMBEDDING_MODEL`
- `EMBEDDING_DIMENSION`

Required for query API and live eval:

- `GEMINI_API_KEY`
- `GENERATION_MODEL`
- `EMBEDDING_MODEL`
- `EMBEDDING_DIMENSION`
- `COHERE_API_KEY`
- `RERANK_MODEL`
- `RATE_LIMIT_RPM`
- `RATE_LIMIT_RPD`
- `MAX_QUERY_CHARS`

Required for production query API:

- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`

Recommended defaults:

- `RATE_LIMIT_RPM=10`
- `RATE_LIMIT_RPD=100`
- `MAX_QUERY_CHARS=800`
- `EMBEDDING_DIMENSION=768`
- `MAX_COMPLETION_TOKENS=512`

Recommended optional environment variables:

- `GEMINI_API_BASE_URL=https://generativelanguage.googleapis.com/v1beta/models`
- `RERANK_MIN_TOP_SCORE=0.35`
- `RERANK_MIN_SUPPORT_SCORE=0.20`
- `RERANK_MIN_SUPPORT_COUNT=2`
- `FINAL_CONTEXT_TOP_K=5`
- `RERANK_TOP_K=8`

## 11. Public vs Internal Endpoints

Public:

- `GET /`
- `POST /query`
- `GET /healthz`

Internal:

- `GET /readyz`
- `GET /metrics`

## 12. Scope Guardrails

During MVP implementation, do not add:

- tax-law sources
- preview models as defaults
- a dedicated reranker service
- a workflow engine
- chat memory
- user accounts
