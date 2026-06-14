# Anchor - Architecture

## 1. Architectural Pattern

Anchor is a **small monolith**:

- one FastAPI service for online queries
- one ingestion CLI for offline indexing
- one PostgreSQL instance with `pgvector`
- one static frontend

Managed services are used only where they clearly reduce solo-maintainer burden:

- Gemini Developer API for generation and embeddings
- Cohere Rerank API for hosted reranking
- Langfuse Cloud for private tracing

Gemini API calls are implemented as thin first-party HTTP adapters so provider behavior remains easy to inspect.

Everything else stays local and simple. This is intentional. Anchor is a production-grade portfolio project, not an excuse to assemble extra infrastructure.

## 2. Component Diagram

```
                    ┌──────────────────────────────┐
                    │      Browser (Next.js UI)    │
                    └──────────────┬───────────────┘
                                   │ HTTPS
                                   ▼
                    ┌──────────────────────────────┐
                    │     nginx (TLS + limits)     │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │      FastAPI: anchor-api     │
                    │  lexical ─┐                  │
                    │           ├─> fuse -> gen    │
                    │  dense  ──┘                  │
                    └───────┬──────────┬───────────┘
                            │          │
                    ┌───────▼───┐  ┌──▼───────────┐
                    │Postgres + │  │ Langfuse     │
                    │ pgvector  │  │ Cloud        │
                    └───────────┘  └──────────────┘

   Offline:
   ┌───────────────────────────────────────────────┐
   │ anchor-ingest CLI                             │
   │ fetch -> parse -> chunk -> embed -> upsert    │
   └───────────────────────────────────────────────┘
```

## 3. Components

### 3.1 anchor-api (FastAPI)

- public endpoints: `POST /query`, `GET /healthz`
- internal endpoints: `GET /readyz`, `GET /metrics`
- in-process query pipeline
- structured response validation using Pydantic models
- structured JSON logs to stdout
- one Langfuse trace per request

### 3.2 Query Pipeline

The online path is a straight-through function pipeline:

1. validate and normalize request
2. run lexical search in PostgreSQL
3. run dense vector search in PostgreSQL
4. fuse with RRF
5. rerank the fused candidate set
6. select final context window
7. call Gemini generation model
8. validate citations and response shape
9. return answered or refused response

No LangGraph or agent framework is used. The workflow is still linear enough that a simple pipeline is the right choice.

Provider adapters, retrieval SQL, RRF fusion, rerank wiring, and refusal decisions stay in application code.

### 3.3 anchor-ingest (CLI)

- reads `corpus/manifest.yaml`
- fetches official source files
- verifies content hashes
- parses PDFs and HTML
- chunks into heading-aware spans
- embeds with Gemini API `gemini-embedding-2`
- upserts into PostgreSQL
- records an ingestion run summary

Primary parsing choices:

- PDF: `PyMuPDF`
- HTML normalization: `BeautifulSoup`

### 3.4 PostgreSQL plus pgvector

PostgreSQL holds operational data and the search corpus:

- `documents`
- `chunks`
- `ingestion_runs`
- `daily_usage`

Indexes:

- GIN index for lexical search over `tsvector`
- HNSW index on embedding vectors

The database is the single retrieval system for MVP. No separate vector database is introduced.

### 3.5 anchor-ui

- static Next.js export served by nginx
- one page with query input, answer panel, refusal state, and citation list
- no client-side API keys
- no auth flows

### 3.6 Gemini Developer API

Used for:

- embeddings via `gemini-embedding-2`
- answer generation via `gemini-2.5-flash`

Only stable model defaults are allowed in production config.

### 3.7 Cohere Rerank API

Used for:

- reranking the fused retrieval candidate set
- returning a relevance-ordered top subset for generation

MVP usage remains intentionally narrow:

- rerank only the fused top candidates, not the entire corpus
- keep rerank input size small and fixed

### 3.8 Langfuse Cloud

- private trace storage for requests
- spans for request validation, lexical search, dense search, fusion, rerank, generation, and response validation
- request metadata attached for eval and debugging

Public reviewers do not get live access by default. Sanitized trace snapshots are exported into `docs/traces/`.

### 3.9 Eval Harness

- `eval/golden.jsonl` stores the benchmark dataset; generated seed rows must be reviewed before production claims
- `eval/run.py` runs the full benchmark
- smoke eval runs in CI on PRs
- full eval runs manually or on schedule
- `docs/EVAL.md` stores the tracked headline results

## 4. Data Flow

### 4.1 Ingestion Flow

1. CLI reads `corpus/manifest.yaml`
2. Fetches or reuses allowlisted source files
3. Verifies content hash
4. Parses the document into normalized text blocks
5. Builds heading-aware chunks with overlap
6. Calls `gemini-embedding-2`
7. Upserts documents and chunks into PostgreSQL
8. Records an ingestion summary

### 4.2 Query Flow

1. Browser sends `POST /query`
2. nginx enforces request limits and forwards to FastAPI
3. FastAPI validates the request and starts a trace
4. Lexical and dense searches run concurrently
5. RRF fuses both ranked lists
6. Cohere reranks the fused candidate set
7. Top context chunks are selected
8. `gemini-2.5-flash` generates structured output from only the selected context
9. Citation validator confirms every citation maps to a provided chunk
10. Response is returned to the browser

## 5. Technology Choices

| Layer | Choice | Rationale |
|---|---|---|
| API framework | FastAPI | typed, small, reliable |
| LLM app library | first-party Gemini API adapter | keeps provider calls inspectable and avoids cloud service-account setup |
| Generation model | Gemini API `gemini-2.5-flash` | stable managed model, good price/performance |
| Embeddings | Gemini API `gemini-embedding-2` | current Google embedding model |
| Reranking | Cohere Rerank API | hosted reranking without operating a separate service |
| Retrieval store | PostgreSQL + pgvector | one DB for lexical and dense retrieval |
| Retrieval strategy | BM25 + dense + RRF + rerank | production-style hybrid retrieval with stronger final ranking |
| Observability | Langfuse Cloud | purpose-built LLM tracing with low ops burden |
| Frontend | Next.js static export | simple deployment, familiar toolchain |
| Reverse proxy | nginx | TLS, rate limiting, static asset serving |
| Hosting | single 4 GB VPS | enough for this workload and cheap to run |

## 6. Deployment Topology

A single VPS hosts:

- nginx
- anchor-api under `systemd`
- PostgreSQL with `pgvector`
- static frontend bundle

Secrets live in `/etc/anchor/anchor.env`.

CI/CD:

- on every PR: lint, unit tests, smoke eval, container build
- on merge to `main`: upload release bundle, rebuild the venv/static UI on the VPS, migrate, optionally ingest, and restart services
- full benchmark runs via workflow dispatch or schedule

## 7. Failure Modes and Responses

| Failure | Detection | Response |
|---|---|---|
| Gemini generation timeout | per-call timeout | return 504; tag trace; retry malformed output only |
| Embedding call fails during ingestion | CLI error | document is not committed; re-run remains idempotent |
| Dense search fails | query exception | fallback to lexical-only retrieval; tag trace |
| Rerank API fails | API error or timeout | fallback to fused pre-rerank ordering; tag trace |
| PostgreSQL unreachable | `/readyz` fails | serve 503 for query traffic |
| Unsupported or out-of-corpus question | refusal rules | return refusal response |
| Invalid structured model output | response parser fails | one retry, then refusal with trace tag |
| Invalid citation mapping | citation validator fails | refuse rather than return unsupported content |
| Daily per-IP cap hit | usage counter | return 429 |

## 8. Security and Public Surface

- HTTPS only
- public endpoints limited to `/`, `/query`, and `/healthz`
- `/readyz` and `/metrics` are internal-only
- query length capped
- rate limiting per IP
- daily usage cap per IP
- CORS restricted to the deployed UI origin
- PostgreSQL bound to localhost only
- secrets never stored in repo
- public traces are sanitized exports, not live dashboards

## 9. Observability

- Langfuse trace per request
- structured JSON logs
- internal `/metrics` endpoint for request count, refusal rate, latency, and citation validation failures
- benchmark reports written to `docs/EVAL.md`
- trace snapshots committed under `docs/traces/` when useful for review

## 10. Build and Operate

```
make dev         # local stack
make ingest      # run anchor-ingest against corpus/manifest.yaml
make eval-smoke  # small benchmark subset
make eval        # full golden-set evaluation
make test        # unit + integration tests
make deploy      # build and restart production
```

## 11. Repository Layout

```
anchor/
  anchor/
    api/
    pipeline/
    ingest/
    eval/
  ui/
  corpus/
    manifest.yaml
    raw/
  eval/
    golden.jsonl
    run.py
  deploy/
    docker/
    nginx/
    systemd/
  docs/
    PRD.md
    ARCHITECTURE.md
    SPEC.md
    EVAL.md
    traces/
  .github/workflows/
    ci.yml
    deploy.yml
    eval.yml
  Makefile
  README.md
```

## 12. Why This Is Production-Grade Enough

Anchor should communicate the following clearly:

- the corpus is narrow and authoritative
- the retrieval stack is hybrid and measurable
- refusal is an intentional product behavior, not an afterthought
- the deployment is real but intentionally small
- observability exists without turning the project into a platform
- the architecture respects solo-maintainer reality
