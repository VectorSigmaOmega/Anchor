# Anchor Deployment Runbook

## Repo-Managed Pieces

- GitHub Actions CI runs lint, backend tests, UI build, fixture smoke eval, and container build.
- The deploy workflow uploads a release bundle to the VPS, installs required host packages, rebuilds the Python virtual environment, builds the static UI, applies DB migrations, installs systemd units, installs nginx TLS config, creates a Let's Encrypt certificate when missing, and restarts services.
- Optional ingestion can be run during manual deployment with the `run_ingest=true` workflow input.

## Required External Inputs

These are intentionally not stored in the repository:

- GitHub secrets: `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `ANCHOR_DOMAIN`.
- VPS env file: `/etc/anchor/anchor.env`.
- Provider secrets in `/etc/anchor/anchor.env`: `DATABASE_URL`, `GEMINI_API_KEY`, `COHERE_API_KEY`, optional Langfuse keys.
- TLS certificates: `/etc/letsencrypt/live/$ANCHOR_DOMAIN/fullchain.pem` and `privkey.pem`. The workflow can create these with certbot when port 80 reaches the VPS.
- PostgreSQL with pgvector installed and reachable through `DATABASE_URL`.
- Linux user/group named `anchor` for systemd units.

## Minimum `/etc/anchor/anchor.env`

```bash
DATABASE_URL=postgresql://anchor:anchor@localhost:5432/anchor
ENVIRONMENT=production
GEMINI_API_KEY=...
COHERE_API_KEY=...
GENERATION_MODEL=gemini-2.5-flash
EMBEDDING_MODEL=gemini-embedding-2
EMBEDDING_DIMENSION=768
RERANK_MODEL=rerank-v4.0-pro
RATE_LIMIT_RPM=10
RATE_LIMIT_RPD=100
MAX_QUERY_CHARS=800
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
