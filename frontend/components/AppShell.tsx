"use client";

// AppShell — the persistent left sidebar every authenticated page wraps
// itself in. This is the single biggest structural gap being fixed:
// before this, every page had a different, ad-hoc set of links to a
// different subset of other pages, with no consistent "you are here."
//
// Deliberately a plain wrapper component, not a Next.js route-group
// layout — avoids moving any existing page file into a new folder
// structure, which would be real risk to already-working code for a
// purely organizational win. Each page imports <AppShell> and wraps
// its content in it instead of rolling its own header.
//
// Layout/responsive structure lives in globals.css (.app-shell-*
// classes) rather than inline styles — inline styles can't hold media
// queries, and below 768px this collapses into a fixed bottom tab bar
// instead of squeezing a 220px sidebar onto a phone screen. Only the
// per-item ACTIVE state (genuinely dynamic, depends on the current
// route) stays inline.

import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { clearApiKey } from "@/lib/api";

// Grouped into sections so genuinely related pages read as related,
// rather than sitting scattered through one long, flat list. The SEC
// & Conviction group is also ordered by the real, established
// workflow (screen the market → get the quick read on one ticker →
// verify the underlying filings), not alphabetically or by build
// order, matching the cross-links already wired between these pages.
const NAV_SECTIONS: { label: string | null; items: { href: string; label: string; icon: string }[] }[] = [
  {
    label: null,
    items: [
      { href: "/dashboard", label: "Dashboard", icon: "◆" },
      { href: "/growth-hunter", label: "Growth Hunter", icon: "◎" },
      { href: "/chat", label: "Chat", icon: "◐" },
      { href: "/universe", label: "Universe", icon: "◈" },
      { href: "/nasdaq100-screener", label: "Nasdaq-100 Screener", icon: "▧" },
      { href: "/terminal", label: "Watchlist", icon: "▤" },
      { href: "/portfolios", label: "Portfolios", icon: "▣" },
      { href: "/valuation", label: "Valuation", icon: "◇" },
      { href: "/capital-flow", label: "Capital Flow", icon: "⇄" },
      { href: "/capital-flow-monitor", label: "Flow Monitor", icon: "▦" },
    ],
  },
  {
    label: "SEC & Conviction",
    items: [
      { href: "/conviction-screener", label: "Conviction Screener", icon: "☰" },
      { href: "/sec-research", label: "SEC Research", icon: "◭" },
      { href: "/institutional-holdings", label: "13F Holdings", icon: "▥" },
    ],
  },
  {
    label: null,
    items: [
      { href: "/brokerage", label: "Trading", icon: "$" },
      { href: "/alerts", label: "Alerts", icon: "◉" },
    ],
  },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  function logout() {
    clearApiKey();
    router.push("/login");
  }

  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      <nav className="app-shell-nav">
        <Link href="/dashboard" className="app-shell-logo" style={{ textDecoration: "none", display: "block" }}>
          <p className="eyebrow" style={{ margin: 0 }}>Conviction</p>
        </Link>

        <div className="app-shell-items">
          {NAV_SECTIONS.map((section, sectionIndex) => (
            <div key={section.label ?? `section-${sectionIndex}`}>
              {section.label && (
                <p
                  className="num"
                  style={{
                    fontSize: "0.7rem", opacity: 0.5, textTransform: "uppercase",
                    letterSpacing: "0.04em", margin: "1rem 0 0.35rem", padding: "0 0.75rem",
                  }}
                >
                  {section.label}
                </p>
              )}
              {section.items.map((item) => {
                const active = pathname === item.href || pathname?.startsWith(item.href + "/");
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.75rem",
                      padding: "0.6rem 0.75rem",
                      borderRadius: "4px",
                      textDecoration: "none",
                      fontSize: "0.92rem",
                      color: active ? "var(--accent)" : "var(--text)",
                      background: active ? "rgba(94,184,199,0.1)" : "transparent",
                      fontWeight: active ? 600 : 400,
                      transition: "background 0.12s ease",
                    }}
                  >
                    <span className="num" style={{ fontSize: "0.9rem", opacity: active ? 1 : 0.55, width: "1rem" }}>
                      {item.icon}
                    </span>
                    {item.label}
                  </Link>
                );
              })}
            </div>
          ))}
        </div>

        <button onClick={logout} className="num app-shell-logout">
          Log out
        </button>
      </nav>

      <main className="app-shell-main">{children}</main>
    </div>
  );
}
