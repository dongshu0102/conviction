"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, setApiKey, ApiError } from "@/lib/api";

const MIN_PASSWORD_LENGTH = 8;

export default function SignUpPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim() || !password) return;
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
      const result = await api.signUp(email.trim(), password);
      setApiKey(result.plaintext_key);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the server. Check your connection and try again.");
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
        <h1 style={{ fontSize: "2rem", marginBottom: "0.75rem" }}>Start with the real numbers.</h1>
        <p style={{ color: "var(--text-soft)", marginBottom: "2rem", lineHeight: 1.6 }}>
          Real email and password now — this account is yours alone, and no one
          else can mint a key under your identity without knowing this password.
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
          <input
            type="password"
            placeholder={`Password (min ${MIN_PASSWORD_LENGTH} characters)`}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
          />
          <input
            type="password"
            placeholder="Confirm password"
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
            {loading ? "Creating account…" : "Create account"}
          </button>
        </form>
        <p style={{ marginTop: "1.5rem", fontSize: "0.9rem", color: "var(--text-soft)" }}>
          Already have an account?{" "}
          <Link href="/login" style={{ color: "var(--accent)" }}>
            Log in
          </Link>
        </p>
      </div>
    </main>
  );
}
