"use client";

import { useState, useEffect, useRef } from "react";
import { useChat } from "@ai-sdk/react";
import { TextStreamChatTransport } from "ai";
import { getApiKey } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://p8xpcshdn9.us-east-1.awsapprunner.com";

// Real contract, confirmed directly from the installed package's own
// .d.ts files (not inferred from docs/search, which turned out to
// describe an older API surface entirely — see the ChatPanel commit
// history for the debugging trail). useChat in this version returns
// `sendMessage`/`messages`/`status`/`error` — NOT `input`/
// `handleInputChange`/`handleSubmit`, which belong to the separate
// `useCompletion` hook. The transport needs to be TextStreamChatTransport
// specifically, since our backend streams plain text, not the default
// typed UI-message-stream protocol.
function getMessageText(message: any): string {
  if (typeof message.content === "string") return message.content;
  if (Array.isArray(message.parts)) {
    return message.parts
      .filter((p: any) => p.type === "text")
      .map((p: any) => p.text)
      .join("");
  }
  return "";
}

export function ChatPanel() {
  const [input, setInput] = useState("");
  const [transport] = useState(
    () =>
      new TextStreamChatTransport({
        api: `${API_URL}/chat/stream`,
        headers: { "X-Api-Key": getApiKey() || "" },
      })
  );
  const { messages, sendMessage, status, error } = useChat({ transport } as any);

  const isLoading = status === "submitted" || status === "streaming";
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    sendMessage({ text: input });
    setInput("");
  }

  return (
    <section>
      <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>
        Ask FinInsight
      </p>
      <div className="card" style={{ display: "flex", flexDirection: "column", height: 380 }}>
        <div style={{ flex: 1, overflowY: "auto", marginBottom: "1rem" }}>
          {messages.length === 0 && (
            <p style={{ color: "var(--text-soft)", fontSize: "0.9rem", lineHeight: 1.6 }}>
              Ask about your watchlist, portfolios, or any company —
              e.g. &ldquo;what&rsquo;s my riskiest position?&rdquo; or
              &ldquo;add TSLA to my watchlist.&rdquo;
            </p>
          )}
          {messages.map((m: any) => (
            <div
              key={m.id}
              style={{
                marginBottom: "1rem",
                textAlign: m.role === "user" ? "right" : "left",
              }}
            >
              <span
                className={m.role === "user" ? "num" : ""}
                style={{
                  display: "inline-block",
                  maxWidth: "85%",
                  padding: "0.6rem 0.85rem",
                  borderRadius: "6px",
                  fontSize: "0.9rem",
                  lineHeight: 1.5,
                  background: m.role === "user" ? "var(--accent)" : "var(--surface)",
                  color: m.role === "user" ? "#0d1215" : "var(--text)",
                  border: m.role === "user" ? "none" : "1px solid var(--rule)",
                  textAlign: "left",
                }}
              >
                {getMessageText(m)}
              </span>
            </div>
          ))}
          {isLoading && (
            <p className="num" style={{ color: "var(--text-soft)", fontSize: "0.85rem" }}>
              thinking…
            </p>
          )}
          {error && (
            <p className="num loss" style={{ fontSize: "0.85rem" }}>
              {error.message || "Something went wrong."}
            </p>
          )}
          <div ref={bottomRef} />
        </div>
        <form onSubmit={handleSubmit} style={{ display: "flex", gap: "0.5rem" }}>
          <input
            type="text"
            placeholder="Ask a question…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            style={{ flex: 1, fontSize: "0.9rem" }}
          />
          <button
            type="submit"
            className="btn-primary"
            disabled={isLoading || !input.trim()}
            style={{ padding: "0.55rem 1.1rem", fontSize: "0.9rem" }}
          >
            Send
          </button>
        </form>
      </div>
    </section>
  );
}
