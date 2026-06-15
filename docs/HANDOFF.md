# Anchor Handoff

Last updated: 2026-06-14T20:14:46Z.

## Current Production State

- Domain: `https://anchor.abhinash.dev`.
- VPS SSH alias: `ai-skyserver`.
- Existing non-Anchor deployment must coexist; Anchor API binds to `127.0.0.1:8010`.
- Public health endpoint was verified during deployment: `https://anchor.abhinash.dev/healthz`.
- Nginx proxies Anchor traffic and keeps `/readyz` and `/metrics` restricted to localhost.
- PostgreSQL plus pgvector are provisioned on the VPS.
- Runtime env file is `/etc/anchor/anchor.env`; do not print secrets.

## Active Ingestion Run

- GitHub Actions run: `27509390807`.
- Run URL: `https://github.com/VectorSigmaOmega/Anchor/actions/runs/27509390807`.
- Workflow status at last check: `in_progress`.
- Workflow commit: `589b65df3da5478246fa676e883ddc4330f5e575`.
- Release path: `/opt/anchor/releases/589b65df3da5478246fa676e883ddc4330f5e575-27509390807`.
- VPS process at last check:
  - parent deploy shell PID: `1198614`
  - ingestion process PID: `1199184`
  - command: `.venv/bin/python -m anchor.ingest.cli`
- DB ingestion run at last check:
  - run ID: `523c3945-527c-44ab-803e-c4416645b6af`
  - status: `running`
  - started at: `2026-06-14 19:24:20.20273+00`
  - no error yet
- Current DB corpus at last check was still the old partial state: 8 active documents and 8 chunks. The current ingestion counters update only when the run finishes or fails, so `docs_seen=0` during an active run does not by itself indicate failure.

## What Was Changed For Deployment

- Switched runtime LLM access to Gemini Developer API secrets.
- Added production GitHub Actions SSH deployment.
- Added systemd/nginx deployment assets for Anchor.
- Configured Anchor to coexist with the existing VPS app by using port `8010`.
- Added TLS/nginx config for `anchor.abhinash.dev`.
- Added release directories under `/opt/anchor/releases`.
- Fixed release collisions by using `RELEASE_ID=${{ github.sha }}-${{ github.run_id }}`.
- Added workflow concurrency group `anchor-production-deploy`.
- Increased SSH deploy timeout to `120m`.
- Made Langfuse tracing fail open to avoid query failures from SDK/API mismatch.
- Added roadmap task to replace the wrapper with real Langfuse v4/OpenTelemetry tracing.
- Replaced unstable corpus wrapper URLs with direct RBI/SEBI official PDF URLs.
- Added PDF download streaming/retry and `.part` file handling.
- Fixed PDF table parsing for empty cells.
- Added Gemini embedding batch calls.
- Added conservative Gemini embedding pacing/backoff after observed `429` responses.
- Added roadmap tasks for Gemini 3 Flash, Gemini 429 diagnostics, and manual SEBI corpus verification.

## Known Issues And Caveats

- Production is not signed off until full corpus ingestion succeeds and live `/query` is verified.
- The active ingestion run may be slow because it is conservatively paced around Gemini embedding `429` responses.
- The user checked AI Studio and reported `gemini-embedding-2` was not near RPM or input TPM limits. Treat this as unresolved. The next code change should capture sanitized Gemini 429 response bodies and relevant response headers.
- Current generation model is `gemini-3-flash-preview`; promote to the stable Gemini 3 Flash model ID when Google publishes one for the Developer API.
- Current embedding model is `gemini-embedding-2`.
- Current Langfuse integration is fail-open/no-op if the installed SDK does not support the assumed `.trace()` API.
- `npm ci` reported frontend vulnerabilities during deploy: 1 moderate and 1 high. Not yet remediated.
- GitHub Actions warned Node.js 20 actions are deprecated. Not blocking today, but workflow actions should be reviewed.
- SHA-256 manifest hashes are project-pinned snapshot checksums computed from downloaded official PDFs. They catch bad/partial/changed downloads; they are not regulator cryptographic signatures.

## Resume Commands

Check the active workflow:

```bash
gh run view 27509390807 --repo VectorSigmaOmega/Anchor --json status,conclusion,url,createdAt,headSha
```

Check whether ingestion is still running on the VPS:

```bash
ssh ai-skyserver 'ps -eo pid,ppid,etime,pcpu,pmem,state,args | grep -E "anchor.ingest|python -m anchor" | grep -v grep || true'
```

Check latest ingestion rows and corpus counts:

```bash
ssh ai-skyserver 'set -euo pipefail
set -a
. /etc/anchor/anchor.env
set +a
psql "$DATABASE_URL" -P pager=off -c "select run_id, started_at, ended_at, docs_seen, docs_changed, docs_indexed, status, left(coalesce(error_message, chr(60)||chr(110)||chr(111)||chr(110)||chr(101)||chr(62)), 240) as error from ingestion_runs order by started_at desc limit 5;"
psql "$DATABASE_URL" -P pager=off -c "select count(*) as active_documents from documents where is_active; select count(*) as chunks from chunks;"
psql "$DATABASE_URL" -P pager=off -c "select regulator, count(*) from documents where is_active group by regulator order by regulator;"
'
```

Check service health:

```bash
curl -fsS https://anchor.abhinash.dev/healthz
ssh ai-skyserver 'curl -fsS http://127.0.0.1:8010/readyz'
```

If ingestion succeeds, verify live query:

```bash
curl -sS -i --max-time 180 -X POST https://anchor.abhinash.dev/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"According to the RBI KYC Direction, who do the Directions apply to?"}'
```

If ingestion fails, inspect failed logs:

```bash
gh run view 27509390807 --repo VectorSigmaOmega/Anchor --log-failed
```

## Recommended Next Actions

1. Check whether GitHub run `27509390807` finished.
2. If succeeded, verify corpus counts, `/readyz`, and a live `/query`.
3. If failed with Gemini `429`, implement sanitized 429 diagnostics before changing throttle values again.
4. If still running close to timeout, decide whether to let it finish, move ingestion to a dedicated systemd job, or add per-document/batch progress commits.
5. Do not expose or print secrets from GitHub or `/etc/anchor/anchor.env`.
