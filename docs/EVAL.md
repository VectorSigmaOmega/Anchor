# Anchor Evaluation

## Current Status

- Verified locally: fixture smoke evaluation path.
- Not yet verified: live full evaluation against an indexed PostgreSQL corpus and real Gemini/Cohere API calls.
- Production-readiness implication: the current checked-in metrics prove eval plumbing only. They do not prove retrieval quality, refusal quality, latency, or grounded answer quality in production.

## Latest Verified Fixture Run

- Mode: Smoke
- Execution: fixture mode
- Retrieval Recall@5: 1.00
- Citation validity: 1.00
- Faithfulness / groundedness: 1.00
- Refusal precision: 1.00
- Average latency (ms): 15.2
- Malformed outputs: 0

## Method

- Full eval runs the direct query service against the indexed corpus when Gemini/Cohere credentials and PostgreSQL are available.
- CI smoke eval runs against the fixed `eval/smoke.jsonl` subset in fixture mode to validate the benchmark path without external providers.
- Citation validity requires every answered response to include at least one citation whose `doc_id` matches the expected document set.
- Groundedness is tracked as a citation-overlap proxy against the reviewed reference set.

## Required Before Production Claim

- Run `python eval/run.py --write-docs` with a populated database and real provider credentials.
- Replace or supplement the generated seed questions with reviewed regulatory QA items that test actual document obligations, thresholds, exceptions, and refusal boundaries.
- Publish the resulting full-eval metrics here with the run date and corpus snapshot date.
