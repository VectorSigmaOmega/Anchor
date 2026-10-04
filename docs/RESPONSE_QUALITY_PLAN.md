# Response quality improvement tracker

Updated: 4 October 2026. Owner: Codex with Abhinash.

This file tracks the remaining work, the first approach to each problem, how to
judge the result, and a backup if the first approach fails. Proposed changes below
are tracked separately from the implementation status. Several first approaches
are implemented on the disabled workflow branch, but none has passed the release
gate. Status changes must link to code and recorded results; implementing a change
is not the same as resolving its problem.

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
- The 161 passing software tests establish software behavior, not factual
  correctness. The 27 ordinary regression checks and five complex comparison
  questions provide limited evidence of answer quality.
- **Frozen development cases:** `eval/workflow_quality.jsonl` (five cases), SHA-256
  `2a287f6d2be34388a6f61b4ba85fa060426620b8cc678415eab78af9fce652`.
  They may guide implementation and become regression tests.
- **Frozen held-out cases:** `eval/workflow_holdout.jsonl` (ten new scenarios across
  KYC, mutual funds, ICDR, SSE, NCS, and one outside-corpus request), SHA-256
  `50bd21200d517631cd64fad3f2e16d999c223e957cec4e12891f0d5153bdb695`.
  Its `must_include`, `must_not_claim`, and source page fields are the review
  rubric. Its empty regex-pattern lists intentionally avoid treating keywords as
  semantic grades. Do not inspect candidate answers or tune against these cases
  before the final development-case gate.

## Work list

| ID | Problem | Status | First approach | Backup |
| --- | --- | --- | --- | --- |
| P1 | Incorrect assertions pass verification | In progress; clause checks and one live corrupted-claim control pass | Check each independent assertion against its own source rule | Render difficult parts directly from verified source records/excerpts |
| P2 | Relevant obligations and requested details disappear | In progress; focused reviews, sectioned answers, and proposal-value guard implemented | Dynamic review tasks with obligation and answer coverage checks | Answer requested parts separately, then assemble without resummarizing |
| P3 | Differing provisions are overlooked or incorrectly reconciled | In progress; pair comparison and scope labeling implemented | Compare rules about the same activity and applicable scope | Present unresolved source provisions side by side with citations |
| P4 | Relevant passages exist but are not selected | In progress; follow-up retrieval re-reviewed, neighboring/reference expansion pending | Targeted follow-up retrieval and nearby/reference expansion | Retrieve a bounded parent section with lexical and document-aware search |
| P5 | Extra calls increase cost, latency, and capacity pressure | Open; current candidate exceeds latency/token targets | Reduce duplicated context/calls and measure per-stage usage | Use a simpler evidence-first path and restrict costly reviews to unresolved parts |
| P6 | Evaluation is too narrow to establish generalisation | In progress; five development replays inspected, held-out set frozen and untouched | Freeze source-reviewed development and held-out sets | Narrow rollout scope and retain source-reviewed/manual release checks |
| P7 | Remaining UI states need refinement and verification | Pending audit; no new defect claimed | Test loading, citations, errors, partial answers, and responsive behavior | Use a simpler answer/status/source presentation if richer interactions fail |

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

**Success check:** Initial engineering targets are aggregate generation input
below twice the matched linear baseline and median latency below 12 seconds while
meeting the quality checks. These are proposed targets, not user-approved spending
limits or reported results. Record every timeout and tail latency; a small sample
cannot establish a reliable p95. Keep explicit call/retry/context limits.

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

For each experiment, append its commit, model/index versions, dataset/split, artifact
path, measured result, and decision. Use statuses: Open, In progress, Implemented
but unverified, Validated locally, Deployed and checked, or Deferred with reason.
