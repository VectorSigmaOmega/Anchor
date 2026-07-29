"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  CORPUS_SNAPSHOT,
  CORPUS_SUMMARY,
  DOCS,
  REPO_URL,
  STARTER_QUESTIONS,
  chatHref,
} from "./content";
import {
  AnchorMark,
  ArrowRight,
  ArrowUp,
  ChevronDown,
  CircleSlash,
  DocumentMark,
  MagnifierPlus,
  ShieldCheck,
} from "./icons";
import { AppearanceToggle } from "./theme";

import "./landing.css";

const RESEARCH_ANALYST_PDF =
  "https://www.sebi.gov.in/sebi_data/attachdocs/feb-2026/1770375507051.pdf";

const BENEFITS = [
  {
    Icon: DocumentMark,
    title: "An auditable corpus",
    body: "The corpus has 16 official documents. Each document has a source URL, a hash and a snapshot date. Anchor does not search other documents.",
  },
  {
    Icon: MagnifierPlus,
    title: "Hybrid retrieval",
    body: "Anchor does a keyword search and a vector search in PostgreSQL. It then combines the two result sets and puts them in a new order.",
  },
  {
    Icon: ShieldCheck,
    title: "Citation checks on the server",
    body: "The server compares each quotation with the retrieved text. A citation that does not match the retrieved text does not reach the page.",
  },
  {
    Icon: CircleSlash,
    title: "A refusal, not a guess",
    body: "If the corpus does not support an answer, Anchor gives a refusal. The refusal shows the reason: not in corpus, insufficient support or ambiguous question.",
  },
];

const STEPS = [
  {
    name: "Retrieve",
    // The handoff copy said 12; the pipeline keeps `lexical_candidate_count` /
    // `dense_candidate_count`, both 30. Keep this figure tied to the config.
    body: "Anchor does a keyword search and a vector search in PostgreSQL. It keeps 30 results from each search.",
  },
  {
    name: "Combine and rerank",
    body: "Anchor combines the two result sets. A reranker then keeps only the text above the support limit.",
  },
  {
    name: "Answer or refuse",
    body: "The model sees only this text. If the support is too weak, Anchor gives a refusal with a reason.",
  },
  {
    name: "Check citations",
    body: "The server compares each quotation with its retrieved text before it sends the answer.",
  },
];

// Targets from the product requirements — not measured results. If a real
// evaluation run lands, replace the figures and say when it ran.
const MEASURES = [
  ["Groundedness on the golden set", "≥ 0.85", "Fixture path only"],
  ["Retrieval recall at 5", "≥ 0.88", "Fixture path only"],
  ["Refusal precision, out-of-corpus set", "≥ 0.90", "Fixture path only"],
  ["Answers with a valid citation", "100%", "Enforced on the server"],
  ["Latency at p95", "≤ 3.5s", "Recorded for each request"],
];

const FAQS: { question: string; answer: React.ReactNode }[] = [
  {
    question: "What is in the corpus?",
    answer:
      "The corpus has 16 official documents in English: 8 RBI Master Directions and 8 SEBI Master Circulars. The manifest in the repository gives the source URL, the hash and the snapshot date for each document. Anchor does not search superseded documents.",
  },
  {
    question: "What happens if the corpus does not have the answer?",
    answer:
      "Anchor gives a refusal. The refusal shows the reason: not in corpus, insufficient support or ambiguous question. Anchor does not answer from the memory of the model.",
  },
  {
    question: "Can I add my own documents?",
    answer:
      "No. The manifest controls the corpus. File upload, accounts and other languages are not in the scope. Tax law is also not in the scope.",
  },
  {
    question: "Does Anchor store my conversation?",
    answer:
      "Anchor keeps recent conversations with an anonymous session cookie. Your follow-up questions then keep their context. There are no accounts and no identity across devices.",
  },
  {
    question: "Which models does Anchor use?",
    answer: (
      <>
        Anchor uses <code>gemini-3.1-flash-lite</code> for generation and{" "}
        <code>gemini-embedding-2</code> for embeddings. Cohere Rerank puts the
        results in a new order. PostgreSQL with pgvector does the retrieval. Each
        request makes a trace.
      </>
    ),
  },
  {
    question: "Is this legal or financial advice?",
    answer:
      "No. Anchor is a demonstration on public regulatory text. Read the cited text. Then confirm it at the official source.",
  },
];

/**
 * Every major section fades and rises once as it enters the viewport, driven by
 * one shared IntersectionObserver.
 *
 * The hidden state is set from script rather than from CSS, so the page is
 * fully readable if JavaScript never runs. A ref callback applies it during
 * commit, before the browser paints, so there is no flash of visible content.
 */
function useReveal() {
  const observerRef = useRef<IntersectionObserver | null>(null);

  useEffect(() => {
    const observer = observerRef.current;
    return () => observer?.disconnect();
  }, []);

  return useCallback((node: HTMLElement | null) => {
    if (!node) {
      return;
    }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }
    if (!observerRef.current) {
      observerRef.current = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (!entry.isIntersecting) {
              continue;
            }
            const element = entry.target as HTMLElement;
            element.style.opacity = "1";
            element.style.transform = "none";
            observerRef.current?.unobserve(element);
          }
        },
        { rootMargin: "0px 0px -10% 0px", threshold: 0.04 },
      );
    }
    node.style.opacity = "0";
    node.style.transform = "translateY(12px)";
    node.style.transition =
      "opacity 380ms var(--ease), transform 380ms var(--ease)";
    observerRef.current.observe(node);
  }, []);
}

/**
 * The console at a reduced type scale, built from real markup rather than an
 * image. Decorative — the transcript beneath it says the same thing in text.
 */
function ConsoleShot() {
  return (
    <div className="shot" aria-hidden="true">
      <div className="shot-frame">
        <div className="shot-rail">
          <span className="shot-brand">
            <AnchorMark size={13} />
            Anchor
          </span>
          <span className="shot-new">+ New question</span>
          <span className="shot-label">Recent</span>
          <span className="shot-item is-selected">Customer due diligence</span>
          <span className="shot-item">Analyst disclosures</span>
          <span className="shot-item">MSME restructuring</span>
          <span className="shot-item">NBFC deposit ceilings</span>
        </div>
        <div className="shot-main">
          <div className="shot-top">
            <span>Customer due diligence for individuals</span>
            <span>{CORPUS_SUMMARY}</span>
          </div>
          <div className="shot-thread">
            <div className="shot-user">
              <span>{STARTER_QUESTIONS[0]}</span>
            </div>
            <div className="shot-answer">
              <span className="shot-meta">Anchor · 2 sources · 1.8s</span>
              <span className="shot-text">
                A regulated entity must obtain a recent photograph, the PAN or
                equivalent e-document, and one officially valid document for
                identity and address<sup>1</sup> before the account is made
                operational.<sup>2</sup>
              </span>
              <span className="shot-source">
                <span className="shot-source-n">1</span>
                <span className="shot-source-reg">RBI</span>
                <span className="shot-source-doc">
                  Know Your Customer (KYC) Direction, 2016 · p. 14
                </span>
              </span>
            </div>
          </div>
          <div className="shot-dock">
            <div className="shot-composer">
              <span>Ask a follow-up</span>
              <span className="shot-send">
                <ArrowUp size={14} />
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Faq() {
  // Single-open: opening one closes the others, and clicking the open row
  // closes it. -1 means no row is open.
  const [openIndex, setOpenIndex] = useState(0);

  return (
    <div>
      {FAQS.map((item, index) => {
        const isOpen = openIndex === index;
        const panelId = `faq-panel-${index}`;
        return (
          <div key={item.question} className="faq-item">
            <button
              type="button"
              className="faq-trigger"
              aria-expanded={isOpen}
              aria-controls={panelId}
              onClick={() => setOpenIndex(isOpen ? -1 : index)}
            >
              {item.question}
              <span className="faq-chevron">
                <ChevronDown size={16} />
              </span>
            </button>
            {isOpen ? (
              <p className="faq-panel" id={panelId}>
                {item.answer}
              </p>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

export default function LandingPage() {
  const revealRef = useReveal();

  return (
    <div className="landing">
      <header className="landing-header">
        <span className="wordmark">
          <AnchorMark size={15} />
          Anchor
        </span>
        <nav className="landing-nav" aria-label="Primary">
          <a className="nav-link" href="#how">
            How it works
          </a>
          <a className="nav-link" href="#corpus">
            Corpus
          </a>
          <a className="nav-link" href="#faq">
            FAQ
          </a>
          <a
            className="nav-link"
            href={REPO_URL}
            target="_blank"
            rel="noreferrer"
          >
            Source
          </a>
          <AppearanceToggle />
          <Link className="btn btn-outline btn-sm" href={chatHref()}>
            Open console
            <ArrowRight size={13} />
          </Link>
        </nav>
      </header>

      <div className="landing-scroll">
        <div className="landing-column">
          <section className="hero">
            <div>
              <h1 className="hero-title rise">
                Every answer shows the source text.
              </h1>
              <p className="hero-sub rise rise-1">
                Anchor answers questions about Indian financial regulation. It
                uses only a fixed corpus of RBI Master Directions and SEBI Master
                Circulars. If these documents do not support an answer, Anchor
                refuses.
              </p>
              <div className="hero-actions rise rise-2">
                <Link className="btn btn-primary" href={chatHref()}>
                  Open the console
                  <ArrowRight size={13} />
                </Link>
                <Link
                  className="btn btn-outline"
                  href={chatHref(STARTER_QUESTIONS[0])}
                >
                  See an example answer
                </Link>
              </div>
              <div className="hero-proof rise rise-3">
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

            <aside
              id="corpus"
              className="corpus-panel rise rise-4"
              aria-label="Indexed corpus"
            >
              <div className="panel-row panel-head">
                <span>Indexed corpus</span>
                <span>Snapshot date {CORPUS_SNAPSHOT}</span>
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
                <span>
                  Lending to the Micro, Small &amp; Medium Enterprises Sector
                </span>
                <span>Master Circular for Research Analysts</span>
                <span>Master Circular for Mutual Funds</span>
                <span>12 more documents, all in English</span>
              </div>
            </aside>
          </section>

          <section className="shot-section" ref={revealRef}>
            <ConsoleShot />
            <p className="shot-caption">
              The console shows your recent questions on the left. The transcript
              has a maximum width for easy reading. The evidence is one click
              below each answer.
            </p>
          </section>

          <section
            className="section benefits"
            ref={revealRef}
            aria-label="What Anchor guarantees"
          >
            {BENEFITS.map(({ Icon, title, body }) => (
              <div key={title} className="benefit">
                <Icon size={20} />
                <h3>{title}</h3>
                <p>{body}</p>
              </div>
            ))}
          </section>

          <section
            className="section"
            ref={revealRef}
            aria-labelledby="examples-title"
          >
            <h2 className="section-title" id="examples-title">
              Two examples
            </h2>
            <p className="section-intro">
              These are two answers from the console. The support in the corpus
              decides which type of answer you get.
            </p>

            <div className="example-grid">
              <article className="example-card">
                <div className="example-head">
                  <span>Answered</span>
                  <span>2 sources · 1.8s</span>
                </div>
                <div className="example-body">
                  <div className="example-user">
                    <p>{STARTER_QUESTIONS[1]}</p>
                  </div>
                  <div className="example-turn">
                    <p className="example-meta">Anchor · 2 sources · 1.8s</p>
                    <p className="example-text">
                      Every research report must disclose any actual or potential
                      conflict of interest: financial interest held by the
                      analyst or their relatives in the subject company, and
                      compensation received from that company in the preceding
                      twelve months.<sup className="cite">1</sup> It must also
                      carry the analyst&rsquo;s registration details and the
                      standard disclaimer prescribed for research reports.
                      <sup className="cite">2</sup>
                    </p>
                    <ol className="sources">
                      <li className="source">
                        <span className="source-n">1</span>
                        <span className="reg">SEBI</span>
                        <span className="source-ref">
                          <a
                            href={RESEARCH_ANALYST_PDF}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Master Circular for Research Analysts
                          </a>
                          , disclosure of conflicts of interest · p. 31
                        </span>
                      </li>
                      <li className="source">
                        <span className="source-n">2</span>
                        <span className="reg">SEBI</span>
                        <span className="source-ref">
                          <a
                            href={RESEARCH_ANALYST_PDF}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Master Circular for Research Analysts
                          </a>
                          , standard disclaimer · p. 33
                        </span>
                      </li>
                    </ol>
                  </div>
                </div>
              </article>

              <article className="example-card is-refused">
                <div className="example-head">
                  <span>Refused</span>
                  <span>not in corpus · 0.9s</span>
                </div>
                <div className="example-body">
                  <div className="example-user">
                    <p>What is the GST rate on brokerage services?</p>
                  </div>
                  <div className="example-turn">
                    <p className="example-meta">Anchor · no sources</p>
                    <p className="example-refusal-title">No grounded answer</p>
                    <p className="example-refusal-body">
                      Tax law is not in the corpus. Anchor answers only from the
                      RBI Master Directions and the SEBI Master Circulars in the
                      list above.
                    </p>
                  </div>
                </div>
              </article>
            </div>
          </section>

          <section
            id="how"
            className="section section-anchor"
            ref={revealRef}
            aria-labelledby="how-title"
          >
            <h2 className="section-title" id="how-title">
              The steps for one answer
            </h2>
            <div className="steps">
              {STEPS.map((step, index) => (
                <div key={step.name} className="step">
                  <div className="step-head">
                    <span className="step-n">{index + 1}</span>
                    <span className="step-name">{step.name}</span>
                  </div>
                  <p>{step.body}</p>
                </div>
              ))}
            </div>
          </section>

          <section
            className="section"
            ref={revealRef}
            aria-labelledby="measurement-title"
          >
            <h2 className="section-title" id="measurement-title">
              Measurement
            </h2>
            <p className="section-intro">
              The product requirements give these targets. A smoke evaluation
              runs in the CI pipeline for each pull request.
            </p>
            <div
              className="measure-table"
              role="table"
              aria-label="Evaluation targets"
            >
              <div className="measure-row measure-head" role="row">
                <span role="columnheader">Measure</span>
                <span role="columnheader">Target</span>
                <span role="columnheader">Status</span>
              </div>
              {MEASURES.map(([measure, target, status]) => (
                <div key={measure} className="measure-row" role="row">
                  <span role="cell">{measure}</span>
                  <span role="cell">{target}</span>
                  <span role="cell">{status}</span>
                </div>
              ))}
            </div>
            <p className="measure-note">
              The full evaluation needs live providers and an indexed database.
              Anchor publishes the results in{" "}
              <a href={DOCS.eval} target="_blank" rel="noreferrer">
                docs/EVAL.md
              </a>{" "}
              with the run date.
            </p>
          </section>

          <section
            id="faq"
            className="section section-anchor faq"
            ref={revealRef}
            aria-labelledby="faq-title"
          >
            <div className="faq-aside">
              <h2 className="section-title" id="faq-title">
                Questions and answers
              </h2>
              <p>
                This section gives the scope, the storage and the models. The
                repository documents give more data.
              </p>
            </div>
            <Faq />
          </section>
        </div>

        <section className="cta-band" ref={revealRef}>
          <div className="cta-inner">
            <h2 className="cta-title">
              Ask a question about RBI or SEBI regulation.
            </h2>
            <p className="cta-body">
              One question shows the contract: an answer with its source text, or
              a refusal with a reason. You do not need an account.
            </p>
            <div className="cta-actions">
              <Link className="btn btn-primary btn-lg" href={chatHref()}>
                Open the console
                <ArrowRight size={15} />
              </Link>
              <a
                className="btn btn-outline btn-lg"
                href={DOCS.architecture}
                target="_blank"
                rel="noreferrer"
              >
                Read the architecture
              </a>
            </div>
          </div>
        </section>

        <footer className="landing-footer">
          <div className="footer-grid">
            <div className="footer-brand">
              <span className="wordmark">
                <AnchorMark size={15} />
                Anchor
              </span>
              <p>
                Anchor gives answers with citations from Indian financial
                regulation.
              </p>
            </div>
            <div className="footer-col">
              <h2>Product</h2>
              <Link href={chatHref()}>Console</Link>
              <a href="#corpus">Corpus</a>
              <a href="#how">How it works</a>
              <a href="#faq">FAQ</a>
            </div>
            <div className="footer-col">
              <h2>Documentation</h2>
              <a href={DOCS.readme} target="_blank" rel="noreferrer">
                Readme
              </a>
              <a href={DOCS.architecture} target="_blank" rel="noreferrer">
                Architecture
              </a>
              <a href={DOCS.spec} target="_blank" rel="noreferrer">
                Implementation contract
              </a>
              <a href={DOCS.eval} target="_blank" rel="noreferrer">
                Evaluation
              </a>
            </div>
            <div className="footer-col">
              <h2>Boundaries</h2>
              <span>
                This is a demonstration. It is not legal or financial advice.
              </span>
              <span>No accounts. No file upload. No tax law.</span>
              <span>Confirm each answer at the cited source.</span>
            </div>
          </div>
          <div className="footer-bottom-wrap">
            <div className="footer-bottom">
              <span>Anchor · corpus snapshot {CORPUS_SNAPSHOT}</span>
              <a href={REPO_URL} target="_blank" rel="noreferrer">
                Source on GitHub
              </a>
            </div>
          </div>
        </footer>
      </div>
    </div>
  );
}
