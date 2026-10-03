# Live response quality: 3 October 2026

The revised pipeline passed 24 of 24 reviewed cases against the existing production
index, up from 22 of 24 after Gemini billing was restored. All three questions offered
by the website also passed a separate check. Gemini remains the generation and
embedding provider.

## Corpus and method

- Corpus snapshot: 2 May 2026, 16 active RBI/SEBI PDFs, 6,979 indexed chunks.
- Tests used the production PostgreSQL index through an isolated checkout on the
  VPS. They did not ingest documents, replace embeddings, or write chat history.
- The 24 comparison cases cover KYC, MSME lending, NBFC deposits and research
  analysts: 18 standalone answers, two contextual follow-ups and four refusals.
- Expected facts and PDF pages were reviewed against the cached source documents;
  the cases are in [eval/quality.jsonl](../eval/quality.jsonl).
- A pass means the expected answer/refusal, required fact patterns and expected
  source document were present. Revised answered responses also passed runtime
  validation of their supporting quotations against the retrieved text.
- Outputs, citations and timings are preserved in
  [the run artifact](../eval/reports/quality-2026-10-03.jsonl). This contains public
  regulatory excerpts and synthetic test questions, without credentials or user chats.
- Calls were paced to respect the Cohere trial quota. Pauses are excluded from latency.

## Results

| Run | Generation model | Core cases passed | Mean answered latency | Median answered latency |
| --- | --- | ---: | ---: | ---: |
| Billing restored, original pipeline | Gemini 3.1 Flash-Lite | 22/24 | 1.69 s | 1.66 s |
| Revised pipeline | Gemini 3.1 Flash-Lite | 24/24 | 2.28 s | 2.07 s |
| Revised pipeline, model comparison | Gemini 3.5 Flash-Lite | 24/24 | 2.26 s | 2.18 s |

The original pipeline answered a GST-rate question from unrelated material,
including a document template placeholder. It also rejected a clear follow-up about
low-risk KYC update intervals as ambiguous. Both failures are corrected.

The three website starter questions were tested separately on the revised 3.1
pipeline and passed 3/3. They are included in the dataset for subsequent 27-case runs.
The baseline and 3.5 comparison did not include those additional three cases.

## Changes that mattered

- Resolve short follow-ups into standalone retrieval questions. Search and rerank
  the resolved topic instead of letting the previous risk category dominate retrieval.
- Require each generated citation to include an actual supporting quote. Verify
  it against the retrieved text rather than displaying the chunk's opening words.
  An ellipsis is expanded only when every substantial fragment matches the source
  in order; the displayed result includes the original intervening conditions.
- Prompt for exact thresholds, exceptions, mandatory versus optional requirements,
  and source references. Increase the output ceiling to accommodate verified quotes.
- Reject unsupported tax-rate/filing requests and unresolved references before
  retrieval. Incidental GST mentions in regulatory fee questions remain in scope.
- Surface provider outages as HTTP 503 instead of misleading corpus refusals.
  Remove the reranker failure path that invented high relevance scores.
- Use the current Embedding 2 question-answering prefix. Its API does not support
  `taskType`; embeddings remain 768-dimensional and the existing index is preserved.
- Keep per-IP limits at 10 queries/minute and 100/day, trust client addresses only
  through nginx, and return HTTP 429 with `Retry-After` on application limits.

## Model choice

Keep **Gemini 3.1 Flash-Lite with minimal thinking**, plus **Gemini Embedding 2**.
3.5 Flash-Lite is available and passed the same fact checks, but did not improve the
overall pass count or latency enough to justify a change for this corpus. Manual
inspection also found two 3.5 outputs using internal chunk IDs instead of numbered
references, despite otherwise passing the fact checks.

Standard text pricing checked against [Google's pricing documentation](https://ai.google.dev/gemini-api/docs/pricing):

| Model | Input / million tokens | Output / million tokens |
| --- | ---: | ---: |
| Gemini 3.1 Flash-Lite | $0.25 | $1.50 |
| Gemini 3.5 Flash-Lite | $0.30 | $2.50 |

These are token rates, not total query costs; reranking, embedding, rewrites and
validation retries add usage. The higher output ceiling permits longer supported
quotes; it does not force every response to consume the maximum tokens.

Current API guidance: [Embedding 2 task instructions](https://ai.google.dev/gemini-api/docs/embeddings)
and [Gemini 3.5 Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite).

## Reproduce

Load the application environment, then run against an existing indexed database:

```bash
python -m scripts.evaluate_quality --output /tmp/anchor-quality.jsonl
python -m scripts.evaluate_quality \
  --models gemini-3.1-flash-lite,gemini-3.5-flash-lite \
  --output /tmp/anchor-model-comparison.jsonl
```

The default 6.5-second pause respects the trial reranker quota. Any failed case
returns a nonzero exit status. `--only` selects case IDs; `--contexts` replays
previously saved passages for a generation-only comparison, which does not test
retrieval or application refusal guards.

## Limits of this evidence

This is a small regression set covering four document families, not exhaustive
coverage of all 16 documents. Fact-pattern and source-overlap checks do not prove
that every claim is entailed or every relevant exception is included. Quotations
are verified against indexed text; PDF extraction and chunk page boundaries can
still affect presentation. These results are separate from the fixture smoke
metrics and from the much larger generated seed benchmark in [EVAL.md](EVAL.md).

The existing Cohere key has a trial limit of 10 rerank requests per minute across
all users, independently of per-IP limits. Rapid or concurrent traffic can therefore
return a temporary service error even with funded Gemini access. Live tests confirmed
HTTP 429 after the trial allowance was exhausted; see [Cohere's limits](https://docs.cohere.com/v2/docs/rate-limits).
