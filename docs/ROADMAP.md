# Anchor Roadmap Notes

## Production Readiness

- Fix retrieval and refusal tuning before production sign-off. RBI KYC live queries currently return HTTP 200 but can refuse with `insufficient_support` despite the RBI KYC document being indexed. Inspect retrieved chunks, reranker scores, support thresholds, and prompt behavior.
- Add a production smoke-eval set with known-answer RBI and SEBI questions. Include at minimum RBI KYC, RBI MSME, RBI priority sector lending, SEBI Mutual Funds, SEBI ICDR, and SEBI LODR. Gate production readiness on cited answers for in-corpus questions and refusals for out-of-corpus questions.
- Add operator-visible query diagnostics for refused answers: top retrieved doc IDs, rerank scores, support-count decision, refusal reason, and whether generation was attempted. Keep user-facing responses clean.
- Resolve or explicitly accept the frontend `npm audit` high/moderate findings before production sign-off.
- Review GitHub Actions Node.js 20 deprecation warnings and upgrade/replace actions before they become blocking.

## Provider Follow-Ups

- Promote generation from `gemini-3-flash-preview` to the stable Gemini 3 Flash model ID when Google publishes one for the Developer API.
- Replace the current fail-open Langfuse compatibility wrapper with a real Langfuse v4/OpenTelemetry tracing integration. Preserve fail-open behavior, but emit actual query spans/generations with request ID, retrieval stages, selected citations, model usage metadata, refusal reason, and final status.
- Investigate the `gemini-embedding-2` ingestion 429s against the AI Studio quota dashboard. Current deploy logs showed 429 responses from `gemini-embedding-2:batchEmbedContents`, but the dashboard did not appear close to requests-per-minute or input-tokens-per-minute limits. Capture provider error response bodies safely, without API keys, before making further throttling decisions.
- Improve Gemini diagnostics before changing throttling again:
  - Log sanitized 429 response body fields, including provider error `code`, `status`, `message`, and quota metadata when present.
  - Log response headers relevant to throttling, especially `retry-after`, request IDs, and Google quota/project headers when present.
  - Include Gemini request path, configured model, batch size, attempt number, and calculated backoff delay in structured logs.
  - Track embedding ingestion counters per document and per batch so long runs show visible progress before the final DB run update.
  - Distinguish quota exhaustion, billing/project mismatch, model-specific batch limits, transient overload, and malformed request errors in operator-facing messages.

## Corpus Verification

- Manually verify all SEBI corpus documents before production sign-off. Confirm each selected SEBI source is up to date, the document body contains the expected full file contents, and no source file or download is missing from the pinned manifest.

## Deployment Lifecycle

- Current GitHub Actions deploy has an application restart phase, not a VPS reboot phase. The deploy installs the release, runs migrations, optionally runs ingestion, then executes `sudo systemctl restart anchor-api` and `sudo nginx -s reload`. Add an explicit post-deploy verification step for `/healthz`, local `/readyz`, corpus counts, and a smoke `/query`.
- Consider splitting ingestion from application deployment. Full ingestion can take much longer than code deploys and should eventually run as a dedicated systemd job or manual workflow with clearer progress logs.
