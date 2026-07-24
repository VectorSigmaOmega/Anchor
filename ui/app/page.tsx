"use client";

import { ArrowRight, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import "./landing.css";

function AnchorGlyph({ size = 16, draw = false }: { size?: number; draw?: boolean }) {
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
      className={draw ? "glyph-draw" : undefined}
      aria-hidden="true"
    >
      <circle cx="12" cy="4" r="2.4" pathLength={1} />
      <line x1="12" y1="6.4" x2="12" y2="22" pathLength={1} />
      <line x1="7" y1="11" x2="17" y2="11" pathLength={1} />
      <path d="M4 15c0 5 3.6 7.6 8 7.6s8-2.6 8-7.6" pathLength={1} />
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

/* The demo replays a real console exchange. Segments stream word by word;
   each segment ends by dropping its citation, and the sources rise in last. */
const DEMO_QUESTION = "What must a research analyst disclose in a research report?";

const DEMO_SEGMENTS = [
  {
    cite: 1,
    text: "Any actual or potential conflict of interest: financial interest held by the analyst or their relatives in the subject company, and compensation received from it in the preceding twelve months.",
  },
  {
    cite: 2,
    text: "The report must also carry the analyst's registration details and the standard SEBI disclaimer.",
  },
];

const DEMO_SOURCES = [
  {
    n: 1,
    regulator: "SEBI",
    doc: "Master Circular for Research Analysts",
    section: "conflicts of interest",
  },
  {
    n: 2,
    regulator: "SEBI",
    doc: "Master Circular for Research Analysts",
    section: "standard disclaimer",
  },
];

type DemoWord = { word: string; segment: number };

const DEMO_WORDS: DemoWord[] = DEMO_SEGMENTS.flatMap((segment, segmentIndex) =>
  segment.text.split(" ").map((word) => ({ word, segment: segmentIndex })),
);

const SEGMENT_END: number[] = DEMO_SEGMENTS.map(
  (_, segmentIndex) =>
    DEMO_WORDS.filter((entry) => entry.segment <= segmentIndex).length,
);

const WORD_INTERVAL_MS = 34;
const STREAM_START_DELAY_MS = 1050;

function GroundedDemo() {
  const total = DEMO_WORDS.length;
  // Server-rendered HTML carries the full answer; the stream is a client replay.
  const [shown, setShown] = useState(total);
  const [isStreaming, setIsStreaming] = useState(false);
  const [canReplay, setCanReplay] = useState(false);
  const [hoveredCite, setHoveredCite] = useState<number | null>(null);
  const timersRef = useRef<number[]>([]);

  const clearTimers = useCallback(() => {
    timersRef.current.forEach((id) => {
      window.clearTimeout(id);
      window.clearInterval(id);
    });
    timersRef.current = [];
  }, []);

  const play = useCallback(
    (startDelay: number) => {
      clearTimers();
      setShown(0);
      setIsStreaming(true);
      const startId = window.setTimeout(() => {
        const tickId = window.setInterval(() => {
          setShown((current) => {
            if (current + 1 >= total) {
              window.clearInterval(tickId);
              setIsStreaming(false);
              setCanReplay(true);
              return total;
            }
            return current + 1;
          });
        }, WORD_INTERVAL_MS);
        timersRef.current.push(tickId);
      }, startDelay);
      timersRef.current.push(startId);
    },
    [clearTimers, total],
  );

  useEffect(() => {
    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    // Skip the replay when motion is unwelcome, the tab is hidden, or
    // hydration arrived late enough that the text was already read.
    if (reduceMotion || document.visibilityState === "hidden" || performance.now() > 1600) {
      return;
    }
    play(STREAM_START_DELAY_MS);
    return clearTimers;
    // Run once on mount only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const done = shown >= total;

  return (
    <aside className="lp-demo" aria-label="Example of a grounded answer">
      <div className="lp-demo-head">
        <p className="lp-demo-label">From the console</p>
        {canReplay && done ? (
          <button
            type="button"
            className="lp-replay"
            onClick={() => play(160)}
            aria-label="Replay the demonstration"
          >
            <RotateCcw size={12} aria-hidden="true" />
            Replay
          </button>
        ) : null}
      </div>

      <p className="lp-demo-q">{DEMO_QUESTION}</p>

      <p className="lp-demo-a">
        {DEMO_SEGMENTS.map((segment, segmentIndex) => {
          const start = segmentIndex === 0 ? 0 : SEGMENT_END[segmentIndex - 1];
          const end = SEGMENT_END[segmentIndex];
          const words = DEMO_WORDS.slice(start, end);
          const renderWord = (entry: DemoWord, absolute: number) => (
            <span
              key={absolute}
              className={absolute < shown ? "dw on" : "dw"}
            >
              {entry.word}
              {absolute === shown - 1 && isStreaming ? (
                <span className="lp-caret" aria-hidden="true" />
              ) : null}
            </span>
          );
          return (
            <span key={segment.cite}>
              {words.slice(0, -1).map((entry, wordIndex) => (
                <span key={start + wordIndex}>
                  {renderWord(entry, start + wordIndex)}{" "}
                </span>
              ))}
              {/* the closing word and its citation never separate */}
              <span className="lp-hold">
                {renderWord(words[words.length - 1], end - 1)}
                <sup
                  className={shown >= end ? "lp-cite on" : "lp-cite"}
                  data-hi={hoveredCite === segment.cite}
                  onMouseEnter={() => setHoveredCite(segment.cite)}
                  onMouseLeave={() => setHoveredCite(null)}
                >
                  {segment.cite}
                </sup>
              </span>{" "}
            </span>
          );
        })}
      </p>

      <ol className="sources lp-demo-sources" data-in={done}>
        {DEMO_SOURCES.map((source) => (
          <li
            key={source.n}
            className="source"
            data-hi={hoveredCite === source.n}
            onMouseEnter={() => setHoveredCite(source.n)}
            onMouseLeave={() => setHoveredCite(null)}
          >
            <span className="source-n">{source.n}</span>
            <span className="reg">{source.regulator}</span>
            <span className="source-ref">
              <span className="source-doc">{source.doc}</span>
              <span className="source-sec">, {source.section}</span>
            </span>
          </li>
        ))}
      </ol>
    </aside>
  );
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
          <AnchorGlyph size={16} draw />
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
            <span className="lp-h1-mask">
              <span className="lp-h1-line">Answered from</span>
            </span>
            <span className="lp-h1-mask">
              <span className="lp-h1-line">the source,</span>
            </span>
            <span className="lp-h1-mask">
              <span className="lp-h1-line">not the model.</span>
            </span>
          </h1>
          <p className="lp-lede lp-rise" style={{ "--d": "260ms" } as React.CSSProperties}>
            Ask about RBI Master Directions and SEBI Master Circulars. Anchor
            answers only from those documents, shows the passages behind every
            answer, and refuses when they do not cover your question.
          </p>

          <form
            className="lp-ask lp-rise"
            style={{ "--d": "360ms" } as React.CSSProperties}
            onSubmit={ask}
          >
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

          <div
            className="lp-try lp-rise"
            style={{ "--d": "440ms" } as React.CSSProperties}
          >
            <span className="lp-try-label">or try</span>
            {EXAMPLES.map((example) => (
              <Link
                key={example.question}
                href={chatHref(example.question)}
                className="chip"
              >
                {example.short}
              </Link>
            ))}
          </div>
        </div>

        <GroundedDemo />
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
