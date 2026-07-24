"use client";

import { ChatComposer, ChatComposerInput } from "@astryxdesign/core/Chat";
import { Theme } from "@astryxdesign/core/theme";
import { neutralTheme } from "@astryxdesign/theme-neutral/built";
import {
  ArrowUpRight,
  ChevronDown,
  Menu,
  Plus,
  RefreshCw,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

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

type CitationRecord = {
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
  refusal_reason:
    | "not_in_corpus"
    | "insufficient_support"
    | "ambiguous_question"
    | "rate_limited"
    | null;
  citations: CitationRecord[];
  disclaimer: string;
  latency_ms: number;
};

type ChatQueryResponse = {
  conversation: Conversation;
};

type MessageStatus = "complete" | "pending" | "error" | "stopped";

type ConversationMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
  status: MessageStatus;
  response?: QueryResponse;
  error?: string;
};

type Conversation = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: ConversationMessage[];
};

const MAX_QUERY_LENGTH = 800;
const REQUEST_TIMEOUT_MS = 45_000;
const MAX_SAVED_CONVERSATIONS = 20;
const CHAT_API_BASE = "/chat-api/conversations";

const SUGGESTED_QUESTIONS = [
  {
    label: "Customer due diligence",
    question:
      "What customer due diligence steps apply to individual customers?",
  },
  {
    label: "Analyst disclosures",
    question: "What does SEBI require research analysts to disclose?",
  },
  {
    label: "MSME loan restructuring",
    question: "When may an MSME loan be restructured under RBI directions?",
  },
];

const REFUSAL_COPY: Record<NonNullable<QueryResponse["refusal_reason"]>, string> = {
  not_in_corpus:
    "The indexed RBI and SEBI documents do not cover this question.",
  insufficient_support:
    "Related material was found, but it was not strong enough to support a reliable answer.",
  ambiguous_question:
    "A little more detail is needed before this can be answered from the official corpus.",
  rate_limited:
    "This demo has reached its query limit for your connection. Please try again later.",
};

function createUuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (part) => {
    const value = Math.floor(Math.random() * 16);
    const digit = part === "x" ? value : (value & 0x3) | 0x8;
    return digit.toString(16);
  });
}

function titleFromQuestion(question: string): string {
  const compact = question.replace(/\s+/g, " ").trim();
  return compact.length > 46 ? `${compact.slice(0, 43).trim()}...` : compact;
}

function isConversation(value: unknown): value is Conversation {
  if (!value || typeof value !== "object") {
    return false;
  }

  const candidate = value as Partial<Conversation>;
  return (
    typeof candidate.id === "string" &&
    typeof candidate.title === "string" &&
    typeof candidate.createdAt === "string" &&
    typeof candidate.updatedAt === "string" &&
    Array.isArray(candidate.messages) &&
    candidate.messages.every((message) => {
      if (!message || typeof message !== "object") {
        return false;
      }
      const storedMessage = message as Partial<ConversationMessage>;
      return (
        typeof storedMessage.id === "string" &&
        (storedMessage.role === "user" || storedMessage.role === "assistant") &&
        typeof storedMessage.content === "string" &&
        typeof storedMessage.createdAt === "string" &&
        ["complete", "pending", "error", "stopped"].includes(
          storedMessage.status ?? "",
        )
      );
    })
  );
}

function isChatQueryResponse(value: unknown): value is ChatQueryResponse {
  return (
    !!value &&
    typeof value === "object" &&
    "conversation" in value &&
    isConversation((value as Partial<ChatQueryResponse>).conversation)
  );
}

async function parseJson(response: Response): Promise<unknown> {
  return response.json().catch(() => null);
}

async function loadServerConversations(): Promise<Conversation[]> {
  const response = await fetch(CHAT_API_BASE, { cache: "no-store" });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(getResponseError(payload, response.status));
  }
  if (
    !payload ||
    typeof payload !== "object" ||
    !Array.isArray((payload as { conversations?: unknown }).conversations)
  ) {
    throw new Error("Chat history could not be loaded.");
  }
  return (payload as { conversations: unknown[] }).conversations
    .filter(isConversation)
    .slice(0, MAX_SAVED_CONVERSATIONS);
}

async function createServerConversation(): Promise<Conversation> {
  const response = await fetch(CHAT_API_BASE, { method: "POST" });
  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(getResponseError(payload, response.status));
  }
  if (!isConversation(payload)) {
    throw new Error("A new chat could not be created.");
  }
  return payload;
}

async function deleteServerConversation(conversationId: string): Promise<void> {
  const response = await fetch(
    `${CHAT_API_BASE}/${encodeURIComponent(conversationId)}`,
    { method: "DELETE" },
  );
  if (!response.ok && response.status !== 404) {
    const payload = await parseJson(response);
    throw new Error(getResponseError(payload, response.status));
  }
}

function getResponseError(payload: unknown, status: number): string {
  if (status >= 500) {
    return "The query service is temporarily unavailable. Please try again.";
  }

  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
  }

  return "The query could not be completed. Please review it and try again.";
}

function safeSourceUrl(sourceUrl: string): string | undefined {
  try {
    const parsedUrl = new URL(sourceUrl);
    return parsedUrl.protocol === "https:" || parsedUrl.protocol === "http:"
      ? sourceUrl
      : undefined;
  } catch {
    return undefined;
  }
}

function sourceLine(citation: CitationRecord): string {
  return citation.section_title
    ? `${citation.doc_title}, ${citation.section_title}`
    : citation.doc_title;
}

function SourceReference({ citation }: { citation: CitationRecord }) {
  const url = safeSourceUrl(citation.source_url);
  const body = (
    <>
      <span className="source-doc">{citation.doc_title}</span>
      {citation.section_title ? (
        <span className="source-sec">, {citation.section_title}</span>
      ) : null}
    </>
  );

  if (!url) {
    return <span className="source-ref">{body}</span>;
  }

  return (
    <a className="source-ref" href={url} target="_blank" rel="noreferrer">
      {body}
      <ArrowUpRight size={13} className="source-ext" aria-hidden="true" />
    </a>
  );
}

function AnswerContent({ response }: { response: QueryResponse }) {
  const { citations } = response;
  const count = citations.length;

  return (
    <div className="answer">
      <p className="answer-text">{response.answer}</p>

      {count > 0 ? (
        <div className="answer-sources">
          <div className="sources-label">
            {count === 1 ? "Source" : "Sources"}
          </div>
          <ol className="sources">
            {citations.map((citation, index) => (
              <li key={citation.chunk_id} className="source">
                <span className="source-n">{index + 1}</span>
                <span className="reg">{citation.regulator}</span>
                <SourceReference citation={citation} />
              </li>
            ))}
          </ol>

          <details className="evidence-block">
            <summary className="evidence-toggle">
              Read the {count === 1 ? "excerpt" : "excerpts"}
              <ChevronDown size={15} className="evidence-chev" aria-hidden="true" />
            </summary>
            <div className="evidence-list">
              {citations.map((citation, index) => {
                const url = safeSourceUrl(citation.source_url);
                const location = citation.page
                  ? `Page ${citation.page}`
                  : "HTML source";
                return (
                  <figure key={citation.chunk_id} className="evidence">
                    <figcaption className="evidence-meta">
                      <span className="source-n">{index + 1}</span>
                      <span className="reg">{citation.regulator}</span>
                      <span className="evidence-loc">{location}</span>
                    </figcaption>
                    <div className="evidence-doc">{sourceLine(citation)}</div>
                    <blockquote className="evidence-quote">
                      {citation.quote}
                    </blockquote>
                    {url ? (
                      <a
                        className="link"
                        href={url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Open official source
                      </a>
                    ) : null}
                  </figure>
                );
              })}
            </div>
          </details>
        </div>
      ) : null}
    </div>
  );
}

function RefusalContent({ response }: { response: QueryResponse }) {
  const reason = response.refusal_reason;
  const isRateLimited = reason === "rate_limited";
  const description = reason
    ? REFUSAL_COPY[reason]
    : "The corpus did not support a reliable answer to this question.";

  return (
    <div className="note">
      <span className="note-title">
        {isRateLimited ? "Query limit reached" : "No grounded answer"}
      </span>
      <p className="note-body">{description}</p>
    </div>
  );
}

function FailureContent({
  message,
  onRetry,
}: {
  message: ConversationMessage;
  onRetry: (messageId: string) => void;
}) {
  const wasStopped = message.status === "stopped";
  return (
    <div className="note">
      <span className="note-title">
        {wasStopped ? "Response stopped" : "Response failed"}
      </span>
      <p className="note-body">
        {message.error ?? "The query could not be completed. Please try again."}
      </p>
      <button
        type="button"
        className="note-retry"
        onClick={() => onRetry(message.id)}
      >
        <RefreshCw size={14} aria-hidden="true" />
        Try again
      </button>
    </div>
  );
}

function PendingContent() {
  return (
    <div className="pending" role="status" aria-label="Searching the corpus">
      <span>Searching the corpus</span>
      <span className="pending-dots" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
    </div>
  );
}

function Transcript({
  messages,
  onRetry,
  stillIds,
}: {
  messages: ConversationMessage[];
  onRetry: (messageId: string) => void;
  stillIds: Set<string>;
}) {
  return (
    <div className="thread">
      {messages.map((message) => {
        const entrance = stillIds.has(message.id) ? "" : " turn-in";
        if (message.role === "user") {
          return (
            <div
              key={message.id}
              data-mid={message.id}
              className={`turn turn-q${entrance}`}
            >
              <p className="question">{message.content}</p>
            </div>
          );
        }

        let body: React.ReactNode;
        if (message.status === "pending") {
          body = <PendingContent />;
        } else if (message.status === "error" || message.status === "stopped") {
          body = <FailureContent message={message} onRetry={onRetry} />;
        } else if (message.response?.status === "answered") {
          body = <AnswerContent response={message.response} />;
        } else if (message.response) {
          body = <RefusalContent response={message.response} />;
        } else {
          body = null;
        }

        return (
          <div
            key={message.id}
            data-mid={message.id}
            className={`turn turn-a${entrance}`}
          >
            {body}
          </div>
        );
      })}
    </div>
  );
}

export default function ChatConsole() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState("");
  const [draft, setDraft] = useState("");
  const [composerError, setComposerError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isHistoryBusy, setIsHistoryBusy] = useState(false);
  const [isHydrated, setIsHydrated] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const stopRequestedRef = useRef(false);
  const pendingHandoffRef = useRef<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const workRef = useRef<HTMLDivElement | null>(null);
  const pendingScrollRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      try {
        const params = new URLSearchParams(window.location.search);
        const handoff = params.get("q")?.trim() ?? "";
        const forceNew = params.get("new") === "1";
        let initialConversations = await loadServerConversations();

        if (handoff) {
          window.history.replaceState(null, "", window.location.pathname);
        }

        if (forceNew) {
          const conversation = await createServerConversation();
          initialConversations = [
            conversation,
            ...initialConversations.filter((item) => item.id !== conversation.id),
          ];
          if (handoff) {
            pendingHandoffRef.current = handoff;
          }
        } else if (initialConversations.length === 0) {
          initialConversations = [await createServerConversation()];
          if (handoff) {
            pendingHandoffRef.current = handoff;
          }
        } else if (handoff) {
          pendingHandoffRef.current = handoff;
        }

        if (cancelled) {
          return;
        }
        setConversations(initialConversations);
        setActiveConversationId(initialConversations[0]?.id ?? "");
        setHistoryError("");
      } catch (caught) {
        if (cancelled) {
          return;
        }
        setHistoryError(
          caught instanceof Error
            ? caught.message
            : "Chat history could not be loaded.",
        );
      } finally {
        if (!cancelled) {
          setIsHydrated(true);
        }
      }
    }

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  // Lock the viewport to the console shell (the landing page scrolls freely).
  useEffect(() => {
    document.documentElement.dataset.route = "chat";
    return () => {
      delete document.documentElement.dataset.route;
    };
  }, []);

  // Close the mobile sidebar with Escape.
  useEffect(() => {
    if (!sidebarOpen) {
      return;
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setSidebarOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sidebarOpen]);

  const activeConversation = useMemo(
    () =>
      conversations.find(
        (conversation) => conversation.id === activeConversationId,
      ),
    [activeConversationId, conversations],
  );

  const messages = activeConversation?.messages ?? [];

  // Submit a landing-page handoff after server history has selected the target
  // conversation. `/chat?new=1&q=...` targets a fresh conversation.
  useEffect(() => {
    if (!isHydrated || !activeConversation || isLoading) {
      return;
    }
    const handoff = pendingHandoffRef.current;
    if (!handoff) {
      return;
    }
    pendingHandoffRef.current = null;
    submitMessage(handoff);
    // submitMessage intentionally consumes the captured handoff once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeConversation, isHydrated, isLoading]);

  // Turns present when a conversation is opened render still; only turns
  // added afterwards get the entrance animation.
  const stillIds = useMemo(
    () =>
      new Set(
        conversations
          .find((conversation) => conversation.id === activeConversationId)
          ?.messages.map((message) => message.id) ?? [],
      ),
    // Snapshot only when the active conversation changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeConversationId],
  );

  // Opening a conversation resumes at its latest turn.
  useEffect(() => {
    const node = scrollRef.current;
    if (node) {
      node.scrollTop = node.scrollHeight;
    }
  }, [activeConversationId]);

  // A just-asked question scrolls to the top of the reading column so the
  // answer unfolds below it instead of yanking the view to the bottom.
  useEffect(() => {
    const targetId = pendingScrollRef.current;
    if (!targetId) {
      return;
    }
    pendingScrollRef.current = null;
    scrollRef.current
      ?.querySelector(`[data-mid="${targetId}"]`)
      ?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [messages.length]);

  // Land the cursor in the composer when a keyboard is the likely input.
  useEffect(() => {
    if (!isHydrated || messages.length > 0) {
      return;
    }
    if (!window.matchMedia("(min-width: 52rem) and (hover: hover)").matches) {
      return;
    }
    workRef.current
      ?.querySelector<HTMLElement>('[role="textbox"][contenteditable="true"]')
      ?.focus({ preventScroll: true });
  }, [isHydrated, messages.length]);

  function updateAssistantMessage(
    conversationId: string,
    messageId: string,
    update: Partial<ConversationMessage>,
  ) {
    setConversations((current) =>
      current.map((conversation) =>
        conversation.id === conversationId
          ? {
              ...conversation,
              updatedAt: new Date().toISOString(),
              messages: conversation.messages.map((message) =>
                message.id === messageId ? { ...message, ...update } : message,
              ),
            }
          : conversation,
      ),
    );
  }

  function replaceConversation(nextConversation: Conversation) {
    setConversations((current) => [
      nextConversation,
      ...current.filter((conversation) => conversation.id !== nextConversation.id),
    ]);
    setActiveConversationId(nextConversation.id);
  }

  async function requestAnswer(
    conversationId: string,
    assistantMessageId: string,
    question: string,
    userMessageId: string,
  ) {
    const controller = new AbortController();
    abortControllerRef.current = controller;
    stopRequestedRef.current = false;
    setIsLoading(true);

    let didTimeout = false;
    const timeoutId = window.setTimeout(() => {
      didTimeout = true;
      controller.abort();
    }, REQUEST_TIMEOUT_MS);

    try {
      const response = await fetch(
        `${CHAT_API_BASE}/${encodeURIComponent(conversationId)}/query`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question,
            user_message_id: userMessageId,
            assistant_message_id: assistantMessageId,
          }),
          signal: controller.signal,
        },
      );
      const payload = await parseJson(response);

      if (isChatQueryResponse(payload)) {
        replaceConversation(payload.conversation);
        return;
      }

      throw new Error(getResponseError(payload, response.status));
    } catch (caught) {
      const wasStopped = stopRequestedRef.current;
      const message = wasStopped
        ? "You stopped this response."
        : didTimeout
          ? "The query took too long to complete."
          : caught instanceof Error
            ? caught.message
            : "The query could not be completed. Please try again.";

      updateAssistantMessage(conversationId, assistantMessageId, {
        status: wasStopped ? "stopped" : "error",
        error: message,
      });
    } finally {
      window.clearTimeout(timeoutId);
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null;
      }
      setIsLoading(false);
    }
  }

  async function requestRetry(
    conversationId: string,
    assistantMessageId: string,
  ) {
    const controller = new AbortController();
    abortControllerRef.current = controller;
    stopRequestedRef.current = false;
    setIsLoading(true);

    let didTimeout = false;
    const timeoutId = window.setTimeout(() => {
      didTimeout = true;
      controller.abort();
    }, REQUEST_TIMEOUT_MS);

    try {
      const response = await fetch(
        `${CHAT_API_BASE}/${encodeURIComponent(
          conversationId,
        )}/messages/${encodeURIComponent(assistantMessageId)}/retry`,
        {
          method: "POST",
          signal: controller.signal,
        },
      );
      const payload = await parseJson(response);

      if (isChatQueryResponse(payload)) {
        replaceConversation(payload.conversation);
        return;
      }

      throw new Error(getResponseError(payload, response.status));
    } catch (caught) {
      const wasStopped = stopRequestedRef.current;
      const message = wasStopped
        ? "You stopped this response."
        : didTimeout
          ? "The query took too long to complete."
          : caught instanceof Error
            ? caught.message
            : "The query could not be completed. Please try again.";

      updateAssistantMessage(conversationId, assistantMessageId, {
        status: wasStopped ? "stopped" : "error",
        error: message,
      });
    } finally {
      window.clearTimeout(timeoutId);
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null;
      }
      setIsLoading(false);
    }
  }

  function submitMessage(rawMessage: string) {
    if (isLoading || isHistoryBusy || !isHydrated) {
      return;
    }

    const question = rawMessage.trim();
    if (!question) {
      setComposerError("Enter a question.");
      return;
    }
    if (question.length > MAX_QUERY_LENGTH) {
      setComposerError(`Keep the message to ${MAX_QUERY_LENGTH} characters.`);
      return;
    }

    if (!activeConversation) {
      setComposerError("Chat history is still loading. Please try again.");
      return;
    }

    const conversation = activeConversation;
    const now = new Date().toISOString();
    const userMessage: ConversationMessage = {
      id: createUuid(),
      role: "user",
      content: question,
      createdAt: now,
      status: "complete",
    };
    const assistantMessage: ConversationMessage = {
      id: createUuid(),
      role: "assistant",
      content: "",
      createdAt: now,
      status: "pending",
    };
    const updatedConversation: Conversation = {
      ...conversation,
      title:
        conversation.messages.length === 0
          ? titleFromQuestion(question)
          : conversation.title,
      updatedAt: now,
      messages: [...conversation.messages, userMessage, assistantMessage],
    };

    replaceConversation(updatedConversation);
    pendingScrollRef.current = userMessage.id;
    setDraft("");
    setComposerError("");
    void requestAnswer(
      conversation.id,
      assistantMessage.id,
      question,
      userMessage.id,
    );
  }

  function retryMessage(messageId: string) {
    if (!activeConversation || isLoading || isHistoryBusy) {
      return;
    }

    updateAssistantMessage(activeConversation.id, messageId, {
      content: "",
      response: undefined,
      status: "pending",
      error: undefined,
      createdAt: new Date().toISOString(),
    });
    void requestRetry(activeConversation.id, messageId);
  }

  function stopResponse() {
    stopRequestedRef.current = true;
    abortControllerRef.current?.abort();
  }

  async function startNewConversation(options: { force?: boolean } = {}) {
    if (isLoading || isHistoryBusy || !isHydrated) {
      return;
    }

    const existingEmpty = options.force
      ? undefined
      : conversations.find((conversation) => conversation.messages.length === 0);
    if (existingEmpty) {
      setActiveConversationId(existingEmpty.id);
      setDraft("");
      setComposerError("");
      return;
    }

    setIsHistoryBusy(true);
    try {
      const conversation = await createServerConversation();
      setConversations((current) => [
        conversation,
        ...current.filter((item) => item.id !== conversation.id),
      ]);
      setActiveConversationId(conversation.id);
      setDraft("");
      setComposerError("");
      setHistoryError("");
    } catch (caught) {
      setComposerError(
        caught instanceof Error ? caught.message : "A new chat could not be created.",
      );
    } finally {
      setIsHistoryBusy(false);
    }
  }

  function selectConversation(conversationId: string) {
    if (isLoading || isHistoryBusy) {
      return;
    }
    setActiveConversationId(conversationId);
    setDraft("");
    setComposerError("");
  }

  async function deleteConversation(conversationId: string) {
    if (isLoading || isHistoryBusy) {
      return;
    }

    setIsHistoryBusy(true);
    try {
      await deleteServerConversation(conversationId);
      let next = conversations.filter(
        (conversation) => conversation.id !== conversationId,
      );
      if (next.length === 0) {
        next = [await createServerConversation()];
      }
      setConversations(next);
      if (conversationId === activeConversationId) {
        setActiveConversationId(next[0]?.id ?? "");
        setDraft("");
        setComposerError("");
      }
      setHistoryError("");
    } catch (caught) {
      setComposerError(
        caught instanceof Error ? caught.message : "This chat could not be deleted.",
      );
    } finally {
      setIsHistoryBusy(false);
    }
  }

  function updateDraft(value: string) {
    if (value.length > MAX_QUERY_LENGTH) {
      setDraft(value.slice(0, MAX_QUERY_LENGTH));
      setComposerError(`Messages are limited to ${MAX_QUERY_LENGTH} characters.`);
      return;
    }
    setDraft(value);
    setComposerError("");
  }

  const isEmpty = messages.length === 0;
  const isBusy = isLoading || isHistoryBusy || !isHydrated;

  const composer = (
    <div className="composer">
      <ChatComposer
        value={draft}
        onChange={updateDraft}
        onSubmit={submitMessage}
        onStop={stopResponse}
        isStopShown={isLoading}
        density="balanced"
        placeholder={
          isEmpty
            ? "Ask a question about RBI or SEBI regulation"
            : "Ask a follow-up"
        }
        input={
          <ChatComposerInput
            label="Message Anchor"
            maxRows={6}
            isDisabled={isBusy}
            pasteAsToken={false}
          />
        }
        headerContext={
          draft.length > MAX_QUERY_LENGTH - 120 ? (
            <span className="composer-count">
              {draft.length}/{MAX_QUERY_LENGTH}
            </span>
          ) : undefined
        }
        status={
          composerError ? { type: "error", message: composerError } : undefined
        }
      />
    </div>
  );

  const composerNote = (
    <p className="composer-note">
      Anchor is an AI system. It answers only from the official corpus. Verify
      against the cited source.
    </p>
  );

  return (
    <Theme theme={neutralTheme} mode="light">
      <div className="workspace" data-open={sidebarOpen}>
        <aside className="side" aria-label="Your questions">
          <div className="side-head">
            <Link
              href="/"
              className="wordmark wordmark-link"
              aria-label="Anchor home"
            >
              <AnchorGlyph size={16} />
              Anchor
            </Link>
            <button
              type="button"
              className="side-close"
              onClick={() => setSidebarOpen(false)}
              aria-label="Close menu"
            >
              <X size={18} aria-hidden="true" />
            </button>
          </div>

          <button
            type="button"
            className="side-new"
            onClick={() => {
              void startNewConversation();
              setSidebarOpen(false);
            }}
            disabled={isBusy}
          >
            <Plus size={16} aria-hidden="true" />
            New question
          </button>

          <p className="side-label">Recent</p>
          <nav className="side-list">
            {conversations.map((conversation) => {
              const hasMessages = conversation.messages.length > 0;
              const title = hasMessages ? conversation.title : "New question";
              return (
                <div
                  key={conversation.id}
                  className="side-item"
                  data-active={conversation.id === activeConversationId}
                >
                  <button
                    type="button"
                    className="side-item-select"
                    disabled={isBusy && conversation.id !== activeConversationId}
                    onClick={() => {
                      selectConversation(conversation.id);
                      setSidebarOpen(false);
                    }}
                  >
                    <span className="side-item-title">{title}</span>
                  </button>
                  {hasMessages ? (
                    <button
                      type="button"
                      className="side-item-delete"
                      aria-label={`Delete "${title}"`}
                      disabled={isBusy}
                      onClick={() => void deleteConversation(conversation.id)}
                    >
                      <Trash2 size={14} aria-hidden="true" />
                    </button>
                  ) : null}
                </div>
              );
            })}
          </nav>

          <p className="side-foot">History is saved to this browser session.</p>
        </aside>

        <button
          type="button"
          className="side-scrim"
          tabIndex={-1}
          aria-hidden="true"
          onClick={() => setSidebarOpen(false)}
        />

        <div className="work" ref={workRef}>
          <header className="work-top">
            <button
              type="button"
              className="icon-btn"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open questions menu"
            >
              <Menu size={18} aria-hidden="true" />
            </button>
            <Link href="/" className="wordmark" aria-label="Anchor home">
              <AnchorGlyph size={15} />
              Anchor
            </Link>
            <button
              type="button"
              className="icon-btn"
              onClick={() => void startNewConversation()}
              aria-label="New question"
              disabled={isBusy}
            >
              <Plus size={18} aria-hidden="true" />
            </button>
          </header>

          {isEmpty ? (
            <div className="hero">
              <div className="hero-inner">
                <h1 className="hero-title">Ask about RBI or SEBI regulation.</h1>
                <p className="hero-sub">
                  Anchor answers only from the official corpus it has indexed,
                  shows the passages behind each answer, and refuses when the
                  documents do not cover your question.
                </p>
                {historyError ? (
                  <div className="note">
                    <span className="note-title">History unavailable</span>
                    <p className="note-body">{historyError}</p>
                  </div>
                ) : null}
                {composer}
                <div className="hero-chips">
                  {SUGGESTED_QUESTIONS.map((suggestion) => (
                    <button
                      key={suggestion.question}
                      type="button"
                      className="chip"
                      onClick={() => submitMessage(suggestion.question)}
                      disabled={isBusy}
                    >
                      {suggestion.label}
                    </button>
                  ))}
                </div>
                {composerNote}
              </div>
            </div>
          ) : (
            <div className="thread-wrap">
              <div className="thread-scroll" ref={scrollRef}>
                <Transcript
                  messages={messages}
                  onRetry={retryMessage}
                  stillIds={stillIds}
                />
              </div>
              <div className="dock">
                <div className="dock-inner">
                  {composer}
                  {composerNote}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </Theme>
  );
}
