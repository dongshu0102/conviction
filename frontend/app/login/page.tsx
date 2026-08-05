"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, setApiKey, ApiError } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim() || !password) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.logIn(email.trim(), password);
      setApiKey(result.plaintext_key);
      router.push("/dashboard");
    } catch (err) {
      // Deliberately the same message the backend gives for both a
      // wrong password and an unregistered email — never confirm
      // which one it was.
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
        <h1 style={{ fontSize: "2rem", marginBottom: "0.75rem" }}>Open your ledger.</h1>
        <p style={{ color: "var(--text-soft)", marginBottom: "2rem", lineHeight: 1.6 }}>
          Log in with your email and password.
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
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
          <Link
            href="/forgot-password"
            className="num"
            style={{ fontSize: "0.85rem", color: "var(--text-soft)", alignSelf: "flex-end" }}
          >
            Forgot password?
          </Link>
          {error && (
            <p className="num loss" style={{ fontSize: "0.9rem" }}>
              {error}
            </p>
          )}
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? "Logging in…" : "Log in"}
          </button>
        </form>
        <p style={{ marginTop: "1.5rem", fontSize: "0.9rem", color: "var(--text-soft)" }}>
          New here?{" "}
          <Link href="/signup" style={{ color: "var(--accent)" }}>
            Create an account
          </Link>
        </p>
      </div>
    </main>
  );
}
