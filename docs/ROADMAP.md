# Anchor Roadmap Notes

## Provider Follow-Ups

- Switch the default generation model from `gemini-2.5-flash` to Gemini 3 Flash after confirming the exact Gemini Developer API model ID available to the deployment key.
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
