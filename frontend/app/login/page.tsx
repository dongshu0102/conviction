"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setApiKey } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.createApiKey(name.trim(), "web-frontend");
      setApiKey(result.plaintext_key);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "2rem",
      }}
    >
      <div style={{ maxWidth: 420, width: "100%" }}>
        <p className="eyebrow" style={{ marginBottom: "0.5rem" }}>
          FinInsight
        </p>
        <h1 style={{ fontSize: "2rem", marginBottom: "0.75rem" }}>Open your ledger.</h1>
        <p style={{ color: "var(--text-soft)", marginBottom: "2rem", lineHeight: 1.6 }}>
          Enter a name to identify your account. This creates an access key stored
          only in this browser — there&rsquo;s no password yet, so don&rsquo;t use
          this for anything you wouldn&rsquo;t want someone with this device to see.
        </p>
        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <input
            type="text"
            placeholder="Your name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
          />
          {error && (
            <p className="num loss" style={{ fontSize: "0.9rem" }}>
              {error}
            </p>
          )}
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? "Opening…" : "Continue"}
          </button>
        </form>
      </div>
    </main>
  );
}
