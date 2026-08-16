// Tests for the API client. Cannot be run in the environment that
// wrote them — no network access to install vitest's dependencies
// here. Written carefully against known-correct Vitest conventions and
// needs to be verified by actually running `npm test`, same as every
// other frontend change this session that needed a real environment
// this sandbox doesn't have.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  api,
  getApiKey,
  setApiKey,
  clearApiKey,
  ApiError,
} from "./api";

function mockFetchOnce(body: unknown, status = 200, ok = status < 400) {
  const response = {
    ok,
    status,
    statusText: ok ? "OK" : "Error",
    json: async () => body,
  } as Response;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
  return (global.fetch as ReturnType<typeof vi.fn>);
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("API key storage", () => {
  it("returns null when no key is stored", () => {
    expect(getApiKey()).toBeNull();
  });

  it("round-trips a key through set/get", () => {
    setApiKey("fi_live_test123");
    expect(getApiKey()).toBe("fi_live_test123");
  });

  it("clearApiKey removes the stored key", () => {
    setApiKey("fi_live_test123");
    clearApiKey();
    expect(getApiKey()).toBeNull();
  });
});

describe("request() — the shared fetch wrapper", () => {
  it("attaches X-Api-Key when a key is stored", async () => {
    setApiKey("fi_live_test123");
    const fetchMock = mockFetchOnce({ ok: true });

    await api.getWatchlist();

    const [, options] = fetchMock.mock.calls[0];
    expect((options.headers as Record<string, string>)["X-Api-Key"]).toBe("fi_live_test123");
  });

  it("does not attach X-Api-Key when no key is stored", async () => {
    const fetchMock = mockFetchOnce([]);

    await api.getWatchlist();

    const [, options] = fetchMock.mock.calls[0];
    expect((options.headers as Record<string, string> | undefined)?.["X-Api-Key"]).toBeUndefined();
  });

  it("throws ApiError with the backend's detail message on failure", async () => {
    mockFetchOnce({ detail: "Ticker not found" }, 404, false);

    await expect(api.getFactorScore("NOTREAL")).rejects.toThrow(ApiError);
    await expect(api.getFactorScore("NOTREAL")).rejects.toMatchObject({
      status: 404,
      message: "Ticker not found",
    });
  });

  it("falls back to statusText when the error body isn't JSON", async () => {
    const response = {
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: async () => {
        throw new Error("not json");
      },
    } as unknown as Response;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));

    await expect(api.getWatchlist()).rejects.toMatchObject({
      status: 500,
      message: "Internal Server Error",
    });
  });
});

describe("constructRiskParity — sends a JSON body, not query params", () => {
  // This exact function had a REAL, confirmed production bug earlier
  // this session: FastAPI expects a JSON body for a list[str]
  // parameter, not repeated query params, and the original
  // implementation got that backwards, causing a live 422. This test
  // exists specifically so that regression can never come back
  // silently.
  it("sends tickers and total_investment as a JSON body", async () => {
    const fetchMock = mockFetchOnce({ allocations: [] });

    await api.constructRiskParity(["nvda", "amd"], 10000);

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/portfolios/construct-risk-parity");
    expect(url).not.toContain("tickers="); // must NOT be in the query string
    expect(options.method).toBe("POST");
    expect(options.headers["Content-Type"]).toBe("application/json");
    const body = JSON.parse(options.body as string);
    expect(body).toEqual({ tickers: ["NVDA", "AMD"], total_investment: 10000 });
  });
});

describe("ingestEtf — separate path from ingestion", () => {
  it("posts to the ETF-specific ingest path, uppercasing the ticker", async () => {
    const fetchMock = mockFetchOnce({ ticker: "SPY", name: "SPDR S&P 500", expense_ratio: 0.09, aum: 1e11 });

    await api.ingestEtf("spy");

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/companies/SPY/ingest-etf");
    expect(options.method).toBe("POST");
  });
});

describe("getUpcomingEarnings — optional list_name param", () => {
  it("omits list_name from the query string when not given", async () => {
    const fetchMock = mockFetchOnce({ events: [] });

    await api.getUpcomingEarnings();

    const [url] = fetchMock.mock.calls[0];
    expect(url).not.toContain("list_name");
    expect(url).toContain("lookahead_days=14");
  });

  it("includes list_name when given", async () => {
    const fetchMock = mockFetchOnce({ events: [] });

    await api.getUpcomingEarnings("Growth");

    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain("list_name=Growth");
  });
});

describe("signUp / logIn — real auth, JSON body not query params", () => {
  it("signUp posts email and password as a JSON body", async () => {
    const fetchMock = mockFetchOnce({ plaintext_key: "fi_live_abc", user_id: "alice@example.com" });

    await api.signUp("Alice@Example.com", "correcthorse");

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/auth/signup");
    expect(options.method).toBe("POST");
    const body = JSON.parse(options.body as string);
    expect(body).toEqual({ email: "Alice@Example.com", password: "correcthorse" });
  });

  it("logIn posts email and password as a JSON body", async () => {
    const fetchMock = mockFetchOnce({ plaintext_key: "fi_live_abc", user_id: "alice@example.com" });

    await api.logIn("alice@example.com", "correcthorse");

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/auth/login");
    expect(options.method).toBe("POST");
    const body = JSON.parse(options.body as string);
    expect(body).toEqual({ email: "alice@example.com", password: "correcthorse" });
  });

  it("logIn surfaces the backend's deliberately vague error on failure", async () => {
    mockFetchOnce({ detail: "Invalid email or password." }, 401, false);

    await expect(api.logIn("alice@example.com", "wrongpassword")).rejects.toMatchObject({
      status: 401,
      message: "Invalid email or password.",
    });
  });
});
