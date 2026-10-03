# Multipart answer evaluation: 3 October 2026

The dual-registration question originally failed on the public site. The composer
silently truncated its 1,196 characters to 800, dropping the deposit and exemption
questions. A complete 733-character version reached the server but returned
`insufficient_support`, with no answer or citations, after 8.124 seconds.

The revised pipeline passes the reviewed fact and source checks for both versions,
along with all 27 existing cases. The UI and API now accept 4,000 characters. An
over-limit draft is preserved with a visible error, rather than silently clipped.

## What failed and what changed

The original retrieval selected five passages dominated by fees. It missed the
research-analyst deposit requirement. Generation also reconstructed table quotes
and used chunk suffixes as citation numbers; strict source validation rejected
those outputs. Increasing the input limit alone did not resolve the refusal.

Multipart questions now produce two to six role-specific searches. Candidate
selection reserves space for each topic before a single Cohere rerank call over
up to 40 candidates. Context selection retains relevant passages across those
topics, up to 16 chunks, without lowering the support threshold.

Gemini selects labelled, contiguous source excerpts for each claim. The server
constructs the exact quotes and numbered references, then validates them against
the retrieved text. Distinct quotes from the same chunk are allowed; unknown
references and duplicate quotes are rejected. Up to 24 citations can support a
long answer. The public response schema stays the same.

Expanded multipart context uses Gemini 3.5 Flash-Lite with low thinking and a
4,096-token output ceiling. Ordinary context keeps Gemini 3.1 Flash-Lite with
minimal thinking. With the same complete passages, 3.1 still omitted the required
undertaking and the source inconsistency. Embedding 2 and the existing index are
unchanged. IP limits remain 10 queries/minute and 100/day.

Prompts require explicit verdicts on proposed amounts, periods and activities;
separate role obligations and exceptions; and disclosure of incompatible source
requirements. They prohibit invented precedence or revision history and avoid
conflating advice/research segregation with research/distribution segregation.

## Results and expected answer

| Case | Original result | Revised result | Revised elapsed time |
| --- | --- | --- | ---: |
| Full 1,196-character question | Truncated to 800; incomplete answer | Answered, both circulars cited; reviewed checks pass | 9.532 s |
| Compact 733-character question | Refused: insufficient support | Answered, both circulars cited; reviewed checks pass | 9.651 s |
| Existing 27 regression cases | Earlier deployment passed 27/27 | 27/27 pass | Answered mean 3.33 s, median 3.31 s |

The reviewed answer distinguishes these requirements:

- Separate IA/RA compliance and reporting, an arms-length undertaking, and clearly
  segregated advisory and research services. Undifferentiated operation fails.
- Each role's annual fee ceiling is ₹151,000 per ordinary individual/HUF family,
  excluding statutory charges. The proposed ₹160,000 per service exceeds it.
- IA advance fees are limited to one year with client agreement. RA passages
  disagree: the main fee provision says one year; the MITC template says one
  quarter. Eighteen months exceeds either limit.
- Both roles refund unexpired fees. IA permits breakage of at most one-quarter
  fee; RA prohibits breakage fees.
- Prior-year peaks determine deposits: 280 IA clients require ₹2 lakh with a lien
  to IAASB; 425 RA clients require ₹5 lakh with a lien to RAASB. Current counts of
  120 do not replace that basis. Adjustment is due by 30 April of the subsequent
  financial year.
- Non-individual clients and accredited investors negotiate fee terms bilaterally.
  That fee exception does not establish an exemption from dual-registration duties.

The original expected-answer ledger missed the RA MITC on PDF page 60. The
corrected evaluation requires the inconsistency to be disclosed, without deciding
legal precedence. Sources are the indexed [IA circular](https://www.sebi.gov.in/sebi_data/attachdocs/feb-2026/1770375291405.pdf)
and [RA circular](https://www.sebi.gov.in/sebi_data/attachdocs/feb-2026/1770375507051.pdf).

## Evidence and reproduction

The [29-case dataset](../eval/quality.jsonl) contains the original 27 cases plus
both multipart questions. The [answers, quotes and timings](../eval/reports/multipart-2026-10-03.jsonl)
contain public regulatory text and synthetic questions. The artifact combines the
27-case regression results with the two final multipart reruns after multipart-only
prompt refinement. A subsequent replay of the required patterns also accepts
equivalent wording such as “research business” for “RA” and “separate rules.”
Those corrections preserve the required facts.

Calls used the local copy of the production index: 16 PDFs and 6,979 chunks from
the 2 May 2026 snapshot. No ingestion or embedding replacement was performed.
Load an environment pointing at an existing corpus, then run:

```bash
python -m scripts.evaluate_quality --output /tmp/anchor-quality.jsonl
```

The default 6.5-second pause respects the trial reranker quota. An explicit
`--models` pins both ordinary and multipart generation for a model comparison.

Local verification passed 116 tests, with three real-PostgreSQL integration tests
skipped locally and covered by CI. Frontend lint and static export passed.
Playwright checked `/` and `/chat` at widths 360, 768, 1,100 and 1,440: full drafts
and 4,001-character drafts were preserved, errors were visible, and no horizontal
overflow was found. A local browser query returned a complete answer in 10.248 s;
reloading/selecting its saved conversation and asking why current counts do not
determine deposits also returned HTTP 200 with supported citations.

## Limits

These are small regression checks, not exhaustive coverage of the corpus. Pattern
checks and exact quotations do not prove every generated claim is entailed. Manual
review was also used for the multipart answers. PDF extraction can give a chunk a
page label preceding the actual passage's page.

Multipart queries add planning, embedding searches, context and output tokens;
their latency exceeds the site's 3.5-second target. One local browser attempt
exceeded the existing 25-second query budget and returned HTTP 503; the retry
succeeded. Funded Gemini access does not remove Cohere's shared trial allowance
of 10 rerank calls/minute. The change keeps one rerank call per user query.
