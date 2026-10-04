# Bounded LangGraph workflow — 3 October 2026

The prototype is implemented and tested, but **disabled by default** and not
ready for production rollout. The five-question comparison shows improvements
in some coverage and calculations, alongside missed material facts, inconsistent
claim verification and substantially higher token use. LangGraph provides the
control flow; it does not make the underlying model a reliable judge.

Remaining problems, proposed fixes, fallback approaches, and acceptance checks
are tracked in the [response quality plan](RESPONSE_QUALITY_PLAN.md).

## Implementation

Multipart Gemini requests can opt into a request-local StateGraph:

1. Plan two to six searches covering requested parts.
2. Retrieve with the existing hybrid search, support thresholds and topic balancing.
3. Build an evidence ledger and identify up to two missing-evidence searches.
4. Run at most one targeted retrieval follow-up while retaining established context.
5. Draft using generic source-grounding instructions, without IA/RA-specific rules.
6. Check citation validity and every exact draft claim against source evidence,
   including missing requested parts and incompatible explicit requirements.
7. Repair once, then check again. Return an empty refusal if verification still fails.

Claims are server-numbered contiguous sentences/groups, so the verifier cannot
silently substitute a corrected paraphrase for the claim it is judging. Its
identified evidence must exist; a discretionary/conditional source classified
against a mandatory draft triggers a repair even if the model marks it supported.
Those classifications are themselves model judgments and can be wrong.

The repair prompt discards preliminary ledger findings, which can contain the
original error. The final source quotes remain server-hydrated and strictly
validated. Review summaries are internal reasoning aids, not source quotations.
The graph has no persistent memory or unbounded loops and does not share state
between requests. It uses the existing Gemini 3.5 Flash Lite multipart model,
low thinking, and Gemini Embedding 2. Ordinary requests retain their existing path.

`MULTIPART_WORKFLOW_ENABLED` defaults to false. An opt-in multipart request has a
35-second overall budget, versus the existing 25-second ordinary budget. This is
an experimental server setting; an eventual rollout must also give the reverse
proxy enough time (currently 30 seconds). No production timeout was changed.

The implementation follows the official [LangGraph graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
with a compiled StateGraph, conditional edges and bounded request-local state.

## Controlled comparison

The same corrected 4,012-chunk local index, Gemini 3.5 Flash Lite, reranker and
4,096-token answer limit were used for both pipelines. All searches, planning,
provider calls and verification are included in timing. The linear pipeline uses
the deployed prompts; the workflow introduces generic prompts and additional
checks. This measures that combined intervention, not LangGraph alone.

The [five questions](../eval/workflow_quality.jsonl) cover three-bank PSL targets,
currency-chest incentives/penalties, RTA versus listed-issuer reporting,
NBFC deposits plus company beneficial ownership, and the original IA/RA scenario.
Facts are source-reviewed. Keyword patterns are diagnostics, not semantic grades.

| Question | Linear result | Exact-claim workflow result | Linear / workflow time |
| --- | --- | --- | --- |
| Three bank types | Correct targets/calculations; measurement basis omitted | Requested checked passages covered | 7.31 / 15.85 s |
| Currency chest | Outside-NE calculation omitted; discretion strengthened | Initial errors detected; still refused after one repair | 6.01 / 24.69 s |
| RTA/issuer reporting | Supported answer | Supported deadlines and distinct scopes; email pattern absent | 5.71 / 16.86 s |
| NBFC/company KYC | Supported answer | Supported limits, ownership and independent control | 6.05 / 15.97 s |
| IA/RA scenario | Refused | Answered, but undertaking and RA source inconsistency omitted | 16.69 / 23.89 s |

The RTA email pattern is overly strict: source wording permits website **or**
email dissemination. Its failure alone does not establish an incorrect answer.
The currency and IA/RA problems are substantive. IA/RA context includes the
one-quarter MITC passage alongside the main one-year rule, but the ledger and
verifier miss the incompatibility. The explicit undertaking is also lost while
its underlying separation duties are described.

A subsequent currency-chest repair experiment removed preliminary findings from
repair notes. It answered in 18.80 seconds and passed patterns, but manual review
still found an automatic Rs 50,000 penalty where the source says one **may** be
levied. The verifier accepted it. That is why the prototype remains disabled;
passing patterns and a model's positive judgment do not establish correctness.
Earlier review versions also hit malformed evidence references and quote
reconstruction errors; the current code maps numeric draft references to source
IDs and uses internal summaries rather than reconstructed quotes.

Generation prompt tokens across these five cases were 50,996 for the linear
pipeline and 150,728 for the exact-claim workflow (including planning, ledgers,
verification and repairs). Median end-to-end time was 6.05 versus 16.86 seconds.
One run per question does not establish stable latency or accuracy rates. These
results do not justify enabling this workflow as implemented.

## Validation and next change

The full local suite passed 145 tests before three additional focused guard tests;
all 12 focused workflow/provider tests then passed. CI run 37154608046 passed all
148 tests, including six PostgreSQL integration tests, plus lint, UI export, smoke
evaluation and Docker build. The added guards cover complete exact-claim review,
discretion mismatch and removal of faulty ledger notes during repair. Tests establish
control flow and guard behavior, not the correctness of Gemini's source interpretation.

All 27 existing ordinary-question regression checks passed on the corrected index
with normal configured model routing. Production chunking rollout passed CI and
completed atomic reindex through deployment run 37153435797. PostgreSQL confirms
16 active documents with `layout-structured-v2` and 4,012 chunks; readiness passes.
Playwright submitted an MSME question on the public site and saw the restored
Rs 20 lakh/Rs 25 lakh limits and linked source. This is a focused functional check,
not a comprehensive semantic certification of that generated answer.

The next architecture change should give each planned topic a small, explicit
source set, compare overlapping provisions within that set, and consolidate the
resulting evidence. That addresses buried conditions and conflicts before drafting,
instead of relying on one broad-context ledger and a second broad-context judge.
Keep the same model while testing that change so the comparison stays useful.

[Recorded answers, context and traces](../eval/reports/workflow-2026-10-03.jsonl)
contain public source text and synthetic questions, with no credentials or user
chat exports. The original first comparison, diagnostic iterations and selected
repair follow-up remain in ignored `.benchmarks/workflow` for reproducibility.

```bash
PYTHONPATH=.benchmarks/workflow/lib python -m scripts.evaluate_workflow
```

A normal environment installed from the project does not need PYTHONPATH. The
local experiment used an isolated dependency directory to preserve the other
worktrees' Python environment. The script compares linear/workflow variants,
records all Gemini usage and traces, resumes completed cases, and pauses between
questions to respect the trial reranker quota. Use a fresh output path for a fresh
rerun. It requires the existing isolated `anchor_chunking_structured` local DB.
