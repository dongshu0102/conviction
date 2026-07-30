"use client";

import { useState } from "react";

export function InlineAddForm({
  placeholder,
  buttonLabel,
  onSubmit,
  uppercase,
}: {
  placeholder: string;
  buttonLabel: string;
  onSubmit: (value: string) => Promise<void>;
  uppercase?: boolean;
}) {
  const [value, setValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!value.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await onSubmit(value.trim());
      setValue("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      style={{ display: "flex", gap: "0.5rem", marginTop: "1rem", alignItems: "flex-start" }}
    >
      <div style={{ flex: 1 }}>
        <input
          type="text"
          placeholder={placeholder}
          value={value}
          onChange={(e) => setValue(uppercase ? e.target.value.toUpperCase() : e.target.value)}
          style={{ width: "100%", fontSize: "0.9rem", padding: "0.55rem 0.75rem" }}
        />
        {error && (
          <p className="num loss" style={{ fontSize: "0.78rem", marginTop: "0.4rem" }}>
            {error}
          </p>
        )}
      </div>
      <button
        type="submit"
        className="btn-primary"
        disabled={loading}
        style={{ padding: "0.55rem 1.1rem", fontSize: "0.9rem", whiteSpace: "nowrap" }}
      >
        {loading ? "…" : buttonLabel}
      </button>
    </form>
  );
}
