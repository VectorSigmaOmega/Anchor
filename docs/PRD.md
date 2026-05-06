# Anchor - Product Requirements Document

## 1. Overview

Anchor is a citation-grounded retrieval system over a fixed corpus of Indian financial regulations. MVP scope is limited to official English-language **SEBI Master Circulars** and **RBI Master Directions**. It accepts natural-language questions and returns either:

- a grounded answer backed by exact citations to the indexed corpus, or
- a refusal when the corpus does not support an answer

This is a **production-grade portfolio project**, not a product business. The goal is to show professional AI engineering judgment without building an oversized system for a solo developer. The stack should look disciplined, measurable, and deployable, but remain small enough to build and operate alone.

## 2. Primary Goal

Produce a single repository plus a public live demo that shows, within a 10-minute review:

- hybrid retrieval over real regulatory documents, not naive semantic search
- grounded answer generation with citation validation and refusal
- evaluation discipline on a versioned golden set
- production-style observability, logging, and deployment
- a simple stack that is clearly intentional rather than over-engineered

Secondary goal: signal backend competence through the ingestion pipeline, FastAPI service, PostgreSQL plus pgvector data model, and reproducible deployment.

Recognizable tooling is welcome where it genuinely improves implementation clarity or reduces boilerplate, but the core retrieval and refusal logic should remain easy to inspect in first-party code.

## 3. Personas

| Persona | Time spent | Needs |
|---|---|---|
| Recruiter / engineering manager | 60-600 s | clear README, live URL, example questions, evaluation headline, clean architecture |
| Senior AI engineer / interviewer | 10-30 min | retrieval design, refusal policy, trace examples, eval methodology, failure modes |

## 4. Goals (Measurable)

| ID | Goal |
|---|---|
| G1 | Public demo URL reachable >=99% of the calendar month. |
| G2 | Faithfulness / groundedness >=0.85 on the full golden set. |
| G3 | Retrieval Recall@5 >=0.88 on answerable questions in the golden set. |
| G4 | 100% of answered responses display at least one valid citation in the UI. |
| G5 | Refusal precision >=0.90 on the out-of-corpus subset. |
| G6 | Every request produces a trace, structured logs, and request metadata that can be inspected during review. |
| G7 | A reviewer can understand the system and verify one successful query path in under 10 minutes. |

## 5. Product Principles

- narrow scope beats broad scope
- official sources only
- stable managed models only; no preview models in production
- one service, one database, one ingestion CLI
- use recognizable tooling only where it reduces boilerplate or improves clarity
- evaluation and refusal matter more than clever prompting
- public demo should be simple to use and simple to operate

## 6. Non-Goals

The following are explicitly out of scope:

- tax laws or Income Tax Act content
- multilingual queries
- multi-turn chat memory
- user accounts, saved sessions, or history
- document upload by end users
- self-hosted LLM or embedding inference
- self-hosted reranker service
- public programmatic API keys
- mobile apps
- legal or financial advice

## 7. Functional Requirements

### FR1 - Corpus

The system shall ingest a **fixed curated corpus** defined only by `corpus/manifest.yaml`.

MVP corpus rules:

- sources are restricted to official SEBI and RBI domains
- only official English-language SEBI Master Circulars and RBI Master Directions are allowed
- live search corpus contains only the current allowlisted documents in the manifest
- superseded or dropped documents may be archived on disk, but are not searchable in MVP
- the manifest records a corpus snapshot date and document hashes

Target corpus size for MVP:

- 20 to 30 total documents
- at least 8 SEBI documents
- at least 8 RBI documents

### FR2 - Ingestion Pipeline

The ingestion pipeline shall:

- fetch documents listed in `corpus/manifest.yaml`
- verify hashes before parse and before upsert
- extract text, headings, and tables from official source files
- chunk documents into bounded sections with overlap
- attach metadata to each chunk
- generate embeddings with Vertex AI `gemini-embedding-2`
- upsert documents, chunks, and embeddings into PostgreSQL plus pgvector

Re-ingestion shall be idempotent. Unchanged documents must be skipped.

### FR3 - Retrieval

The retriever shall:

- run lexical search and dense vector search in parallel
- fuse both result sets with Reciprocal Rank Fusion (RRF)
- rerank the fused candidate set with a hosted reranking API
- deduplicate by chunk id
- select a final context window from the fused ranking
- return chunk metadata sufficient for citation rendering

MVP retrieval is intentionally simple:

- hosted reranking is allowed, but no self-hosted reranker service
- no query rewriting
- no multi-hop agent workflow

### FR4 - Generation

The generator shall:

- use Vertex AI `gemini-2.5-flash` as the default generation model
- accept the user query and selected context chunks
- return structured output conforming to the API contract in `docs/SPEC.md`
- answer only from supplied context
- refuse when support is insufficient
- never return a citation that does not map to a retrieved chunk

### FR5 - Evaluation

The repository shall contain:

- `eval/golden.jsonl` with >=100 reviewed questions
- an out-of-corpus refusal subset with >=20 questions
- a smoke evaluation runnable in CI on pull requests
- a full evaluation runnable manually or on schedule
- a results summary published to `docs/EVAL.md`

### FR6 - Observability

The system shall:

- emit one trace per request to Langfuse Cloud
- record token counts, latency, model ids, refusal reason, and retrieval metadata
- emit structured JSON logs
- expose internal health and metrics endpoints for operations
- publish sanitized trace snapshots under `docs/traces/` for portfolio review

### FR7 - Public Surface

The public deployment shall expose:

- a single-page web UI
- `POST /query`
- `GET /healthz`

The public deployment shall **not** expose:

- ingestion endpoints
- admin endpoints
- a public live observability dashboard

### FR8 - Safety and Abuse Controls

The system shall:

- rate-limit per IP
- enforce a daily per-IP query cap
- cap query length
- cap context size and completion size
- display a visible disclaimer that the system is a demo and not legal or financial advice

## 8. Non-Functional Requirements

| ID | Requirement | Target |
|---|---|---|
| NFR1 | Demo URL availability | >=99% monthly |
| NFR2 | Monthly hosting cost | <= INR 500 |
| NFR3 | p95 end-to-end latency for a typical query | <= 3.5 s |
| NFR4 | Public surface area | only the UI, `/query`, and `/healthz` |
| NFR5 | Secrets storage | no secrets in repo; environment only |
| NFR6 | Reproducibility | rebuildable from a bare VPS in <=45 minutes |
| NFR7 | Cold-start ingestion | full corpus indexed in <=20 minutes |
| NFR8 | Solo maintainer operability | one person can redeploy or re-ingest using documented steps |

## 9. Success Criteria

The project is considered successful if a reviewer can, within 10 minutes:

1. understand the system from the README
2. reach the live demo and ask a question that returns a cited answer or a correct refusal
3. inspect one sanitized trace snapshot and see retrieval plus generation steps
4. find benchmark results in `docs/EVAL.md`
5. understand the stack from the architecture document without extra explanation

## 10. Definition of Done (MVP)

MVP is complete when all of the following are true:

- corpus scope is frozen to SEBI plus RBI in `corpus/manifest.yaml`
- ingestion is idempotent and indexes the allowlisted corpus into PostgreSQL plus pgvector
- `POST /query` returns a structured answered or refused response
- UI renders clickable citations to source chunks
- citation validation is enforced server-side
- rate limiting and daily per-IP limits are active
- Langfuse traces and structured logs are emitted for every request
- golden set with >=100 questions exists in `eval/golden.jsonl`
- smoke eval runs in CI on every PR
- full eval runs via workflow dispatch or schedule and updates `docs/EVAL.md`
- `docs/ARCHITECTURE.md` and `docs/SPEC.md` match the implementation contract
- GitHub Actions runs lint, unit tests, smoke eval, and container build
- public demo is reachable over HTTPS with a valid certificate

If any of the above is missing, the MVP is not done.

## 11. Frozen Decisions

The following decisions are resolved for MVP and should not be reopened during implementation:

- domain: SEBI Master Circulars plus RBI Master Directions only
- generation provider: Vertex AI
- generation model: `gemini-2.5-flash`
- embedding provider: Vertex AI
- embedding model: `gemini-embedding-2`
- reranking provider: Cohere Rerank API
- observability provider: Langfuse Cloud for private traces, exported snapshots for public review
- retrieval strategy: BM25 plus dense plus RRF plus hosted reranking
- deployment shape: monolith API plus PostgreSQL plus static UI on one VPS

Model ids remain environment-configurable, but default values must point to stable models only.

## 12. Deferred Backlog

Items deliberately deferred until after MVP:

- tax-law expansion
- metadata filtering UI
- self-hosted reranker service
- multilingual support
- streaming token output
- public API access
- prompt management UI
- automatic corpus refresh workflows exposed to users

If any deferred item is built, it must not regress citation validity, refusal quality, or deployment simplicity.
