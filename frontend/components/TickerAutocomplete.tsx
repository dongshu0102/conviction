"use client";

// Shared ticker autocomplete for pages built around a single-ticker
// search (13F Holdings, 13D/13G, Insider Trades, Conviction Summary).
// Fetches the full, locally-ingested company list once (cheap, no
// live API calls behind it — see GET /companies/list-all's own
// docstring), then filters client-side as the user types. Matches by
// ticker prefix OR a substring of the company name, so "apple" finds
// AAPL just as readily as typing "AAPL" itself.

import { useEffect, useRef, useState } from "react";
import { api, CompanyListItem } from "@/lib/api";

interface TickerAutocompleteProps {
  value: string;
  onChange: (value: string) => void;
  onSelect?: (item: CompanyListItem) => void;
  placeholder?: string;
  style?: React.CSSProperties;
}

const MAX_SUGGESTIONS = 8;

export function TickerAutocomplete({ value, onChange, onSelect, placeholder, style }: TickerAutocompleteProps) {
  const [companies, setCompanies] = useState<CompanyListItem[]>([]);
  const [open, setOpen] = useState(false);
  const [highlightIndex, setHighlightIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // A real, honest failure here (e.g. the endpoint is unreachable)
    // isn't fatal to the page — the plain text input this component
    // wraps still works exactly as it did before autocomplete
    // existed, so failing silently and simply not offering
    // suggestions is the right degradation, not a visible error.
    api.getCompanyList().then((r) => setCompanies(r.companies)).catch(() => {});
  }, []);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const query = value.trim().toUpperCase();
  const suggestions = query
    ? companies
        .filter((c) => c.ticker.startsWith(query) || c.name.toUpperCase().includes(query))
        .slice(0, MAX_SUGGESTIONS)
    : [];

  function selectItem(item: CompanyListItem) {
    onChange(item.ticker);
    onSelect?.(item);
    setOpen(false);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || suggestions.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightIndex((i) => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && suggestions[highlightIndex]) {
      e.preventDefault();
      selectItem(suggestions[highlightIndex]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div ref={containerRef} style={{ position: "relative", flex: style?.flex ?? 1 }}>
      <input
        type="text"
        placeholder={placeholder}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
          setHighlightIndex(0);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={handleKeyDown}
        style={{ width: "100%", padding: "0.6rem 0.9rem", fontSize: "0.95rem", ...style }}
        autoComplete="off"
      />
      {open && suggestions.length > 0 && (
        <div
          style={{
            position: "absolute", top: "100%", left: 0, right: 0, zIndex: 20,
            background: "var(--surface, #16181d)", border: "1px solid var(--border)",
            borderRadius: "0.4rem", marginTop: "0.25rem", overflow: "hidden",
            boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
          }}
        >
          {suggestions.map((s, i) => (
            <div
              key={s.ticker}
              onMouseDown={(e) => {
                e.preventDefault(); // keep the input from blurring before the click registers
                selectItem(s);
              }}
              onMouseEnter={() => setHighlightIndex(i)}
              style={{
                padding: "0.5rem 0.9rem", cursor: "pointer", fontSize: "0.85rem",
                background: i === highlightIndex ? "var(--border)" : "transparent",
                display: "flex", justifyContent: "space-between", gap: "0.75rem",
              }}
            >
              <span className="num" style={{ fontWeight: 700 }}>{s.ticker}</span>
              <span style={{ color: "var(--text-soft)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {s.name}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
