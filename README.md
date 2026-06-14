# Anchor

Anchor is a narrow, production-shaped RAG system over a fixed corpus of official English-language RBI Master Directions and SEBI Master Circulars. It answers only from retrieved context, validates citations server-side, and refuses when support is weak.

## Scope

- Corpus source of truth: [`corpus/manifest.yaml`](corpus/manifest.yaml)
- Public surface: `GET /`, `POST /query`, `GET /healthz`
- Internal endpoints: `GET /readyz`, `GET /metrics`
- Out of scope: tax law, chat memory, uploads, user accounts, workflow engines, vector DBs other than PostgreSQL + pgvector

## Stack

- FastAPI
- PostgreSQL + pgvector
- Gemini Developer API for embeddings and generation
- Cohere Rerank API
- first-party provider adapters
- Langfuse for tracing
- Next.js static export UI
- nginx + systemd deployment artifacts

## Repo Map

- [`anchor/api`](anchor/api) FastAPI app and endpoint wiring
- [`anchor/pipeline`](anchor/pipeline) retrieval, RRF, refusal rules, generation orchestration, citation validation
- [`anchor/ingest`](anchor/ingest) manifest loading, fetch, parse, chunk, embed, upsert
- [`anchor/db`](anchor/db) connection pool, repository SQL, migrations
- [`eval`](eval) golden set, smoke set, eval entrypoint
- [`ui`](ui) static Next.js frontend
- [`deploy`](deploy) Dockerfile, nginx config, systemd units
- [`docs`](docs) PRD, architecture, spec, eval summary, sanitized traces

## Local Setup

1. Create the virtual environment and install dependencies.

```bash
make setup
```

2. Copy `.env.example` to `.env` and fill in:

- `DATABASE_URL`
- `GEMINI_API_KEY`
- `COHERE_API_KEY`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`

3. Start PostgreSQL with pgvector.

```bash
docker compose up -d postgres
```

4. Apply the schema.

```bash
make migrate
```

5. Ingest the allowlisted corpus.

```bash
make ingest
```

6. Run the API.

```bash
make dev
```

7. In another shell, build or run the UI.

```bash
cd ui
npm install
npm run dev
```

## Query Contract

Request:

```json
{
  "question": "What are the KYC requirements for small accounts?"
}
```

Answered response shape:

```json
{
  "request_id": "uuid",
  "status": "answered",
  "answer": "Grounded plain-text answer.",
  "refusal_reason": null,
  "citations": [
    {
      "chunk_id": "rbi_kyc_2016::chunk_000",
      "doc_id": "rbi_kyc_2016",
      "doc_title": "Master Direction - Know Your Customer (KYC) Direction, 2016",
      "regulator": "RBI",
      "section_title": "Customer Due Diligence (CDD) Procedure",
      "page": 14,
      "source_url": "https://www.rbi.org.in/...",
      "quote": "Short supporting excerpt."
    }
  ],
  "disclaimer": "Demo only. Not legal or financial advice.",
  "latency_ms": 1800
}
```

Refusal response shape:

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

## Important Commands

```bash
make setup
make migrate
make ingest
make test
make lint
make eval-smoke
make eval
make ui-build
```

## Evaluation

- Golden set: [`eval/golden.jsonl`](eval/golden.jsonl)
- Smoke subset: [`eval/smoke.jsonl`](eval/smoke.jsonl)
- Latest summary: [`docs/EVAL.md`](docs/EVAL.md)

Smoke eval is fixture-backed so CI can validate the benchmark path without provider credentials:

```bash
./.venv/bin/python eval/run.py --smoke --fixture-mode --write-docs
```

Full eval runs the direct query service against the indexed corpus and requires real provider credentials plus a populated database:

```bash
./.venv/bin/python eval/run.py --write-docs
```

## Deployment Notes

- nginx serves `ui/out` and proxies `/query` and `/healthz`
- systemd units live under [`deploy/systemd`](deploy/systemd)
- nginx config lives at [`deploy/nginx/anchor.conf`](deploy/nginx/anchor.conf)
- Production TLS template lives at [`deploy/nginx/anchor.tls.conf.template`](deploy/nginx/anchor.tls.conf.template)
- Deployment runbook: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
- the GitHub Actions deploy workflow expects a VPS with Python, Node, nginx, PostgreSQL + pgvector, and `/etc/anchor/anchor.env`

## Review Aids

- Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Implementation contract: [`docs/SPEC.md`](docs/SPEC.md)
- Product requirements: [`docs/PRD.md`](docs/PRD.md)
- Sanitized trace snapshot: [`docs/traces/query_trace_sanitized.json`](docs/traces/query_trace_sanitized.json)
