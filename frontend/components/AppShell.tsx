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

import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { clearApiKey } from "@/lib/api";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: "◆" },
  { href: "/terminal", label: "Watchlist", icon: "▤" },
  { href: "/universe", label: "Universe", icon: "◈" },
  { href: "/portfolios", label: "Portfolios", icon: "▣" },
  { href: "/chat", label: "Chat", icon: "◐" },
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
      <nav
        style={{
          width: "220px",
          flexShrink: 0,
          borderRight: "1px solid var(--rule)",
          padding: "1.75rem 1rem",
          display: "flex",
          flexDirection: "column",
          position: "sticky",
          top: 0,
          height: "100vh",
        }}
      >
        <Link href="/dashboard" style={{ textDecoration: "none", marginBottom: "2.5rem", display: "block" }}>
          <p className="eyebrow" style={{ margin: 0 }}>FinInsight</p>
        </Link>

        <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem", flex: 1 }}>
          {NAV_ITEMS.map((item) => {
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

        <button
          onClick={logout}
          className="num"
          style={{
            background: "none",
            border: "none",
            color: "var(--text-soft)",
            fontSize: "0.82rem",
            padding: "0.6rem 0.75rem",
            textAlign: "left",
            cursor: "pointer",
          }}
        >
          Log out
        </button>
      </nav>

      <main style={{ flex: 1, minWidth: 0 }}>{children}</main>
    </div>
  );
}
