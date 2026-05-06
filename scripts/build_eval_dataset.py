from __future__ import annotations

import json
from pathlib import Path

DATA = [
    {
        "doc_id": "sebi_mutual_funds_2026",
        "regulator": "SEBI",
        "title": "Master Circular for Mutual Funds",
        "topic": "mutual fund regulation and operations",
        "section_path": "Master Circular for Mutual Funds",
        "summary": "It is the SEBI master circular that consolidates operational requirements for mutual funds.",
    },
    {
        "doc_id": "sebi_icdr_2026",
        "regulator": "SEBI",
        "title": "Master Circular for Issue of Capital and Disclosure Requirements",
        "topic": "capital issuance and disclosure requirements",
        "section_path": "Master Circular for Issue of Capital and Disclosure Requirements",
        "summary": "It is the SEBI master circular covering issue of capital and disclosure requirements.",
    },
    {
        "doc_id": "sebi_research_analysts_2026",
        "regulator": "SEBI",
        "title": "Master Circular for Research Analysts",
        "topic": "research analyst compliance requirements",
        "section_path": "Master Circular for Research Analysts",
        "summary": "It is the SEBI master circular for research analyst obligations and compliance.",
    },
    {
        "doc_id": "sebi_investment_advisers_2026",
        "regulator": "SEBI",
        "title": "Master Circular for Investment Advisers",
        "topic": "investment adviser compliance requirements",
        "section_path": "Master Circular for Investment Advisers",
        "summary": "It is the SEBI master circular for investment adviser obligations and compliance.",
    },
    {
        "doc_id": "sebi_rta_2026",
        "regulator": "SEBI",
        "title": "Master Circular for Registrars to an Issue and Share Transfer Agents",
        "topic": "registrars to an issue and share transfer agents",
        "section_path": "Master Circular for Registrars to an Issue and Share Transfer Agents",
        "summary": "It is the SEBI master circular for registrars to an issue and share transfer agents.",
    },
    {
        "doc_id": "sebi_lodr_listed_entities_2026",
        "regulator": "SEBI",
        "title": "Master Circular for compliance with the provisions of the Securities and Exchange Board of India (Listing Obligations and Disclosure Requirements) Regulations, 2015 by listed entities",
        "topic": "listed entity compliance under the LODR regulations",
        "section_path": "Master Circular for compliance with the provisions of the Securities and Exchange Board of India (Listing Obligations and Disclosure Requirements) Regulations, 2015 by listed entities",
        "summary": "It is the SEBI master circular for listed entity compliance under the LODR regulations.",
    },
    {
        "doc_id": "sebi_social_stock_exchange_2026",
        "regulator": "SEBI",
        "title": "Master Circular for Framework on Social Stock Exchange.",
        "topic": "the social stock exchange framework",
        "section_path": "Master Circular for Framework on Social Stock Exchange.",
        "summary": "It is the SEBI master circular for the social stock exchange framework.",
    },
    {
        "doc_id": "sebi_ncs_listing_2025",
        "regulator": "SEBI",
        "title": "Master Circular for issue and listing of Non-convertible Securities, Securitised Debt Instruments, Security Receipts, Municipal Debt Securities and Commercial Paper",
        "topic": "issue and listing requirements for non-convertible securities and related debt instruments",
        "section_path": "Master Circular for issue and listing of Non-convertible Securities, Securitised Debt Instruments, Security Receipts, Municipal Debt Securities and Commercial Paper",
        "summary": "It is the SEBI master circular for issue and listing of non-convertible securities and related debt instruments.",
    },
    {
        "doc_id": "rbi_psl_sfb_2019",
        "regulator": "RBI",
        "title": "Master Direction – Priority Sector Lending – Small Finance Banks – Targets and Classification",
        "topic": "priority sector lending targets for small finance banks",
        "section_path": "Master Direction – Priority Sector Lending – Small Finance Banks – Targets and Classification",
        "summary": "It is the RBI master direction on priority sector lending targets and classification for small finance banks.",
    },
    {
        "doc_id": "rbi_currency_chest_penal_interest_2019",
        "regulator": "RBI",
        "title": "Master Direction on Levy of Penal Interest for Delayed Reporting / Wrong Reporting / Non-Reporting of Currency Chest Transactions and Inclusion of Ineligible Amounts in Currency Chest Balances",
        "topic": "penal interest for currency chest reporting failures",
        "section_path": "Master Direction on Levy of Penal Interest for Delayed Reporting / Wrong Reporting / Non-Reporting of Currency Chest Transactions and Inclusion of Ineligible Amounts in Currency Chest Balances",
        "summary": "It is the RBI master direction covering penal interest for currency chest reporting failures.",
    },
    {
        "doc_id": "rbi_cdes_2019",
        "regulator": "RBI",
        "title": "Master Direction on Currency Distribution & Exchange Scheme (CDES) based on performance in rendering customer service to the members of public",
        "topic": "the currency distribution and exchange scheme tied to customer service",
        "section_path": "Master Direction on Currency Distribution & Exchange Scheme (CDES) based on performance in rendering customer service to the members of public",
        "summary": "It is the RBI master direction on the currency distribution and exchange scheme linked to customer service.",
    },
    {
        "doc_id": "rbi_rrb_psl_2016",
        "regulator": "RBI",
        "title": "Master Direction - Regional Rural Banks - Priority Sector Lending - Targets and Classification",
        "topic": "priority sector lending targets for regional rural banks",
        "section_path": "Master Direction - Regional Rural Banks - Priority Sector Lending - Targets and Classification",
        "summary": "It is the RBI master direction on priority sector lending targets and classification for regional rural banks.",
    },
    {
        "doc_id": "rbi_kyc_2016",
        "regulator": "RBI",
        "title": "Master Direction - Know Your Customer (KYC) Direction, 2016",
        "topic": "know your customer and customer due diligence requirements",
        "section_path": "Master Direction - Know Your Customer (KYC) Direction, 2016 > Customer Due Diligence (CDD) Procedure",
        "summary": "It is the RBI KYC direction covering customer identification, due diligence, and related AML controls.",
    },
    {
        "doc_id": "rbi_msme_2017",
        "regulator": "RBI",
        "title": "Master Direction - Lending to Micro, Small & Medium Enterprises (MSME) Sector",
        "topic": "bank lending to the MSME sector",
        "section_path": "Master Direction - Lending to Micro, Small & Medium Enterprises (MSME) Sector",
        "summary": "It is the RBI master direction covering bank lending to the MSME sector.",
    },
    {
        "doc_id": "rbi_nbfc_public_deposits_2016",
        "regulator": "RBI",
        "title": "Master Direction - Non-Banking Financial Companies Acceptance of Public Deposits (Reserve Bank) Directions, 2016",
        "topic": "acceptance of public deposits by non-banking financial companies",
        "section_path": "Master Direction - Non-Banking Financial Companies Acceptance of Public Deposits (Reserve Bank) Directions, 2016",
        "summary": "It is the RBI master direction governing acceptance of public deposits by eligible non-banking financial companies.",
    },
    {
        "doc_id": "rbi_psl_2016",
        "regulator": "RBI",
        "title": "Master Direction - Priority Sector Lending – Targets and Classification",
        "topic": "priority sector lending targets and classification for scheduled commercial banks",
        "section_path": "Master Direction - Priority Sector Lending – Targets and Classification",
        "summary": "It is the RBI master direction on priority sector lending targets and classification for scheduled commercial banks.",
    },
]

EXTRA_DOC_IDS = {
    "sebi_mutual_funds_2026",
    "sebi_lodr_listed_entities_2026",
    "sebi_research_analysts_2026",
    "rbi_kyc_2016",
    "rbi_msme_2017",
    "rbi_psl_2016",
}

REFUSAL_QUESTIONS = [
    "What does the Income Tax Act say about depreciation on software?",
    "How is GST applied to cross-border SaaS sales?",
    "What is the Companies Act rule for board quorum in a private company?",
    "What labour law notice period is required for factory layoffs?",
    "What does the Insolvency and Bankruptcy Code say about homebuyers?",
    "How should a startup value ESOPs under tax law?",
    "What is the FEMA rule for export invoice realization timelines not covered in the indexed docs?",
    "What stamp duty applies to a share transfer in Maharashtra?",
    "How is TDS calculated on contractor payments?",
    "What are the merger filing thresholds under the Competition Act?",
    "What is the latest customs duty on imported semiconductors?",
    "How does Indian patent law define inventive step?",
    "What is the SEZ rule for net foreign exchange calculations?",
    "How is gratuity computed for a five-year employee?",
    "What is the penal provision for cheque bounce under the NI Act?",
    "How is professional tax calculated in Karnataka?",
    "What disclosure is required under the Companies Act for related-party loans?",
    "What FEMA route applies to overseas direct investment for a software company outside the indexed corpus?",
    "What are the RBI rules on UPI chargeback timelines in the unindexed payments corpus?",
    "What tax treatment applies to mutual fund capital gains?",
]

AMBIGUOUS_QUESTIONS = [
    "What does this circular require?",
    "What does that master direction say about reporting?",
    "What are the rules in the latest one?",
    "Can you explain this rule for listed entities?",
    "What does that RBI document say for banks?",
    "What is the disclosure rule in that circular?",
    "How does the same direction treat customers?",
    "What should be filed under this framework?",
    "What does the recent circular change here?",
    "What are the obligations under that one?",
]


def build_answer_rows() -> list[dict]:
    rows: list[dict] = []
    for item in DATA:
        base = {
            "reference_citations": [
                {
                    "doc_id": item["doc_id"],
                    "section_path": item["section_path"],
                }
            ],
            "regulator": item["regulator"],
            "doc_ids": [item["doc_id"]],
        }
        rows.extend(
            [
                {
                    "id": f"{item['doc_id']}_01",
                    "question": f"Which document in Anchor's corpus should I consult for {item['topic']}?",
                    "expected_outcome": "answer",
                    "reference_answer": item["title"] + ". " + item["summary"],
                    "difficulty": "easy",
                    "notes": "document lookup",
                    **base,
                },
                {
                    "id": f"{item['doc_id']}_02",
                    "question": f"Is {item['topic']} covered by RBI or SEBI in Anchor's corpus?",
                    "expected_outcome": "answer",
                    "reference_answer": f"It is covered by {item['regulator']} in the document titled '{item['title']}'.",
                    "difficulty": "easy",
                    "notes": "regulator identification",
                    **base,
                },
                {
                    "id": f"{item['doc_id']}_03",
                    "question": f"What is the main subject of the document titled '{item['title']}'?",
                    "expected_outcome": "answer",
                    "reference_answer": item["summary"],
                    "difficulty": "medium",
                    "notes": "topic summary",
                    **base,
                },
                {
                    "id": f"{item['doc_id']}_04",
                    "question": f"Does Anchor include an official master document on {item['topic']}?",
                    "expected_outcome": "answer",
                    "reference_answer": f"Yes. Anchor includes '{item['title']}', an official {item['regulator']} master document on {item['topic']}.",
                    "difficulty": "medium",
                    "notes": "corpus presence",
                    **base,
                },
            ]
        )
        if item["doc_id"] in EXTRA_DOC_IDS:
            rows.append(
                {
                    "id": f"{item['doc_id']}_05",
                    "question": f"What should a reviewer open first if they want the Anchor corpus source for {item['topic']}?",
                    "expected_outcome": "answer",
                    "reference_answer": f"They should open '{item['title']}', which is the indexed source document for {item['topic']}.",
                    "reference_citations": base["reference_citations"],
                    "regulator": item["regulator"],
                    "doc_ids": base["doc_ids"],
                    "difficulty": "hard",
                    "notes": "reviewer path",
                }
            )
    return rows


def build_refusal_rows() -> list[dict]:
    rows: list[dict] = []
    for index, question in enumerate(REFUSAL_QUESTIONS, start=1):
        rows.append(
            {
                "id": f"refusal_{index:02d}",
                "question": question,
                "expected_outcome": "refusal",
                "reference_answer": "",
                "reference_citations": [],
                "regulator": "none",
                "doc_ids": [],
                "difficulty": "medium",
                "notes": "out_of_corpus",
            }
        )
    for index, question in enumerate(AMBIGUOUS_QUESTIONS, start=1):
        rows.append(
            {
                "id": f"ambiguous_{index:02d}",
                "question": question,
                "expected_outcome": "refusal",
                "reference_answer": "",
                "reference_citations": [],
                "regulator": "none",
                "doc_ids": [],
                "difficulty": "hard",
                "notes": "ambiguous",
            }
        )
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=True) for row in rows) + "\n")


def main() -> None:
    answer_rows = build_answer_rows()
    refusal_rows = build_refusal_rows()
    golden_rows = answer_rows + refusal_rows
    smoke_rows = answer_rows[:8] + refusal_rows[:4] + refusal_rows[20:23]

    write_jsonl(Path("eval/golden.jsonl"), golden_rows)
    write_jsonl(Path("eval/smoke.jsonl"), smoke_rows)
    print(f"golden={len(golden_rows)} smoke={len(smoke_rows)}")


if __name__ == "__main__":
    main()
