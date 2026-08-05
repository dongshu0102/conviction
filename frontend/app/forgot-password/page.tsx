"use client";

import { useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Deliberately a single generic message shown on success, regardless
  // of whether the email is actually registered — matching the backend's
  // own account-enumeration defense. Never render anything that would
  // let someone distinguish "sent" from "no such account."
  const [submitted, setSubmitted] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await api.forgotPassword(email.trim());
      setSubmitted(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
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
          Conviction
        </p>
        <h1 style={{ fontSize: "2rem", marginBottom: "0.75rem" }}>Reset your password.</h1>

        {submitted ? (
          <>
            <p style={{ color: "var(--text-soft)", lineHeight: 1.6, marginBottom: "1.5rem" }}>
              If an account exists for that email, a password reset link has
              been sent. It expires in 1 hour.
            </p>
            <Link href="/login" style={{ color: "var(--accent)", fontSize: "0.9rem" }}>
              ← Back to log in
            </Link>
          </>
        ) : (
          <>
            <p style={{ color: "var(--text-soft)", marginBottom: "2rem", lineHeight: 1.6 }}>
              Enter your email and we&rsquo;ll send a reset link.
            </p>
            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <input
                type="email"
                placeholder="Email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoFocus
                autoComplete="email"
              />
              {error && (
                <p className="num loss" style={{ fontSize: "0.9rem" }}>
                  {error}
                </p>
              )}
              <button type="submit" className="btn-primary" disabled={loading}>
                {loading ? "Sending…" : "Send reset link"}
              </button>
            </form>
            <p style={{ marginTop: "1.5rem", fontSize: "0.9rem", color: "var(--text-soft)" }}>
              <Link href="/login" style={{ color: "var(--accent)" }}>
                Back to log in
              </Link>
            </p>
          </>
        )}
      </div>
    </main>
  );
}
