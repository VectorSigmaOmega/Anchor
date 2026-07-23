"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import "./landing.css";

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
  {
    short: "Customer due diligence",
    question: "What customer due diligence steps apply to individual customers?",
  },
  {
    short: "Analyst disclosures",
    question: "What must a research analyst disclose in a research report?",
  },
  {
    short: "MSME loan restructuring",
    question: "When may an MSME loan be restructured under RBI directions?",
  },
];

function chatHref(question?: string): string {
  return question ? `/chat?q=${encodeURIComponent(question)}` : "/chat";
}

export default function LandingPage() {
  const [draft, setDraft] = useState("");

  function ask(event: React.FormEvent) {
    event.preventDefault();
    const question = draft.trim();
    window.location.assign(chatHref(question || undefined));
  }

  return (
    <div className="landing">
      <header className="lp-bar">
        <Link href="/" className="wordmark wordmark-link" aria-label="Anchor home">
          <AnchorGlyph size={16} />
          Anchor
        </Link>
        <Link href={chatHref()} className="lp-bar-link">
          Open console
          <ArrowRight size={15} aria-hidden="true" />
        </Link>
      </header>

      <main className="lp-main">
        <div className="lp-left">
          <h1 className="lp-h1">
            Answered from the source,
            <br />
            not the model.
          </h1>
          <p className="lp-lede">
            Ask about RBI Master Directions and SEBI Master Circulars. Anchor
            answers only from those documents, shows the passages behind every
            answer, and refuses when they do not cover your question.
          </p>

          <form className="lp-ask" onSubmit={ask}>
            <input
              className="lp-ask-input"
              type="text"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Ask a question about RBI or SEBI regulation"
              aria-label="Ask a question about RBI or SEBI regulation"
              autoComplete="off"
            />
            <button type="submit" className="btn btn-primary lp-ask-submit">
              Ask
              <ArrowRight size={17} aria-hidden="true" />
            </button>
          </form>

          <p className="lp-examples">
            <span className="lp-examples-label">or try</span>
            {EXAMPLES.map((example, index) => (
              <span key={example.question}>
                <Link href={chatHref(example.question)} className="link">
                  {example.short}
                </Link>
                {index < EXAMPLES.length - 1 ? (
                  <span className="lp-examples-sep" aria-hidden="true">
                    ,
                  </span>
                ) : null}
              </span>
            ))}
          </p>
        </div>

        <aside className="lp-demo" aria-label="Example of a grounded answer">
          <p className="lp-demo-label">A grounded answer</p>
          <p className="lp-demo-q">
            What must a research analyst disclose in a research report?
          </p>
          <p className="lp-demo-a">
            Any actual or potential conflict of interest: financial interest
            held by the analyst or their relatives in the subject company, and
            compensation received from it in the preceding twelve months.
            <sup className="lp-cite">1</sup> The report must also carry the
            analyst&apos;s registration details and the standard SEBI
            disclaimer.
            <sup className="lp-cite">2</sup>
          </p>
          <ol className="lp-demo-src">
            <li>
              <span className="reg">SEBI</span>
              Master Circular for Research Analysts, conflicts of interest
            </li>
            <li>
              <span className="reg">SEBI</span>
              Master Circular for Research Analysts, standard disclaimer
            </li>
          </ol>
        </aside>
      </main>

      <footer className="lp-foot">
        <span className="lp-foot-corpus">16 official documents from RBI and SEBI.</span>
        <span className="lp-foot-note">
          Demonstration only, not legal advice. Verify against the cited source.
        </span>
      </footer>
    </div>
  );
}
