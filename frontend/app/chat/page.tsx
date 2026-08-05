"use client";

// Chat — the AI agent's dedicated, prominent home. Deliberately just
// wraps the existing, already-correct ChatPanel component rather than
// reimplementing chat logic a second time — ChatPanel's exact useChat
// + TextStreamChatTransport setup was hard-won (see its own comments:
// confirmed directly from the installed package's real types after
// documentation-based guesses turned out wrong), and duplicating that
// logic here would just be a second place for the same bug class to
// reappear. This page's only real job is layout: same chat, more room.

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { ChatPanel } from "@/components/ChatPanel";
import { getApiKey } from "@/lib/api";

export default function ChatPage() {
  const router = useRouter();

  useEffect(() => {
    if (!getApiKey()) router.push("/login");
  }, [router]);

  return (
    <AppShell>
      <main style={{ maxWidth: "760px", margin: "0 auto", padding: "2rem 1.5rem 3rem" }}>
        <p className="eyebrow" style={{ margin: 0 }}>Conviction · Chat</p>
        <h1 style={{ margin: "0.3rem 0 1.5rem" }}>Ask anything</h1>
        <ChatPanel height="calc(100vh - 220px)" />
      </main>
    </AppShell>
  );
}
