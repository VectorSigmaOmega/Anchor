"""Measure source-scoped evidence in candidate pools and final answer context.

These literal evidence checks are retrieval diagnostics, not semantic grades.
Manual answer review is recorded separately in the experiment report.
"""

import json
import re
from pathlib import Path
from statistics import median

from scripts.prepare_chunking_experiment import ROOT


def normalized(text):
    return re.sub(r"(?<=\d),(?=\d)", "", " ".join(text.split())).replace("–", "-")


def evidence_checks(facts, chunks):
    rows = []
    for fact in facts:
        found = [
            c["chunk_id"]
            for c in chunks
            if c["doc_id"] == fact["doc_id"]
            and re.search(
                " ".join(fact["pattern"].split()).replace("–", "-"),
                normalized(c["text"]),
                re.I,
            )
        ]
        rows.append({**fact, "found_in": found, "present": bool(found)})
    return rows


def main():
    facts = json.loads(Path("eval/chunking_evidence.json").read_text())
    selected_ids = {json.loads(line)["id"] for line in Path("eval/chunking_quality.jsonl").read_text().splitlines()}
    summaries = {}
    annotated = []
    for strategy in ["baseline", "fixed", "structured"]:
        path = ROOT / (strategy + ".answers.jsonl")
        if not path.exists():
            continue
        rows = [row for line in path.read_text().splitlines() if (row := json.loads(line))["id"] in selected_ids]
        evidence_total = context_found = candidate_found = 0
        complete_evidence = 0
        for row in rows:
            expected = facts.get(row["id"], [])
            context = evidence_checks(expected, row.get("context", []))
            candidates = evidence_checks(expected, row.get("candidates", []))
            evidence_total += len(expected)
            context_found += sum(f["present"] for f in context)
            candidate_found += sum(f["present"] for f in candidates)
            complete_evidence += bool(expected) and all(f["present"] for f in context)
            annotated.append(
                {
                    "strategy": strategy,
                    "id": row["id"],
                    "context_evidence": context,
                    "candidate_evidence": candidates,
                    "context_words": sum(len(c["text"].split()) for c in row.get("context", [])),
                }
            )
            print(
                json.dumps(
                    {
                        "strategy": strategy,
                        "id": row["id"],
                        "context_found": sum(f["present"] for f in context),
                        "expected": len(expected),
                        "missing": [f["doc_id"] + ":" + f["fact"] for f in context if not f["present"]],
                    }
                )
            )
        summaries[strategy] = {
            "cases": len(rows),
            "runtime_errors": sum("error" in r for r in rows),
            "pattern_checks_passed": sum(not r.get("pattern_failures") for r in rows),
            "context_evidence_found": context_found,
            "candidate_evidence_found": candidate_found,
            "evidence_total": evidence_total,
            "complete_evidence_cases": complete_evidence,
            "median_seconds_excluding_planning_embedding": median(r["elapsed_seconds"] for r in rows),
            "context_words": sum(sum(len(c["text"].split()) for c in r.get("context", [])) for r in rows),
            "generation_input_tokens": sum(u.get("promptTokenCount", 0) for r in rows for u in r.get("generation_usages", [])),
            "generation_output_tokens": sum(u.get("candidatesTokenCount", 0) for r in rows for u in r.get("generation_usages", [])),
            "generation_thinking_tokens": sum(u.get("thoughtsTokenCount", 0) for r in rows for u in r.get("generation_usages", [])),
        }
    (ROOT / "retrieval-evidence.json").write_text(json.dumps(annotated, indent=2))
    (ROOT / "results-summary.json").write_text(json.dumps(summaries, indent=2))
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
