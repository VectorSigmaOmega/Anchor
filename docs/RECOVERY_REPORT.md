# Anchor recovery, 2026-10-03

Production Gemini embedding and generation requests initially returned HTTP 402
because Google prepayment credits were depleted. Access recovered during the
investigation; no billing change was made by this agent. The corpus was intact:
16 documents and 6,979 indexed chunks. Gemini remains the default provider.

Provider failures now return a recoverable service error rather than a corpus
refusal or invented reranking confidence. Queries have a 25-second budget.
IP limits are 10 requests/minute and 100/day, shared across query routes, with
trusted proxy handling, HTTP 429 and Retry-After. Daily counts persist in PostgreSQL.

## Provider choice

Prices checked against official model pages on 2026-10-03, USD per million tokens:

| Generation model | Input | Output | Assessment |
| --- | ---: | ---: | --- |
| Gemini 3.1 Flash-Lite | $0.25 | $1.50 | Current model; verified against the copied production corpus |
| GPT-4.1 mini | $0.40 | $1.60 | Configurable OpenAI default; requires live comparative evaluation |
| GPT-5.4 mini | $0.75 | $4.50 | Higher-cost comparison candidate; no Anchor quality result yet |

Sources: [Google pricing](https://ai.google.dev/gemini-api/docs/pricing),
[GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini),
[GPT-5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini).

Gemini Embedding 2 text costs $0.20/million tokens; OpenAI
text-embedding-3-small costs $0.02/million. The latter supports the index's
768 dimensions. Sources: [Google pricing](https://ai.google.dev/gemini-api/docs/pricing),
[OpenAI embeddings](https://developers.openai.com/api/docs/guides/embeddings),
[embedding model pricing](https://developers.openai.com/api/docs/models/text-embedding-3-small).

Generation and embedding providers can be selected independently. Retain Gemini
for this release because access works and its answers have a measured baseline.
OpenAI request formats, structured responses and embedding validation have mock
coverage; no OpenAI credential was available for live testing. Changing embedding
providers requires replacing the corpus vectors, even when dimensions match.
The new migration stages replacements and commits vectors and model provenance
atomically. PostgreSQL integration tests cover rollback, successful replacement
and continued reads of the old index during generation.

## Answer checks

The public corpus and existing vectors were copied to an ignored local development
database. Natural-language lexical retrieval now ranks significant terms, contents
pages are filtered, follow-ups use conversation context, and prompts preserve
limits, exceptions and the scope of each obligation. Citation checks reject
unknown IDs and empty answers; model-supplied excerpts are checked against source text and links
open the PDF at its cited page.

The focused live benchmark passed 14/14 cases: 10 supported answers and four
refusals. Cases cover KYC small-account limits, due diligence, research analyst
fees and disclosures, conflicting advance-fee rules, MSME classification,
out-of-scope tax/labour questions and a contextual follow-up. Saved results are in
`docs/traces/regulatory_eval_2026-10-03.json`; cases are in `eval/regulatory.jsonl`.
These are outcome, document and expected-fact checks, not a comprehensive
faithfulness score or a full rerun of the historical golden evaluation.
The integrated release also passed all 27 cases in `eval/quality.jsonl`, including
all three website starter questions and a low-risk KYC follow-up. Current outputs
are saved in `docs/traces/quality_eval_2026-10-03.json`. The two sets overlap;
these counts describe two passing suites, not 41 distinct questions.

The mean latency of the 10 answered cases was 3.90 seconds and the maximum was
5.24 seconds. Benchmark requests were spaced eight seconds apart because the
existing Cohere trial key returned 429 during unpaced experiments. This is an
aggregate provider quota; per-IP limits alone cannot eliminate it under multiple
simultaneous users. The application surfaces an outage instead of fabricating
support when reranking fails.

The corpus contains two different advance-fee statements: one year in the
research analyst fee rule and one quarter in the MITC. The answer now identifies
both statements and cites both instead of silently choosing one.

## UI and development

Playwright checks covered `/` and `/chat` at widths 360, 768, 1100 and 1440,
including a real supported answer, sources, mobile navigation, light/dark,
refusal and a simulated provider outage. A mobile grid sizing bug clipped the
composer and transcript; it is fixed. Sources are easier to inspect, citations
are clickable, and failures offer a clear retry action. A returning-browser
check also caught cached HTML pointing to JavaScript files removed by deployment.
Releases now revalidate HTML and retain previous hashed assets; previous assets
were restored from the server's retained releases.

The integrated release passed 94 backend tests, Ruff, UI lint and the production
static export build. See `docs/LOCAL_DEV.md` for the
populated development database, public-only corpus sync and real benchmark.
