"""Source checks before comparing experimental indexes."""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import fitz

from scripts.analyze_chunking import evidence_checks, normalized
from scripts.prepare_chunking_experiment import ROOT


def main():
    facts = json.loads(Path("eval/chunking_evidence.json").read_text())
    audit = []
    raw_texts = {}
    for file in sorted(ROOT.glob("*.parsed.json")):
        parsed = json.loads(file.read_text())
        doc = parsed["document"]["doc_id"]
        by_page = defaultdict(list)
        for block in parsed["blocks"]:
            by_page[block["page"]].append(block["text"])
        pdf = fitz.open(ROOT / "raw" / (doc + ".pdf"))
        losses = []
        texts = []
        for page_number, page in enumerate(pdf, 1):
            raw = page.get_text()
            texts.append(raw)
            before = Counter(c.lower() for c in raw if c.isalnum())
            after = Counter(c.lower() for c in " ".join(by_page[page_number]) if c.isalnum())
            lost = before - after
            if lost:
                losses.append({"page": page_number, "missing_characters": dict(lost)})
        raw_texts[doc] = normalized(" ".join(texts))
        audit.append({"doc_id": doc, "pages": len(pdf), "pages_with_missing_characters": losses})
    absent_from_source = [
        {"case": case, **fact}
        for case, expected in facts.items()
        for fact in expected
        if not re.search(fact["pattern"], raw_texts[fact["doc_id"]], re.I)
    ]
    inventories = {}
    for strategy in ["fixed", "structured"]:
        chunks = [json.loads(line) for line in (ROOT / (strategy + ".chunks.jsonl")).read_text().splitlines()]
        inventories[strategy] = {
            case: [f["fact"] for f in evidence_checks(expected, chunks) if not f["present"]] for case, expected in facts.items()
        }
    result = {"character_audit": audit, "facts_absent_from_source": absent_from_source, "facts_not_in_one_indexed_chunk": inventories}
    (ROOT / "source-audit.json").write_text(json.dumps(result, indent=2))
    print(
        json.dumps(
            {
                "pages": sum(row["pages"] for row in audit),
                "pages_with_character_loss": sum(len(row["pages_with_missing_characters"]) for row in audit),
                "facts_absent_from_source": absent_from_source,
                "index_fact_gaps": {s: {c: f for c, f in cases.items() if f} for s, cases in inventories.items()},
            }
        )
    )
    if absent_from_source or any(row["pages_with_missing_characters"] for row in audit):
        raise SystemExit("Source audit failed")


if __name__ == "__main__":
    main()
