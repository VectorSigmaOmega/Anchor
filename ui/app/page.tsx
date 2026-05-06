"use client";

import { FormEvent, useState, useTransition } from "react";

type Citation = {
  chunk_id: string;
  doc_id: string;
  doc_title: string;
  regulator: "SEBI" | "RBI";
  section_title: string;
  page: number | null;
  source_url: string;
  quote: string;
};

type QueryResponse = {
  request_id: string;
  status: "answered" | "refused";
  answer: string;
  refusal_reason: "not_in_corpus" | "insufficient_support" | "ambiguous_question" | "rate_limited" | null;
  citations: Citation[];
  disclaimer: string;
  latency_ms: number;
};

const SUGGESTIONS = [
  "What customer due diligence steps does the RBI KYC direction require for individuals?",
  "What does the RBI MSME direction say about restructuring support for MSME borrowers?",
  "What does the SEBI mutual funds master circular say about investor service disclosures?",
  "What reporting requirements apply under SEBI's research analysts master circular?",
];

const REFUSAL_COPY: Record<string, string> = {
  not_in_corpus: "That question does not appear to be supported by the indexed SEBI and RBI corpus.",
  insufficient_support: "The retrieved material is related, but it does not support a clean grounded answer.",
  ambiguous_question: "The question needs more context before the system can answer from the corpus.",
  rate_limited: "The demo rate limit for this IP has been reached.",
};

export default function HomePage() {
  const [question, setQuestion] = useState(SUGGESTIONS[0]);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [error, setError] = useState<string>("");
  const [isPending, startTransition] = useTransition();

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    startTransition(async () => {
      try {
        const response = await fetch("/query", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question }),
        });
        const payload = (await response.json()) as QueryResponse;
        if (!response.ok && !payload.status) {
          throw new Error("Request failed.");
        }
        setResult(payload);
      } catch (caught) {
        const message = caught instanceof Error ? caught.message : "Request failed.";
        setError(message);
      }
    });
  }

  return (
    <main className="shell">
      <section className="hero">
        <div className="eyebrow">Anchor</div>
        <h1>Grounded answers over official RBI Master Directions and SEBI Master Circulars.</h1>
        <p className="lede">
          Narrow corpus. Hybrid retrieval. Hosted rerank. Strict refusal. Server-side citation validation.
        </p>
        <div className="scope-strip">
          <span>Corpus: official English-language RBI Master Directions</span>
          <span>and SEBI Master Circulars only</span>
          <span>No tax-law content</span>
        </div>
      </section>

      <section className="workspace">
        <form className="query-panel" onSubmit={submit}>
          <label htmlFor="question" className="panel-label">
            Ask a regulatory question
          </label>
          <textarea
            id="question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            maxLength={800}
            rows={6}
            placeholder="Ask a question anchored in the indexed corpus."
          />
          <div className="panel-actions">
            <button type="submit" disabled={isPending || question.trim().length === 0}>
              {isPending ? "Running query..." : "Run query"}
            </button>
            <span>{question.trim().length}/800 characters</span>
          </div>
          <div className="suggestions">
            {SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                className="suggestion-chip"
                onClick={() => setQuestion(suggestion)}
              >
                {suggestion}
              </button>
            ))}
          </div>
        </form>

        <section className="answer-panel">
          <div className="answer-header">
            <span>Result</span>
            {result ? <span>{result.latency_ms} ms</span> : null}
          </div>

          {!result && !error ? (
            <div className="empty-state">
              <p>Answers appear here with hydrated citations or a refusal when support is weak.</p>
              <ul>
                <li>Lexical search + dense search</li>
                <li>RRF fusion + Cohere rerank</li>
                <li>Gemini generation from selected chunks only</li>
              </ul>
            </div>
          ) : null}

          {error ? <p className="error">{error}</p> : null}

          {result ? (
            <div className="result-block">
              <div className={`status-pill ${result.status}`}>{result.status}</div>
              {result.status === "answered" ? (
                <p className="answer-copy">{result.answer}</p>
              ) : (
                <p className="answer-copy">
                  {result.refusal_reason ? REFUSAL_COPY[result.refusal_reason] : "The system refused this question."}
                </p>
              )}

              <div className="meta-row">
                <span>Request ID: {result.request_id}</span>
                <span>{result.disclaimer}</span>
              </div>

              {result.citations.length > 0 ? (
                <div className="citations">
                  <h2>Citations</h2>
                  {result.citations.map((citation) => (
                    <a
                      key={citation.chunk_id}
                      className="citation-card"
                      href={citation.source_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <div className="citation-topline">
                        <span>{citation.regulator}</span>
                        <span>{citation.page ? `Page ${citation.page}` : "HTML source"}</span>
                      </div>
                      <h3>{citation.doc_title}</h3>
                      <p className="section-line">{citation.section_title}</p>
                      <p className="quote">{citation.quote}</p>
                    </a>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </section>
      </section>
    </main>
  );
}

