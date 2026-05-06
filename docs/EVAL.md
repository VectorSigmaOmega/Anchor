# Anchor Evaluation

## Latest Run

- Mode: Smoke
- Execution: fixture mode
- Retrieval Recall@5: 1.00
- Citation validity: 1.00
- Faithfulness / groundedness: 1.00
- Refusal precision: 1.00
- Average latency (ms): 15.2
- Malformed outputs: 0

## Method

- Full eval runs the direct query service against the indexed corpus when cloud credentials and PostgreSQL are available.
- CI smoke eval runs against the fixed `eval/smoke.jsonl` subset in fixture mode to validate the benchmark path without external providers.
- Citation validity requires every answered response to include at least one citation whose `doc_id` matches the expected document set.
- Groundedness is tracked as a citation-overlap proxy against the reviewed reference set.
