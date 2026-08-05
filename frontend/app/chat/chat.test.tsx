// Tests for the Chat page. Same unverified-in-sandbox caveat.
//
// Deliberately mocks ChatPanel itself, not the @ai-sdk/react hook it
// uses internally — that library's exact current API surface was
// already the reason a plain-fetch implementation was avoided in favor
// of reusing ChatPanel earlier this session (see ChatPanel.tsx's own
// comments on this). Re-mocking useChat here would mean guessing at
// the same unfamiliar API a second time; testing that this PAGE wires
// height/layout correctly around ChatPanel is the safer, still-real
// thing to verify.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import ChatPage from "./page";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/chat",
  useRouter: () => ({ push: pushMock }),
}));

vi.mock("@/components/ChatPanel", () => ({
  ChatPanel: ({ height }: { height?: string | number }) => (
    <div data-testid="chat-panel" data-height={String(height)} />
  ),
}));

beforeEach(() => {
  pushMock.mockClear();
  localStorage.clear();
});

describe("Chat page", () => {
  it("redirects to /login when no API key is stored", () => {
    render(<ChatPage />);
    expect(pushMock).toHaveBeenCalledWith("/login");
  });

  it("renders the page chrome and the (mocked) ChatPanel when authenticated", () => {
    localStorage.setItem("conviction_api_key", "fi_live_test123");
    render(<ChatPage />);

    expect(pushMock).not.toHaveBeenCalled();
    expect(screen.getByText("Ask anything")).toBeInTheDocument();
    expect(screen.getByTestId("chat-panel")).toBeInTheDocument();
  });

  it("gives ChatPanel a full-page height, not the small embedded-card default", () => {
    localStorage.setItem("conviction_api_key", "fi_live_test123");
    render(<ChatPage />);

    const panel = screen.getByTestId("chat-panel");
    expect(panel.dataset.height).not.toBe("380"); // the dashboard-embedded default
    expect(panel.dataset.height).toContain("calc");
  });
});
