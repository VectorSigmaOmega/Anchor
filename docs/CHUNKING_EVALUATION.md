# Chunking pilot — 3 October 2026

The corrected structure-aware parser is ready for rollout: the follow-up fixes
the pilot regressions, retains all checked source passages, and improves focused
retrieval coverage from 28/36 to 35/36. The original pilot is recorded below,
followed by the corrected parser results.

This evaluates parsing and chunk boundaries. Complex multi-document planning,
evidence verification and answer repair belong to the separate LangGraph work.

## Scope and controls

- All 16 production-snapshot PDFs (2,153 pages) were included in each index.
- Ten focused questions cover seven documents: KYC, MSME, research analysts,
  mutual funds, ICDR, Social Stock Exchange and non-convertible securities.
- There are 36 source-scoped passage checks, including nearby conditions and
  exceptions. Some check useful context beyond the question's minimum answer.
- The source snapshot is 2 May 2026. Local PDF checksums matched the manifest.
- The baseline uses the 6,979 copied production chunks and their existing vectors.
- Candidates share a layout parser. It uses font/style information for headings,
  retains headings in quotable text, interleaves tables with body text, preserves
  empty table cells, and retains original text when table extraction is incomplete.
- `fixed` packs blocks into a hard 450-word limit with 75 words of overlap.
- `structured` uses the same limit, prefers sentence/top-level-clause boundaries,
  and carries complete trailing blocks up to 75 words instead of fragments.
  Both split oversized tables with repeated headers when possible.
- Size counts whitespace words, matching the old implementation's measurement;
  these are not actual Gemini token counts.
- Every variant uses Gemini Embedding 2 at 768 dimensions, Cohere's configured
  reranker, and the deployed prompts/retrieval pipeline. Generation was pinned to
  Gemini 3.5 Flash Lite, low thinking, 4,096 output tokens for this comparison.
- Search plans and query vectors were generated once and reused across variants.
  This prevents different plans from obscuring the chunking comparison.
- No production data, provider configuration or deployed code was changed.

The baseline initially ran eight additional broader cases before the scope was
narrowed. They are excluded from every comparison below. Candidate construction
was revised during PDF extraction checks, before candidate answer evaluation.
The final candidate code and focused questions remained unchanged during the runs.

## Measurements

| Measure | Existing index | Corrected fixed-size | Structure-aware |
| --- | ---: | ---: | ---: |
| Indexed chunks | 6,979 | 3,591 | 3,915 |
| Median chunk size, words | 37 | 173 | 153 |
| Maximum chunk size, words | 658 | 450 | 450 |
| Checked facts in final answer context | 28/36 | 34/36 | 34/36 |
| Questions with all checked context | 6/10 | 9/10 | 9/10 |
| Generation input tokens across ten cases | 37,558 | 46,718 | 39,291 |
| Stored vector bytes, decimal MB | 21.47 | 11.05 | 12.04 |
| Median measured execution, seconds | 2.61 | 2.46 | 2.34 |

Timing excludes cached planning and query embedding for **all** variants. This is
one run per question and does not establish a live-site speed improvement.
The fixed-size candidate used 24.4% more generation input tokens than baseline;
the structure-aware candidate used 4.6% more. Fewer indexed chunks did not imply
cheaper answer generation.

The PDF audit found no reduction in per-page alphanumeric character inventories.
Both chunk constructors retained every parsed word. These checks detect omissions;
they do not prove correct reading order or table associations. The complete-index
fact check also detected the MSME split before retrieval evaluation.

## What the passages show

**SSE thresholds improved.** The old parser treats short numbered rules as
headings. The baseline answer cites `Page 9 of 31` for the minimum issue size,
and says the application-size rule is unavailable. Both candidates retrieve and
quote the operative ₹50 lakh issue minimum, ₹1,000 application minimum and 75%
subscription minimum, and correctly require refund of the ₹42 lakh subscription
to a ₹60 lakh issue. Historical ₹10,000 application wording remains available.

**Rights-issue evidence improved.** The baseline omits the withdrawal prohibition
and cites just `facility.` for the ASBA requirement. Both candidates supply the
complete ASBA-only provision and the prohibition on withdrawal after closing.

**The fixed candidate better preserved a balance-limit exception.** Its KYC
small-account answer includes the government-grant/welfare/procurement exception
to the ₹50,000 balance cap. The structure-aware context contains the exception,
but the generated answer omits it. That is an answer-selection issue rather than
evidence lost by chunking.

**MSME regressed in both candidates.** A change from 11-point to 12-point text
mid-paragraph makes the experimental parser treat the amount/continuation as a
heading. The obligation ends at `loans up to`; ₹20 lakh sits in the next chunk.
Both answers fail to give the mandatory waiver limit, although the original index
does. Font size alone is insufficient evidence of a section boundary.

**Section metadata still needs work.** The structured NCS answer labels EBP rules
as Chapter V even though the actual source heading is Chapter VI. A heading and
body text can share a PDF block, so classifying only whole blocks misses headings.

Manual inspection also found generation problems despite complete evidence: the
structured mutual-fund answer invents a proposed ₹40,000 redemption when the
question provides a ₹40,000 holding. These are recorded separately from passage
coverage; this pilot does not claim overall answer accuracy.

Existing keyword checks give 8/10, 7/10 and 8/10 respectively. Those are **not**
quality grades: “prohibited” fails a negation regex, “No withdrawal … permitted”
fails another, and a correct ₹45 lakh minimum fails a check expecting “70”. The
fact matches and inspected source passages are the relevant chunking evidence.

## Decision

Prefer structure-aware packing as the next candidate: it delivered the same
checked evidence as fixed-size packing with less answer context. First correct
heading detection to preserve paragraph continuations and extract actual section
headings inside mixed blocks. Repeat these focused passage checks before any
production reindexing. Do not tune chunking to solve complex cross-document
reasoning or discard historical footnotes to make answers easier.

The experimental indexes and newly generated vectors are local only. The
embedding cache holds 5,448 unique experimental document vectors, including
discarded extraction-preflight versions; identical texts were reused between
indexes. Baseline production vectors were neither replaced nor regenerated.

## Reproduction and artifacts

Worktree: `/home/dell/dev/AI_Engineer/Anchor-chunking`, branch
`experiment/chunking-comparison`, based on deployed commit `da8669bb`.
There are no application-source edits; the variants live in experimental scripts.

With the copied corpus, local PostgreSQL and existing `.env` available:

```bash
mkdir -p .benchmarks/chunking
ln -s /path/to/copied/corpus/raw .benchmarks/chunking/raw
.venv/bin/python -m scripts.prepare_chunking_experiment prepare
.venv/bin/python -m scripts.audit_chunking
.venv/bin/python -m scripts.prepare_chunking_experiment index --strategy fixed
.venv/bin/python -m scripts.prepare_chunking_experiment index --strategy structured
.venv/bin/python -m scripts.evaluate_chunking
.venv/bin/python -m scripts.analyze_chunking
```

Indexing creates only `anchor_chunking_fixed` and `anchor_chunking_structured`
on the local database host. Embedding and evaluation call the funded APIs.
Evaluation resumes existing answer files; use a new artifact directory or archive
the answer files for a fresh rerun after code/configuration changes. The query cache
must also be refreshed when the planner or query-embedding configuration changes.

- Questions: `eval/chunking_quality.jsonl`.
- Source passage criteria: `eval/chunking_evidence.json`.
- Full answers, quotes and candidate/context passages:
  `.benchmarks/chunking/{baseline,fixed,structured}.answers.jsonl`.
- Matched/missing source checks: `.benchmarks/chunking/retrieval-evidence.json`.
- Extraction audit: `.benchmarks/chunking/source-audit.json`.
- Aggregate results: `.benchmarks/chunking/results-summary.json`.
- Frozen code/question hashes: `.benchmarks/chunking/freeze.json`.

The new helper tests cover heading/rule discrimination, empty table-cell positions,
oversized-block preservation, heading/condition availability, incomplete/repeated
table values, regex quantifier handling and document-specific evidence checks.
Local validation finished with 126 tests passed, 3 skipped, and clean Ruff checks.
CI was not invoked for this experimental branch.

## Corrected parser and rollout candidate

The follow-up in `layout-structured-v2` fixes the two source-layout regressions:
font size alone no longer creates headings, and headings are detected inside
mixed heading/body blocks. Adjacent body lines remain together across font
changes. Chapter/annexure boundaries reset breadcrumbs; headings remain in
quotable text. No retrieval or generation prompts changed in this rerun.
The original pilot code and measurements above remain reproducible at `ce23896`.

The corrected structured index has 4,012 chunks (median 149.5 words, maximum
450), compared with 6,979 in the copied production index. The all-source audit
again covers 2,153 pages, detects no reduced alphanumeric inventories, and finds
all 36 checked passages within individual indexed chunks. Parsed word retention
and the hard chunk bound pass for all 16 documents.

With the same cached plans/query vectors and Gemini 3.5 Flash Lite controls, the
ten focused reruns retrieve 35/36 checked passages into final context (baseline
28/36), with complete checked context in 9/10 cases. The missing passage is the
MSME amendment effective-date footnote; it exists in the index but retrieval did
not select it. The restored MSME answer gives the mandatory ₹20 lakh waiver and
discretionary ₹25 lakh extension. The EBP answer attributes rules to Chapter VI.
Two additional source-reviewed questions, NBFC public-deposit maturity and
commercial-bank PSL targets/denominators, return the correct supported answers.

These are passage and boundary checks, not an overall answer-quality score.
Remaining generation issues include omission of a retrieved KYC balance exception
and an ICDR answer introducing an RTA T+2 passage alongside the ICDR T+1 rule.
The separate workflow evaluation must check scope, historical footnotes and claim
support. No further chunk tuning was made in response to these answer defects.

Generation input across the ten focused reruns totals 39,987 tokens (+6.5% versus
baseline), with 16,320 context words. Median measured execution is 2.433 seconds,
again excluding planning and query embedding; one run cannot establish live speed.
Local verification passes 134 tests, including six real PostgreSQL integration
checks. The reindex tests prove provider-failure rollback, continued access to the
old index during embedding, atomic replacement, and rejection of invalid bundles.

`python -m anchor.ingest.rechunk` verifies source checksums, stages the entire
replacement and commits it atomically. `--prepared-index` reuses evaluated vectors
only when their profile, source hashes and complete chunk records exactly match
a fresh parse. CI/CD's `run_rechunk` input saves a corpus-only backup first.
Document chunking versions ensure unchanged PDFs are not silently skipped after
a parser change. The existing index remains available until the final swap.

Fresh artifacts live in ignored `.benchmarks/chunking-v2`, preserving the pilot.
Set `CHUNKING_ARTIFACT_DIR` when repeating preparation/audit/evaluation, and use
`python -m scripts.export_rechunk_index` to export the evaluated replacement.
