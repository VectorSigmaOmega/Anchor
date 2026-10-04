# Response quality improvement tracker

Updated: 4 October 2026. Owner: Codex with Abhinash.

This file tracks the remaining work, the first approach to each problem, how to
judge the result, and a backup if the first approach fails. Proposed changes below
are tracked separately from the implementation status. The candidate has passed
the limited local release checks described below; CI and production checks are
still pending. Status changes must link to code and recorded results;
implementing a change is not the same as resolving its problem.

## Starting point

- **Deployed:** Gemini generation and embeddings, IP limits, the 4,000-character
  question limit, citation/UI improvements, and the corrected 4,012-chunk index.
- **Experimental:** [PR #9](https://github.com/VectorSigmaOmega/Anchor/pull/9)
  contains a bounded LangGraph workflow. It remains disabled and undeployed.
- **Recorded baseline evidence:** [workflow evaluation](WORKFLOW_EVALUATION.md),
  [answers and traces](../eval/reports/workflow-2026-10-03.jsonl), and
  [chunking evaluation](CHUNKING_EVALUATION.md). New development-only replay
  results are summarized below and stored in ignored `.benchmarks/workflow/`
  artifacts. Replay reuses old retrieved passages, so its timings exclude fresh
  retrieval, embedding, and reranking.
- The software tests establish software behavior, not factual
  correctness. The 27 ordinary regression checks and five complex comparison
  questions provide limited evidence of answer quality.
- **Frozen development cases:** `eval/workflow_quality.jsonl` (five cases), SHA-256
  `2a287f6d2be34388a6f61b4ba85fa060426620b8cc678415eab78af9fce652`.
  They may guide implementation and become regression tests.
- **Initial held-out cases:** `eval/workflow_holdout.jsonl` (ten scenarios),
  SHA-256 `50bd21200d517631cd64fad3f2e16d999c223e957cec4e12891f0d5153bdb695`.
  The first candidate run exposed a false refusal on `holdout_ncs_first_time`;
  that question is now a regression case. **Revised held-out set:**
  `eval/workflow_holdout_v3.jsonl`, SHA-256
  `d92aa1da6c2f21082b5a36e82434b1b0cad956eea185d810da68cf5e6f804b0e`,
  replaces it with an LODR deadline scenario whose first-quarter scope is
  explicit. The remaining nine
  questions are unchanged and already seen in the initial run; disclose this
  limitation when reporting generalisation. `must_include`, `must_not_claim`,
  and source page fields are the review rubric; empty regex-pattern lists
  intentionally avoid treating keywords as semantic grades.

## Work list

| ID | Problem | Status | First approach | Backup |
| --- | --- | --- | --- | --- |
| P1 | Incorrect assertions pass verification | Validated locally on focused corruption controls and source-reviewed answers; broader accuracy unproven | Check each independent assertion against its own source rule | Render difficult parts directly from verified source records/excerpts |
| P2 | Relevant obligations and requested details disappear | Validated locally on undertaking-omission control and five development cases; broader completeness unproven | Dynamic review tasks with obligation and answer coverage checks | Answer requested parts separately, then assemble without resummarizing |
| P3 | Differing provisions are overlooked or incorrectly reconciled | Validated locally on RA advance-period and historical-footnote regressions; cross-document precedence remains unresolved where sources do not establish it | Compare rules about the same activity and applicable scope | Present unresolved source provisions side by side with citations |
| P4 | Relevant passages exist but are not selected | Validated locally on a withheld-footnote control; five development questions avoided unnecessary follow-up searches | Targeted follow-up retrieval and nearby/reference expansion | Retrieve a bounded parent section with lexical and document-aware search |
| P5 | Extra calls increase cost, latency, and capacity pressure | Five-case full workflow median 21.91 s and 275,161 generation input tokens versus 10.73 s and 45,547 for the source-comparison linear path; live progress implemented; production capacity pending | Reduce duplicated context/calls and measure per-stage usage | Use a simpler evidence-first path and restrict costly reviews to unresolved parts |
| P6 | Evaluation is too narrow to establish generalisation | Three repeated revised held-out runs met all written expectations on both routes; only one of ten questions used the graph, nine were previously seen, and production remains unchecked | Freeze source-reviewed development and held-out sets | Narrow rollout scope and retain source-reviewed/manual release checks |
| P7 | Remaining UI states need refinement and verification | Live SSE stage events, cancellation, mobile navigation, failure/refusal actions and landing metrics pass local checks; production smoke check pending | Test loading, citations, errors, partial answers, and responsive behavior | Use a simpler answer/status/source presentation if richer interactions fail |

## Development checkpoint (4 October 2026)

The disabled workflow now uses bounded, question-derived topic reviews over
existing retrieved passages. It retains source IDs, discards findings with IDs
outside the supplied topic excerpts, compares up to two candidate source pairs,
and re-reviews evidence after a follow-up search. Numbered requests are drafted
as separate sections. A numeric proposal guard catches an omitted user amount,
percentage, or period before model verification; claim checks separate some
mixed clauses and compare discretionary with mandatory wording. These are
generic mechanisms, with no regulator, document, or IA/RA branch in the workflow.
The guard does not establish that an answer has assessed every proposal or that
the assessment is correct.

Five development questions were rerun **once each with recorded retrieved
passages** under Gemini 3.5 Flash Lite and the existing structured index.
The five outputs passed their old keyword-pattern checks, which are only a
screen. A manual inspection found the requested IA/RA fees and undertaking,
the two unresolved RA advance periods, the discretionary currency-chest
penalty, bank-specific PSL denominators, distinct RTA/issuer deadlines, and
the two NBFC customer beneficial-owner routes. This small inspection is not
an independent semantic release grade. The RTA topic reviewer cited one
out-of-set excerpt; the code discarded that finding and retained valid ones.
It also produced inaccurate tentative gap notes despite relevant text being
available to the final drafter, so coverage review still needs work.

| Development case | Replay seconds | Gemini calls | Input-token proxy | Artifact |
| --- | ---: | ---: | ---: | --- |
| IA/RA | 24.11 | 9 | 55,336 | `.benchmarks/workflow/answers-topic-v6-ia-replay.jsonl` |
| Currency chest | 16.15 | 8 | 23,815 | `.benchmarks/workflow/answers-topic-v6-currency-replay.jsonl` |
| PSL bank categories | 15.35 | 7 | 29,498 | `.benchmarks/workflow/answers-topic-v8-psl-replay.jsonl` |
| NBFC/KYC | 13.02 | 7 | 39,123 | `.benchmarks/workflow/answers-topic-v9-remaining-replay.jsonl` |
| RTA/issuer | 13.17 | 7 | 32,099 | `.benchmarks/workflow/answers-topic-v10-rta-replay.jsonl` |

Replay excludes fresh retrieval and is **not** comparable to the recorded
end-to-end linear latency. The replay median alone is 15.35 seconds, above the
provisional 12-second target. A previous end-to-end IA/RA run took 33.78
seconds, above the current 30-second proxy timeout, and the IA/RA replay used
55,336 generation-input tokens versus roughly 19,000 in its earlier linear
run. Several development attempts initially timed out or omitted scenario
values before the fixes. The workflow remains disabled; no held-out answers
were generated.

A focused live verifier control using the indexed currency-chest clause accepted
“may be levied” and rejected the deliberately strengthened “is levied
automatically” (`.benchmarks/workflow/discretionary-claim-control.json`).
This one controlled claim does not show that all claim types are caught. The
full software suite passed 161 tests, and Ruff passed. Next, measure and try
the simpler P5 path against the same development cases, improve P4 passage
coverage only where retrieval evidence shows a miss, then perform a fresh
end-to-end comparison before opening the held-out set. P7 follows a workflow
that can meet the live site's latency and quality requirements.

## New development checkpoint (4 October 2026)

The disabled workflow now bounds long-answer claim checks into 12-claim batches,
adds a separate full-answer coverage review, rechecks disputed claims against
focused source text, and preserves server-held citations when a repair fails.
Its follow-up search can add at most four lexically relevant chunks near existing
source anchors. A direct indexed-source probe recovered the MSME effective-date
footnote two chunks away; this does not yet prove that the full workflow chooses
to perform a follow-up when that footnote is missing. Full topic reviews still
consume too many tokens and can exceed the site's current timeout.

The P5 backup is now the better-performing **development candidate**: use Gemini
3.5 Flash Lite for retrieval planning and Gemini 3.8 Flash for the final answer.
The linear answer prompt and planner were rewritten to use general actor, duty,
scope, scenario-value, and conflict instructions. The IA/RA-specific hints and
advance-fee detector were removed. On one fresh end-to-end run of the five frozen
development questions, all five were answered, median latency was 7.57 seconds,
and generation input totalled 40,736 tokens
(`.benchmarks/workflow/answers-linear-generic38-v3-endtoend.jsonl`). Manual
inspection found the requested calculations and duties, the currency-chest
discretion, the distinct RTA/issuer deadlines, and both RA advance periods.
The IA/RA answer calls them a textual divergence but does not explicitly say
which period controls remains unresolved. Its old keyword screen flags this as
missing `inconsisten|discrepan|conflict`; the answer still needs semantic review.
These are **one-run development results**, not held-out evidence or a production
decision. A preceding run with 3.8 Flash as planner hit the 25-second application
budget on two of five questions; the Lite planner avoided those outliers in the
single matched run. The held-out set remains untouched.

The full software suite now passes 176 tests and Ruff passes. Next: run varied
corrupted-answer controls for P1, verify the effective-date end-to-end probe and
other retrieval misses, then repeat the source-reviewed development evaluation.
Only after that gate should the frozen held-out set be opened. P7 and deployment
remain pending.

## Paused checkpoint (4 October 2026)

Implementation is paused on the draft branch; it has not been merged or deployed.
The optional linear comparison is off by default. Its first five-case run answered
all questions but did not surface the known RA advance-fee difference during the
comparison stage: two less relevant numeric pairs used its two-pair budget.
A generic ranking change now prefers comparisons between different source chunks.
The second fresh end-to-end run answered all five development questions, with a
10.55-second median and 47,287 generation-input tokens
(`.benchmarks/workflow/answers-linear-compare38-v2-endtoend.jsonl`). Its comparison
stage identified the RA one-year versus one-quarter provisions and returned no
differences for the other four cases. The IA/RA answer explicitly states that the
provided excerpts do not establish precedence. One run is not a reliability or
generalisation result.

Other completed checks: six live verifier corruption/valid-answer controls pass;
a separate coverage pass caught the omitted undertaking in a live repeat; a
direct indexed-source probe recovered the MSME effective-date footnote, and one
end-to-end question cited it correctly. A second generic linear run answered all
five cases; another answered four and failed once at the Cohere request. These
remain limited development checks, not release grades. The UI fixes were checked
locally at 360, 768, 1100, and 1440 px, including mobile keyboard navigation,
long citations, and error/refusal actions; `npm run lint` and `npm run build`
passed. The backend suite passed 179 tests; Ruff and `git diff --check` passed.

**Remaining gates:** (1) inspect the new answers against source text and repeat
the generic comparison with negative and changed-scope controls; (2) resolve or
bound Cohere failures and tail latency without masking provider errors as corpus
refusals; (3) evaluate passage-recovery misses where initial retrieval lacks the
needed clause; (4) run the frozen ten-case held-out set once, source-review its
answers and compare quality, latency, and cost with the current linear route;
(5) finish UI rate-limit/error checks, then update this tracker and the draft PR.
Only enable a production path that passes these gates. If comparison remains
unreliable, use the P3 side-by-side cited-source fallback; if workflow calls are
too slow, retain the simpler linear route and limit extra review to uncertain
parts.

## Resumed development checkpoint (4 October 2026)

The full LangGraph candidate now checks reviewer-reported gaps against the
complete selected context before follow-up retrieval. In a controlled end-to-end
probe that withheld an indexed MSME effective-date footnote on the first pass,
it searched again, recovered the footnote, and cited the effective date. The
previous rule that searched for every tentative reviewer limitation had caused
an unnecessary second retrieval in all five development cases. The revised
candidate used one retrieval on each of those five cases and answered all five.
The old IA/RA keyword pattern still flags equivalent wording such as “the
excerpts do not establish which provision controls”; inspect that answer
semantically rather than treating the keyword screen as a grade.

The five-case full-workflow run had a 21.91-second median, 275,161 generation
input tokens, and an estimated $0.188 Gemini generation cost using published
model prices (`.benchmarks/workflow/answers-workflow-mixed-v3-adjudicated.jsonl`).
That estimate excludes embeddings, reranking, and any billing differences.
One IA/RA run omitted an explicit unresolved-precedence statement even though
it cited both periods. Bounded comparison now reserves a candidate for a
different quantity kind when fee-amount pairs otherwise occupy both slots.
Two focused live IA/RA reruns disclosed the one-year versus one-quarter
provisions and the lack of established precedence. A spelling variant in the
disclosure detector was fixed to avoid adding a duplicate fallback paragraph.

The chat now streams actual stage transitions from the backend, including
planning, retrieval, evidence review, follow-up retrieval, drafting, and claim
checks. A local browser run displayed those transitions before a cited answer;
the stream, cancellation, error, rate-limit, and cookie paths have software
tests. The TLS nginx route now disables proxy buffering and allows 75 seconds;
the application allows 60 and the browser 90. User accepted a longer answer
time when the workflow's progress is visible. The previous provisional
12-second median target is therefore diagnostic rather than a release gate.
The backend suite passes 196 tests; Ruff, UI lint/build, and `git diff --check`
pass. Production remains unchanged. The ten-case held-out comparison has begun
only after these development checks; its result and release decision remain open.

The first held-out run answered nine questions and falsely refused the NCS
first-time-issuer question. The matched linear comparison answered all ten.
The NCS source-review pair received an excerpt starting in the middle of a
historical footnote, so it did not see the preceding “prior to substitution”
statement and treated the old five-working-day deadline as a live conflict.
Giving pair comparison the bounded containing chunk restored that context; the
NCS question then answered in one live regression run. This fix applies to
historical and scoped notes generally, not an NCS-specific branch. The new
ten-case set replaces that regression question with an LODR deadline question;
its SHA-256 is recorded above. The first held-out run also exposed an apparent
ICDR T+1 versus RTA T+2 difference: both indexed excerpts explicitly describe
rights-entitlement trading, so the answers correctly report the unresolved
cross-document difference instead of choosing precedence. Production remains
unchanged while the revised set is evaluated.

## Local release comparison (4 October 2026)

The revised ten-case set was run three times through each route with the same
Gemini 3.8 Flash final-answer model and Gemini 3.5 Flash Lite planner. The
`linear_compare` route retains a bounded source-comparison call for multipart
questions; it skips the graph's topic review, coverage, and claim checks.

| Route | Runs meeting written case expectations | Median seconds per ten-case run | Gemini generation input tokens per run | Artifacts |
| --- | --- | --- | --- | --- |
| Graph for multipart questions | 10/10, 10/10, 10/10 | 4.58, 4.80, 4.43 | 87,894; 84,909; 91,009 | `.benchmarks/workflow/holdout-v3-workflow-r{1,2,3}.jsonl` |
| Linear with source comparison | 10/10, 10/10, 10/10 | 4.60, 4.77, 4.63 | 39,094; 38,798; 38,263 | `.benchmarks/workflow/holdout-v3-linear-r{1,2,3}.jsonl` |

Nine questions took the ordinary route on both paths; only the KYC small-account
question triggered multipart routing. The similar held-out outcomes therefore
do not demonstrate a graph quality advantage. These were rubric and source-spot
checks, not an independent expert grade. Nine questions were also already seen
after the first held-out gate. The old NCS false-refusal case answered correctly
in three consecutive live graph runs after the full-chunk context fix
(`.benchmarks/workflow/ncs-first-time-regression-v{2,3,4}-context.jsonl`).
The fix exposes historical supersession text to the comparison step; no
NCS-specific handling was added.

The five complex development cases exercised the graph and source-comparison
linear route end to end. The graph's median was 21.91 seconds and used 275,161
Gemini generation input tokens; the linear route's median was 10.73 seconds and
used 45,547. Both routes answered all five. The IA/RA graph answer explicitly
said the two RA advance-fee periods were unresolved, even though its legacy
keyword screen flagged that wording. A fresh IA/RA and RTA/issuer graph rerun
again answered and covered the requested duties, dates, fee limits and source
differences (`.benchmarks/workflow/dev-complex-final-r1.jsonl`). This supports
local correctness on the tested questions, not a broad superiority claim.

The rollout choice is to use Gemini 3.8 Flash for ordinary answers and enable
the bounded graph only for detected multipart questions. Its extra review and
claim-check controls address the previously observed omission and modal-wording
failures; the user accepts longer answer time when real stage progress appears.
This is a cautious inference from targeted controls, not a measured overall
accuracy lift. The graph stays feature-flagged so production can revert to the
ordinary route without changing the corpus. Before rollout: CI, production
configuration, and browser smoke checks. After rollout: monitor real latency,
provider errors, and answer samples, and disable the graph if those regress.

Local validation: 191 tests passed and 6 PostgreSQL integration checks skipped
without a local PostgreSQL service; Ruff, UI lint/build, fixture smoke
evaluation, and `git diff --check` passed. CI must run the database checks.

## Shared design for P1–P4

Use one generic workflow. The planner derives review tasks from the current
question; there will be no fixed list of fee, deposit, IA, or RA workflows.
All tasks use the same evidence-review procedure. Group passages by the activity
being examined, including related passages from different documents. Keep nearby
conditions, exceptions, footnotes, and scope together.

For each relevant source rule, retain the actor, action, mandatory/discretionary
wording, conditions, amount or period when present, and the exact supporting
passage. Keep user-supplied scenario facts separate from source rules. Citation
references must resolve to server-held text; the model must not reconstruct quotes.

Review tasks and follow-up searches will have explicit limits on calls, context,
and retries. The planner's task list is checked against the original question.
An unfamiliar question follows the same process. An unsupported part remains a
visible gap instead of becoming an invented rule.

This design is a hypothesis. Smaller source sets can also hide useful connections;
the checks below must test that failure mode. Keep the same Gemini models and
index for the first comparisons so changes in behavior can be attributed.

## P1 — Incorrect assertions pass verification

**Observed:** The source says a penalty “may be levied.” The answer says it
“incurs a flat penalty.” The reviewer approved it. That sentence also contained
a separate discretionary statement about interest, but received one overall
classification. A valid citation did not establish that both assertions were true.

**Proposed solution:** Break the draft into independent assertions, preserving
their exact text or character spans. Check each assertion against the relevant
source rule and surrounding qualifications. A sentence may need several checks.
Compare the actor, action, conditions, force of the wording, and amounts/periods.
Validate identifiers and coverage in code. Use deterministic arithmetic and
numeric comparisons when the units and operands are explicit; interpretation
of language still requires evaluation. Allow one targeted repair and recheck.

**Success check:** Catch controlled changes from permission to certainty,
removed conditions, swapped actors, incorrect amounts, and altered calculations.
Include equivalent paraphrases and correctly qualified answers that should pass.
The known mixed-sentence penalty error must be caught across repeated runs.

**Backup trigger:** The focused checker still approves a material unsupported
assertion, or frequently rejects correct answers on the frozen evaluation set.

**Backup solution:** For the affected part, use a constrained rendering of the
source records and show the exact qualifying excerpt. Independently validate any
calculation. If the records cannot be trusted, show the relevant source wording
and explicitly leave the interpretation unresolved. This reduces fluent synthesis
but preserves useful evidence. It does not turn an unverified extraction into a
verified fact. Test this alternative against the same cases before enabling it.

## P2 — Obligations and requested details disappear

**Observed:** The IA/RA answer described separation of the businesses but omitted
the separate requirement to provide an undertaking. A KYC answer also omitted a
balance-limit exception that was present in its supplied evidence.

**Proposed solution:** Derive review tasks from the question and inspect each
task's focused evidence. Record each relevant duty and qualification separately,
including procedural duties such as submitting a document. Check both directions:
source obligations into the findings, then findings into the answer. Check the
final answer against the original question as well as the generated task list.
Label requested parts as supported, unresolved, or outside the available corpus.

**Success check:** All material obligations in the source-reviewed expectations
are included or explicitly identified as unresolved. Test short and multipart
questions, implicit prerequisites, required documents, exceptions, and follow-ups.
Unrelated obligations must not be added merely to increase apparent coverage.

**Backup trigger:** The topic reviews find the right obligations, but the final
synthesis still drops them; or the planner repeatedly omits requested parts.

**Backup solution:** Produce a short answer for each requested part and assemble
those sections without a final summarization pass. Use clause-level source review
for tasks whose initial findings were incomplete. If the question cannot be
decomposed reliably, retain its full text for review instead of silently losing a
part. Report unresolved parts alongside the supported answer.

## P3 — Differing provisions are overlooked

**Observed:** Retrieved RA passages give one year in the main advance-fee
provision and one quarter in the client-terms annex. The answer reports one year
without acknowledging the difference or establishing which provision controls.

**Proposed solution:** Compare source records concerning the same actor, activity,
client category, and applicable period. Preserve different amounts, deadlines,
conditions, and document locations. Classify whether they concern different
scopes, have an explicitly supported amendment/precedence relationship, or remain
incompatible in the supplied evidence. Draft from that comparison. Do not infer
precedence merely because a passage appears earlier, later, or in an annex.

**Success check:** Disclose the known advance-period discrepancy with both sources.
Also pass negative cases: monthly RTA publication and quarterly issuer filing are
different duties, so their different deadlines do not establish a conflict. Test
changed dates, exceptions, different client categories, and consistent passages.

**Backup trigger:** The comparison misses material differences or invents
conflicts/precedence on the frozen cases.

**Backup solution:** For unresolved topics, display a short comparison of the
relevant source provisions and state what cannot be reconciled from the corpus.
Use a separate comparison of small passage pairs to identify differing explicit
constraints, but do not treat different numbers alone as a contradiction. Preserve
both passages in the answer rather than selecting a winner without support.

## P4 — Relevant evidence is not selected

**Observed:** The MSME amendment effective-date footnote exists in the corrected
index but was absent from the selected context. Full-index presence and retrieval
coverage are separate measurements.

**Proposed solution:** When a requested date, exception, definition, or condition
is missing, form a targeted follow-up search. Expand selected passages to bounded
neighboring chunks, their containing section, or referenced footnotes where
available. Preserve already useful passages. Treat document suggestions as search
hints unless the question explicitly restricts the sources; avoid a mistaken
planner choice excluding the correct document entirely.

**Success check:** Recover the missing effective-date evidence and other reserved
exception/footnote cases without dropping previously covered facts. Measure exact
passage coverage, irrelevant context added, tokens, and latency separately from
the quality of the generated answer. Do not hard-code an MSME-specific search.

**Backup trigger:** The passage remains absent despite targeted retrieval, or
neighbor expansion adds too much unrelated context.

**Backup solution:** Use a bounded parent-section retrieval mode and a lexical
search for the named concept or cross-reference, alongside vector search. If a
required referenced source is outside the corpus, state that gap. If source text
itself is missing, open a separate ingestion defect; further answer prompting
cannot repair absent evidence.

## P5 — Cost, latency, and capacity

**Observed:** Across the recorded five-case comparison, generation input tokens
were 50,996 for the linear pipeline and 150,728 for the workflow. Median total
latency was 6.05 versus 16.86 seconds. These are single-run measurements, not
stable percentiles or a complete bill. The experimental application budget is
35 seconds while nginx currently allows 30 seconds. The existing reranker trial
quota is also a shared capacity constraint; funded Gemini does not remove it.

**Proposed solution:** Record input/output/cache usage, stage latency, call count,
follow-ups, repairs, and refusals. Reuse retrieval results, avoid resending the
entire context to every review, and review only unresolved assertions after repair.
Batch or run independent reviews with a small concurrency limit and provider-aware
pacing. Concurrency can reduce latency but does not itself reduce token cost.
Measure actual bills when available; otherwise label token counts as a cost proxy.

**Success check:** The original engineering targets were aggregate generation
input below twice the matched linear baseline and median latency below 12
seconds while meeting quality checks. On 4 October, the user accepted longer
answers when actual workflow stages are visible. Treat those numbers as cost and
latency comparison points, not release blockers; quality, bounded expense,
operational timeouts, and truthful progress still matter. Record every timeout
and tail latency; a small sample cannot establish a reliable p95. Keep explicit
call/retry/context limits.

**Backup trigger:** Quality improves but duplicated work still exceeds those
targets, or quota/timeout failures make the approach unsuitable for the site.

**Backup solution:** Test a simpler path: retrieve, extract relevant source rules,
draft, and run focused checks only for unresolved parts. Use the ordinary path
for questions that do not benefit from decomposition. Compare the quality/cost
tradeoff before choosing a route. If the reranker quota remains limiting, benchmark
hybrid retrieval without it before considering a paid quota change. A rate-limit
error must remain a service error, not be disguised as missing evidence.

**Before rollout:** Align application, proxy, and browser timeouts, with room for
the application to return a controlled response first. Increasing a timeout is
not evidence that the workflow became fast enough. Verify failure handling and
capacity with a small paced smoke run.

## P6 — Evaluation and generalisation

**Current limitation:** Five known complex questions, keyword patterns, and the
pipeline's own model reviewer are insufficient evidence of general reliability.
Some existing patterns are too strict: an allowed website-or-email alternative
must not fail just because the answer gives only the permitted website option.

**Proposed solution:** Before changing prompts, freeze explicit source-based
expectations: required facts and qualifications, applicable entities, supported
calculations, forbidden inferences, and acceptable gaps/refusals. Use the existing
five complex cases for development. Reserve a separate initial set of ten new
questions across at least four topic families, including ordinary questions and
negative cases, for final comparison. Do not inspect/tune against their results
during development. A case used to guide a fix becomes a regression case and
must be replaced in the held-out set.

Test with two complementary methods:

- End-to-end questions with manually checked source evidence, including changed
  scenario facts, different wording, irrelevant passages, and conflicting scopes.
- Deliberately corrupted answers: remove an obligation or exception, strengthen
  permission into certainty, swap an entity, or change a period. Keep correct
  controls so a reviewer that rejects everything cannot appear successful.

Run the unchanged baseline and candidate under the same model/index settings.
Use controlled context replay to isolate interpretation changes, then real
retrieval to assess the full system. Once a candidate passes development checks,
run the held-out comparison three times per question to expose inconsistent
behavior. Record partial answers and false refusals as well as wrong assertions.
Source review decides semantic results; keyword checks and model judges only help
find cases needing inspection. Preserve raw answers, selected passages, and traces.

**Success check:** No material unsupported assertion or hidden material omission
in the reviewed release set; improvement in complete, supported answers without
an increase in false refusals. Existing ordinary regressions must continue to pass.
Publish the sample size and failures; this does not prove correctness for every
future question. Check that new or revised workflow prompts contain no answers,
clause numbers, or entity-specific branches copied from the evaluation cases.

**Backup trigger:** Gains disappear on held-out questions, graders disagree, or
success comes mainly from refusing harder questions.

**Backup solution:** Keep the workflow disabled, narrow the proposed rollout to
the behaviors supported by evidence, and use source-reviewed release checks.
Diagnose the failing stage before another implementation change. Do not keep
tuning against a supposedly held-out set or substitute a passing software-test
count for answer quality.

## P7 — Finish and verify the UI

**Current state:** Responsive layout and citation handling have already improved.
The remaining work is a focused audit after the answer/refusal behavior settles;
this plan does not claim new UI bugs have been reproduced.

**Proposed solution:** Use Playwright to test loading and retry behavior, long
answers, distinct quotes from one document, source navigation, over-limit questions,
partial answers, conflicting sources, provider errors, and IP rate limits. Check
mobile/desktop layouts, keyboard navigation, and screen-reader status announcements.
Show real progress/status and preserve the user's question when a request fails.

**Success check:** Each state has a clear result and a usable next action; source
links match the answer, the draft is retained on failure, and core interactions
work at the tested viewport sizes and with a keyboard. Keep screenshots and the
scenario checklist as evidence.

**Backup trigger:** A richer progress or source-inspection design makes the UI
confusing, fragile, or difficult to use on small screens.

**Backup solution:** Use a plain answer divided by requested part, a simple source
list, one accurate status message, and explicit retry. Retain working interactions
while revising any failed enhancement individually.

## Implementation order and rollout

1. **P6 first:** Freeze expectations, development/held-out splits, and measurement
   fields. Capture the current baseline under those conditions.
2. **P2 + P3:** Implement dynamic topic reviews and explicit obligation/comparison
   records. Test their effect independently of a new final verifier.
3. **P1:** Add assertion-level checks, including mixed sentences and coverage.
   Test repairs and the constrained-source fallback.
4. **P4:** Improve retrieval only for evidenced selection failures. Keep the
   deployed chunking fixed unless an actual extraction/chunking defect is found.
5. **P5:** Measure throughout; optimize the useful candidate after it improves
   quality. Try the simpler backup if cost or latency is still disproportionate.
6. **P6 final comparison:** Run the frozen held-out cases and ordinary regressions.
   If results fail a gate, record the failure and keep the feature disabled.
7. **P7 and rollout:** Verify UI/error behavior and align timeouts. Enable only
   after the quality and operational checks pass. Perform public-site smoke tests;
   retain the feature flag so a failed rollout can return to the deployed path.

Try one backup at a time, against the same evidence, when its trigger is observed.
Do not combine every fallback into a larger workflow. Record any change in scope,
quality, cost, or usability introduced by a backup.

## Progress log

| Date | IDs | Action/result | Next step |
| --- | --- | --- | --- |
| 2026-10-03 | P1–P7 | Created tracker from recorded failures and current code. No implementation or evaluation changes in this update. | Freeze the P6 evaluation criteria before revising the workflow. |
| 2026-10-03 | P2, P3, P6 | Froze five development cases and ten new held-out scenarios. Implemented bounded source-focused reviews for each dynamically planned topic, source-ID validation, and review of any follow-up retrieval before drafting. Focused software tests passed; live semantic evaluation is in progress. | Inspect development-case answers and costs; keep held-out cases sealed until the approach passes that gate. |
| 2026-10-04 | P1–P6 | Commit `c7fe4f5` adds sectioned drafting, proposal-value guard, clause review, source-pair scope checks, bounded topic reviews, and replay mode. Five selected development replays passed keyword screens and were manually inspected; one controlled discretionary claim test passed. The replay median is 15.35 seconds and the full IA/RA trial exceeded the proxy timeout. 161 tests and Ruff pass. Artifacts and limitations are above. | Keep the workflow disabled; try the P5 simpler path and verify P4 retrieval before any held-out or rollout gate. |
| 2026-10-04 | P1–P6 | Uncommitted candidate adds bounded verifier batches, nearby lexical follow-up, generic linear prompt, and Lite retrieval planner option. One fresh five-case 3.8 Flash linear run answered all five at 7.57-second median and 40,736 generation-input tokens; 176 tests and Ruff pass. Held-out unopened. | Run corruption and retrieval controls, repeat semantic development review, then held-out/operational/UI gates. |
| 2026-10-04 | P1–P7 | Resumed candidate adds full-context gap adjudication, quantity-diverse source comparisons, live workflow events, and proxy support. Withheld-footnote probe recovered the source; five development questions avoided false follow-ups at 21.91-second median and estimated $0.188 Gemini generation cost. Two focused IA/RA repeats disclosed the unresolved periods. Backend 196 tests, Ruff, UI lint/build pass. Frozen held-out run started after development gate. | Complete matched-model held-out comparison and source review; decide route, then production/browser smoke checks. |
| 2026-10-04 | P1–P7 | Uncommitted candidate on `feat/bounded-multipart-workflow`: revised held-out SHA recorded above, graph and matched linear route each met 10/10 written expectations in three runs. NCS historical-footnote regression answered in three consecutive graph runs after full-chunk context fix. Five complex development cases answered on both routes; graph used about six times the generation input tokens and twice the median time. Fresh IA/RA and RTA graph checks remained source-consistent. 191 local tests passed, 6 database checks skipped; Ruff, UI lint/build, and fixture smoke passed. | Commit and run CI with PostgreSQL, configure feature flags, deploy, then source-review production samples and inspect browser states. |

For each experiment, append its commit, model/index versions, dataset/split, artifact
path, measured result, and decision. Use statuses: Open, In progress, Implemented
but unverified, Validated locally, Deployed and checked, or Deferred with reason.
