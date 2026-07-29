// Copy and constants shared by the landing page and the console.
//
// The landing page speaks the console's vocabulary rather than a marketing
// one, so the two surfaces read as one product. Anything that appears on both
// lives here so it cannot drift.
//
// All landing copy is ASD-STE100 Simplified Technical English: one idea per
// sentence, active voice, present tense, and consistent technical terms
// (corpus, citation, refusal, passage). Do not rewrite it into marketing voice.

export const REPO_URL = "https://github.com/VectorSigmaOmega/Anchor";
export const DOCS = {
  readme: `${REPO_URL}#readme`,
  architecture: `${REPO_URL}/blob/main/docs/ARCHITECTURE.md`,
  spec: `${REPO_URL}/blob/main/docs/SPEC.md`,
  eval: `${REPO_URL}/blob/main/docs/EVAL.md`,
};

export const CORPUS_SUMMARY = "RBI + SEBI · 16 documents";
export const CORPUS_SNAPSHOT = "2 May 2026";

export const DISCLAIMER =
  "Anchor answers only from the official corpus. Verify against the cited source.";

/** The console's empty state and the landing page offer the same three starters. */
export const STARTER_QUESTIONS = [
  "What customer due diligence steps apply to individual customers?",
  "What must a research analyst disclose in a research report?",
  "When may an MSME loan be restructured under RBI directions?",
];

/** Deep-links into the console. `new=1` forces a fresh conversation. */
export function chatHref(question?: string): string {
  const params = new URLSearchParams({ new: "1" });
  if (question) {
    params.set("q", question);
  }
  return `/chat?${params.toString()}`;
}
