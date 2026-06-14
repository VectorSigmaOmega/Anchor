# Anchor Roadmap Notes

## Provider Follow-Ups

- Switch the default generation model from `gemini-2.5-flash` to Gemini 3 Flash after confirming the exact Gemini Developer API model ID available to the deployment key.
- Investigate the `gemini-embedding-2` ingestion 429s against the AI Studio quota dashboard. Current deploy logs showed 429 responses from `gemini-embedding-2:batchEmbedContents`, but the dashboard did not appear close to requests-per-minute or input-tokens-per-minute limits. Capture provider error response bodies safely, without API keys, before making further throttling decisions.
