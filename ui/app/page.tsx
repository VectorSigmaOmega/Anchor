"use client";

import {
  ArrowRight,
  Ban,
  ChevronDown,
  Database,
  ExternalLink,
  FileText,
  Moon,
  Search,
  ShieldCheck,
  Sun,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import "./landing.css";

type AppearanceMode = "light" | "dark";

function AnchorGlyph({ size = 16 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={(size * 18) / 16}
      viewBox="0 0 24 26"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="4" r="2.4" />
      <line x1="12" y1="6.4" x2="12" y2="22" />
      <line x1="7" y1="11" x2="17" y2="11" />
      <path d="M4 15c0 5 3.6 7.6 8 7.6s8-2.6 8-7.6" />
    </svg>
  );
}

const EXAMPLES = [
  "What customer due diligence steps apply to individual customers?",
  "What must a research analyst disclose in a research report?",
  "When may an MSME loan be restructured under RBI directions?",
];

const FAQS = [
  {
    question: "What is in the corpus?",
    answer:
      "The corpus has 16 official documents in English: 8 RBI Master Directions and 8 SEBI Master Circulars. The manifest gives the source URL, hash and snapshot date for each document. Anchor does not search superseded documents.",
  },
  {
    question: "What happens if the corpus does not have the answer?",
    answer:
      "Anchor gives a refusal with the reason: not in corpus, insufficient support or ambiguous question. It does not answer from model memory.",
  },
  {
    question: "Can I add my own documents?",
    answer:
      "No. The manifest controls the corpus. File upload, accounts and other languages are outside the current scope. Tax law is also outside the scope.",
  },
  {
    question: "Does Anchor store my conversation?",
    answer:
      "Anchor keeps recent conversations with an anonymous session cookie so follow-up questions retain context. There are no accounts and no identity across devices.",
  },
  {
    question: "Which models does Anchor use?",
    answer:
      "Anchor uses Gemini for answer generation and embeddings, Cohere Rerank for reordering, and PostgreSQL with pgvector for retrieval. Each request creates a trace.",
  },
  {
    question: "Is this legal or financial advice?",
    answer:
      "No. Anchor is a demonstration on public regulatory text. Read the cited text, then confirm it at the official source.",
  },
];

function chatHref(question?: string): string {
  const params = new URLSearchParams({ new: "1" });
  if (question) {
    params.set("q", question);
  }
  return `/chat?${params.toString()}`;
}

function AppearanceToggle({
  mode,
  setMode,
}: {
  mode: AppearanceMode;
  setMode: (mode: AppearanceMode) => void;
}) {
  const isDark = mode === "dark";
  return (
    <button
      type="button"
      className="icon-btn"
      onClick={() => setMode(isDark ? "light" : "dark")}
      aria-label="Switch appearance"
    >
      {isDark ? (
        <Sun size={16} aria-hidden="true" />
      ) : (
        <Moon size={16} aria-hidden="true" />
      )}
    </button>
  );
}

function CorpusPanel() {
  return (
    <aside id="corpus" className="corpus-panel" aria-label="Indexed corpus">
      <div className="panel-row panel-head">
        <span>
          <Database size={16} aria-hidden="true" />
          Indexed corpus
        </span>
        <span>Snapshot date May 2, 2026</span>
      </div>
      <div className="panel-row">
        <span>RBI Master Directions</span>
        <span>8</span>
      </div>
      <div className="panel-row panel-divide">
        <span>SEBI Master Circulars</span>
        <span>8</span>
      </div>
      <div className="corpus-list">
        <span>Know Your Customer (KYC) Direction, 2016</span>
        <span>Lending to the Micro, Small and Medium Enterprises Sector</span>
        <span>Master Circular for Research Analysts</span>
        <span>Master Circular for Mutual Funds</span>
        <span>12 more documents, all in English</span>
      </div>
    </aside>
  );
}

function ConsolePreview() {
  return (
    <section className="preview-section" aria-labelledby="preview-title">
      <div className="console-preview" aria-hidden="true">
        <div className="preview-sidebar">
          <span className="preview-brand">
            <AnchorGlyph size={13} />
            Anchor
          </span>
          <span className="preview-new">+ New question</span>
          <span className="preview-label">Recent</span>
          <span className="preview-item active">Customer due diligence</span>
          <span className="preview-item">Analyst disclosures</span>
          <span className="preview-item">MSME restructuring</span>
          <span className="preview-item">NBFC deposit ceilings</span>
        </div>
        <div className="preview-main">
          <div className="preview-top">
            <span>Customer due diligence for individuals</span>
            <span>RBI + SEBI · 16 documents</span>
          </div>
          <div className="preview-thread">
            <div className="preview-user">
              <span>
                What customer due diligence steps apply to individual customers?
              </span>
            </div>
            <div className="preview-answer">
              <span className="preview-meta">Anchor · 2 sources · 1.8s</span>
              <p>
                A regulated entity must obtain a recent photograph, PAN or
                equivalent e-document, and one officially valid document before
                the account is made operational.
                <sup>1</sup>
              </p>
              <span className="preview-source">
                <span>1</span>
                <strong>RBI</strong>
                Know Your Customer Direction, 2016 · p. 14
              </span>
            </div>
          </div>
          <div className="preview-composer">
            <span>Ask a follow-up</span>
            <span className="preview-send">
              <ArrowRight size={14} aria-hidden="true" />
            </span>
          </div>
        </div>
      </div>
      <p id="preview-title" className="preview-caption">
        The console keeps recent questions on the left. The transcript is capped
        for reading, and evidence sits one click below each answer.
      </p>
    </section>
  );
}

function FeatureGrid() {
  const features = [
    {
      icon: FileText,
      title: "An auditable corpus",
      body:
        "Each source has a URL, hash and snapshot date. Anchor does not search outside the manifest.",
    },
    {
      icon: Search,
      title: "Hybrid retrieval",
      body:
        "Keyword search and vector search run in PostgreSQL, then the combined result set is reranked.",
    },
    {
      icon: ShieldCheck,
      title: "Citation checks on the server",
      body:
        "The server compares each quotation with retrieved text before a citation reaches the page.",
    },
    {
      icon: Ban,
      title: "A refusal, not a guess",
      body:
        "If support is too weak, Anchor refuses and names the reason instead of filling the gap.",
    },
  ];

  return (
    <section className="feature-grid" aria-label="Product guarantees">
      {features.map(({ icon: Icon, title, body }) => (
        <div key={title} className="feature">
          <Icon size={20} strokeWidth={1.7} aria-hidden="true" />
          <h2>{title}</h2>
          <p>{body}</p>
        </div>
      ))}
    </section>
  );
}

function ExampleCards() {
  return (
    <section className="examples" aria-labelledby="examples-title">
      <div className="section-intro">
        <h2 id="examples-title">Two examples</h2>
        <p>
          The support in the corpus decides which type of answer reaches the
          transcript.
        </p>
      </div>

      <div className="example-grid">
        <article className="example-card">
          <div className="example-head">
            <span>Answered</span>
            <span>2 sources · 1.8s</span>
          </div>
          <div className="example-body">
            <p className="example-user">
              What must a research analyst disclose in a research report?
            </p>
            <div className="example-answer">
              <span className="preview-meta">Anchor · 2 sources · 1.8s</span>
              <p>
                Every research report must disclose actual or potential
                conflicts of interest and compensation received from the subject
                company in the preceding twelve months.
                <sup>1</sup> It must also carry registration details and the
                prescribed disclaimer.
                <sup>2</sup>
              </p>
            </div>
          </div>
        </article>

        <article className="example-card quiet">
          <div className="example-head">
            <span>Refused</span>
            <span>No source</span>
          </div>
          <div className="example-body">
            <p className="example-user">
              What is the current income tax rate for partnership firms?
            </p>
            <div className="example-answer">
              <span className="preview-meta">Anchor · no sources</span>
              <p>
                The indexed RBI and SEBI documents do not cover this question.
                Anchor cannot give a grounded answer from the current corpus.
              </p>
            </div>
          </div>
        </article>
      </div>
    </section>
  );
}

function HowItWorks() {
  const steps = [
    [
      "Retrieve from the corpus",
      "Anchor searches the indexed chunks with lexical and vector retrieval.",
    ],
    [
      "Combine and rerank",
      "The two result sets are fused, then a reranker keeps the strongest support.",
    ],
    [
      "Answer or refuse",
      "The model sees only retrieved text. Weak support produces a refusal.",
    ],
    [
      "Check citations",
      "The server validates quotations before returning the response.",
    ],
  ];

  return (
    <section id="how" className="how-section" aria-labelledby="how-title">
      <div className="section-intro">
        <h2 id="how-title">How it works</h2>
        <p>
          The interface exposes the retrieval contract without making reviewers
          read backend traces first.
        </p>
      </div>
      <div className="how-panel">
        {steps.map(([title, body], index) => (
          <div key={title} className="how-step">
            <div className="how-step-title">
              <span>{index + 1}</span>
              <h3>{title}</h3>
            </div>
            <p>{body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function Measurement() {
  const rows = [
    ["Groundedness on the golden set", "at least 0.85", "Fixture path only"],
    ["Retrieval recall at 5", "at least 0.88", "Fixture path only"],
    ["Refusal precision", "at least 0.90", "Fixture path only"],
    ["Answers with a valid citation", "100%", "Enforced on the server"],
    ["Latency at p95", "not more than 3.5 s", "Recorded for each request"],
  ];

  return (
    <section className="measurement" aria-labelledby="measurement-title">
      <div className="section-intro">
        <h2 id="measurement-title">Measurement</h2>
        <p>
          A smoke evaluation runs in CI. Live-provider evaluation results belong
          in the repository documents with the run date.
        </p>
      </div>
      <div className="measure-table" role="table" aria-label="Evaluation targets">
        <div className="measure-row measure-head" role="row">
          <span role="columnheader">Measure</span>
          <span role="columnheader">Target</span>
          <span role="columnheader">Status</span>
        </div>
        {rows.map(([measure, target, status]) => (
          <div key={measure} className="measure-row" role="row">
            <span role="cell">{measure}</span>
            <span role="cell">{target}</span>
            <span role="cell">{status}</span>
          </div>
        ))}
      </div>
      <p className="measure-note">
        Read the latest documented evaluation in{" "}
        <a
          href="https://github.com/VectorSigmaOmega/Anchor/blob/main/docs/EVAL.md"
          target="_blank"
          rel="noreferrer"
        >
          docs/EVAL.md
        </a>
        .
      </p>
    </section>
  );
}

function FAQ() {
  const [openIndex, setOpenIndex] = useState(0);

  return (
    <section id="faq" className="faq-section" aria-labelledby="faq-title">
      <div>
        <h2 id="faq-title">Questions and answers</h2>
        <p>
          Scope, storage and model boundaries are kept visible because they are
          part of the product contract.
        </p>
      </div>
      <div className="faq-list">
        {FAQS.map((item, index) => {
          const isOpen = openIndex === index;
          return (
            <div key={item.question} className="faq-item">
              <button
                type="button"
                aria-expanded={isOpen}
                onClick={() => setOpenIndex(isOpen ? -1 : index)}
              >
                {item.question}
                <ChevronDown size={16} aria-hidden="true" />
              </button>
              {isOpen ? <p>{item.answer}</p> : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default function LandingPage() {
  const [mode, setMode] = useState<AppearanceMode>("light");

  return (
    <div className="landing" style={{ colorScheme: mode }}>
      <header className="site-header">
        <Link href="/" className="wordmark wordmark-link" aria-label="Anchor home">
          <AnchorGlyph size={15} />
          Anchor
        </Link>
        <nav className="site-nav" aria-label="Primary navigation">
          <a href="#how">How it works</a>
          <a href="#corpus">Corpus</a>
          <a href="#faq">FAQ</a>
          <a
            href="https://github.com/VectorSigmaOmega/Anchor"
            target="_blank"
            rel="noreferrer"
          >
            Source
          </a>
          <AppearanceToggle mode={mode} setMode={setMode} />
          <Link href={chatHref()} className="btn btn-outline">
            Open console
            <ArrowRight size={13} aria-hidden="true" />
          </Link>
        </nav>
      </header>

      <main className="landing-scroll">
        <section className="hero-section">
          <div className="hero-grid">
            <div className="hero-copy">
              <h1>Every answer shows the source text.</h1>
              <p>
                Anchor answers questions about Indian financial regulation. It
                uses only a fixed corpus of RBI Master Directions and SEBI
                Master Circulars. If those documents do not support an answer,
                Anchor refuses.
              </p>
              <div className="hero-actions">
                <Link href={chatHref()} className="btn btn-primary">
                  Open the console
                  <ArrowRight size={13} aria-hidden="true" />
                </Link>
                <Link href={chatHref(EXAMPLES[0])} className="btn btn-outline">
                  See an example answer
                </Link>
              </div>
              <div className="hero-metrics" aria-label="System summary">
                <span>
                  <strong>16</strong> official documents
                </span>
                <span>
                  <strong>100%</strong> of answers have a citation
                </span>
                <span>
                  <strong>3.5 s</strong> latency target at p95
                </span>
              </div>
              <p className="hero-note">
                No account. No file upload. Anchor keeps your questions in this
                browser session.
              </p>
            </div>
            <CorpusPanel />
          </div>

          <ConsolePreview />
          <FeatureGrid />
          <ExampleCards />
          <HowItWorks />
          <Measurement />
          <FAQ />
        </section>

        <section className="final-cta">
          <h2>Ask a question about RBI or SEBI regulation.</h2>
          <p>
            One question shows the contract: an answer with source text, or a
            refusal with a reason. You do not need an account.
          </p>
          <div>
            <Link href={chatHref()} className="btn btn-primary">
              Open the console
              <ArrowRight size={15} aria-hidden="true" />
            </Link>
            <a
              href="https://github.com/VectorSigmaOmega/Anchor/blob/main/docs/ARCHITECTURE.md"
              target="_blank"
              rel="noreferrer"
              className="btn btn-outline"
            >
              Read the architecture
              <ExternalLink size={15} aria-hidden="true" />
            </a>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="footer-grid">
          <div>
            <span className="wordmark">
              <AnchorGlyph size={15} />
              Anchor
            </span>
            <p>
              Anchor gives answers with citations from Indian financial
              regulation.
            </p>
          </div>
          <div>
            <h2>Product</h2>
            <Link href={chatHref()}>Console</Link>
            <a href="#corpus">Corpus</a>
            <a href="#how">How it works</a>
            <a href="#faq">FAQ</a>
          </div>
          <div>
            <h2>Documentation</h2>
            <a
              href="https://github.com/VectorSigmaOmega/Anchor#readme"
              target="_blank"
              rel="noreferrer"
            >
              Readme
            </a>
            <a
              href="https://github.com/VectorSigmaOmega/Anchor/blob/main/docs/ARCHITECTURE.md"
              target="_blank"
              rel="noreferrer"
            >
              Architecture
            </a>
            <a
              href="https://github.com/VectorSigmaOmega/Anchor/blob/main/docs/SPEC.md"
              target="_blank"
              rel="noreferrer"
            >
              Implementation contract
            </a>
            <a
              href="https://github.com/VectorSigmaOmega/Anchor/blob/main/docs/EVAL.md"
              target="_blank"
              rel="noreferrer"
            >
              Evaluation
            </a>
          </div>
          <div>
            <h2>Boundaries</h2>
            <span>This is a demonstration. It is not legal or financial advice.</span>
            <span>No accounts. No file upload. No tax law.</span>
            <span>Confirm each answer at the cited source.</span>
          </div>
        </div>
        <div className="footer-bottom">
          <span>Anchor · corpus snapshot May 2, 2026</span>
          <a
            href="https://github.com/VectorSigmaOmega/Anchor"
            target="_blank"
            rel="noreferrer"
          >
            Source on GitHub
            <ExternalLink size={13} aria-hidden="true" />
          </a>
        </div>
      </footer>
    </div>
  );
}
