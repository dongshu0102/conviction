"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, setApiKey, ApiError } from "@/lib/api";

const MIN_PASSWORD_LENGTH = 8;

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!password) return;
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords don't match.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await api.resetPassword(token, password);
      setApiKey(result.plaintext_key);
      router.push("/dashboard");
    } catch (err) {
      // The backend returns the same message for "invalid token" and
      // "expired token" — deliberately, no reason to distinguish them
      // for the user beyond "this link no longer works."
      setError(err instanceof ApiError ? err.message : "Couldn't reach the server. Check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }

  if (!token) {
    return (
      <div style={{ maxWidth: 420, width: "100%" }}>
        <p className="eyebrow" style={{ marginBottom: "0.5rem" }}>
          Conviction
        </p>
        <h1 style={{ fontSize: "2rem", marginBottom: "0.75rem" }}>Missing reset link.</h1>
        <p style={{ color: "var(--text-soft)", lineHeight: 1.6, marginBottom: "1.5rem" }}>
          This page needs a reset token from the link in your email.
        </p>
        <Link href="/forgot-password" style={{ color: "var(--accent)", fontSize: "0.9rem" }}>
          Request a new reset link →
        </Link>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 420, width: "100%" }}>
      <p className="eyebrow" style={{ marginBottom: "0.5rem" }}>
        Conviction
      </p>
      <h1 style={{ fontSize: "2rem", marginBottom: "0.75rem" }}>Choose a new password.</h1>
      <p style={{ color: "var(--text-soft)", marginBottom: "2rem", lineHeight: 1.6 }}>
        This also signs out every device using your old password — you&rsquo;ll
        be logged in fresh here once this completes.
      </p>
      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <input
          type="password"
          placeholder={`New password (min ${MIN_PASSWORD_LENGTH} characters)`}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
          autoComplete="new-password"
        />
        <input
          type="password"
          placeholder="Confirm new password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          autoComplete="new-password"
        />
        {error && (
          <p className="num loss" style={{ fontSize: "0.9rem" }}>
            {error}
          </p>
        )}
        <button type="submit" className="btn-primary" disabled={loading}>
          {loading ? "Resetting…" : "Reset password"}
        </button>
      </form>
    </div>
  );
}

export default function ResetPasswordPage() {
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
      {/* useSearchParams needs a Suspense boundary in the App Router —
          without it, the page fails to build/render correctly. */}
      <Suspense fallback={<p className="num" style={{ color: "var(--text-soft)" }}>Loading…</p>}>
        <ResetPasswordForm />
      </Suspense>
    </main>
  );
}
