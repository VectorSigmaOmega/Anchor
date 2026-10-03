# Anchor Deployment Runbook

## Repo-Managed Pieces

- GitHub Actions CI runs lint, backend tests, UI build, fixture smoke eval, and container build.
- The deploy workflow uploads a release bundle to the VPS, installs required host packages, rebuilds the Python virtual environment, builds the static UI, applies DB migrations, installs systemd units, installs nginx TLS config, creates a Let's Encrypt certificate when missing, and restarts services.
- Optional ingestion can be run during manual deployment with the `run_ingest=true` workflow input.

Build and migrate each release in its own directory, then set ownership before
atomically promoting `/opt/anchor/current` and restarting the API. Promoting an
unfinished release can make active requests read inaccessible virtual-environment
files; this caused a transient HTTP 500 while loading TLS certificates during a
live deployment check. Unexpected query failures are persisted as errors so the
assistant message remains retryable rather than being left pending.

## Required External Inputs

These are intentionally not stored in the repository:

- GitHub secrets: `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `ANCHOR_DOMAIN`.
- VPS env file: `/etc/anchor/anchor.env`.
- Provider secrets in `/etc/anchor/anchor.env`: `DATABASE_URL`, `GEMINI_API_KEY`, `COHERE_API_KEY`, optional Langfuse keys.
- TLS certificates: `/etc/letsencrypt/live/$ANCHOR_DOMAIN/fullchain.pem` and `privkey.pem`. The workflow can create these with certbot when port 80 reaches the VPS.
- PostgreSQL with pgvector installed and reachable through `DATABASE_URL`.
- Linux user/group named `anchor` for systemd units.

## Provider checks

Run a small live check after updating billing or provider credentials:

```bash
sudo -u anchor bash -c 'cd /opt/anchor/current && set -a && . /etc/anchor/anchor.env && set +a && .venv/bin/python -m anchor.providers.check'
```

This checks query embeddings, generation, and Cohere reranking. It makes three
small billable API requests, prints no credentials, and exits nonzero if a
provider is unavailable. A Gemini HTTP 402 means the project's prepaid credits
are depleted. The application returns HTTP 503 for provider outages; it does
not classify these failures as corpus refusals. Queries have a 25-second total
time budget (`QUERY_TIMEOUT_SECONDS`), below nginx's 30-second proxy timeout.

Query and retry routes share per-IP limits of 10 requests per minute and 100
requests per UTC day. Daily counts persist in PostgreSQL; minute counts are
held by the single API worker. Rate limits return HTTP 429 and `Retry-After`.
Uvicorn trusts forwarded client addresses only from the loopback nginx proxy.

## Minimum `/etc/anchor/anchor.env`

```bash
DATABASE_URL=postgresql://anchor:anchor@localhost:5432/anchor
ENVIRONMENT=production
GEMINI_API_KEY=...
COHERE_API_KEY=...
GENERATION_MODEL=gemini-3.1-flash-lite
MULTIPART_GENERATION_MODEL=gemini-3.5-flash-lite
GENERATION_THINKING_LEVEL=minimal
EMBEDDING_MODEL=gemini-embedding-2
EMBEDDING_DIMENSION=768
RERANK_MODEL=rerank-v4.0-pro
RATE_LIMIT_RPM=10
RATE_LIMIT_RPD=100
MAX_QUERY_CHARS=4000
MAX_COMPLETION_TOKENS=2048
CORS_ORIGIN=https://your-domain.example
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
```

The Anchor API binds to `127.0.0.1:8010` on the VPS to avoid colliding with other local services.

## Deployment Verification

After deployment:

```bash
curl -fsS https://$ANCHOR_DOMAIN/healthz
curl -fsS https://$ANCHOR_DOMAIN/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"What does the RBI KYC direction require for customer due diligence?"}'
```

Before claiming production readiness:

```bash
python eval/run.py --write-docs
```

The full eval must run against the deployed corpus or an equivalent populated database with real provider credentials.

## Provider selection and embedding migration

GitHub repository variables `GENERATION_PROVIDER`, `EMBEDDING_PROVIDER`,
`GENERATION_MODEL` and `EMBEDDING_MODEL` control deployment and scheduled eval.
Defaults remain Gemini 3.1 Flash-Lite and Gemini Embedding 2. OpenAI requires an
`OPENAI_API_KEY` repository secret. The cost-oriented OpenAI defaults are
`gpt-4.1-mini` and `text-embedding-3-small`. Generation can be switched separately
from embeddings.

When changing embeddings, keep dimension 768 and dispatch deployment with
`run_reembed=true`. Deployment saves a public-corpus backup, embeds the existing
indexed passages in a temporary table, and atomically updates all vectors and
their model profile. A failed batch rolls back the vector changes. Plain
ingestion will not convert unchanged documents to a different embedding model;
runtime profile checks reject that mismatch.

The re-embedding command can also be run directly with the target provider
environment loaded:

```bash
python -m anchor.ingest.reembed
```

Run `python -m scripts.benchmark_answers` against the restored or deployed
corpus to inspect substantive answers. This is distinct from the older
document-lookup golden set and fixture smoke checks.

## Browser cache during releases

HTML and static route payloads use `Cache-Control: no-cache` so navigation
revalidates them. Hashed `/_next/` files retain their asset cache and are copied
without deleting previous hashes. This keeps already-open pages and previously
cached HTML functional during and after deployment.
