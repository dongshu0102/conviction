"""FinInsight MCP server.

Wraps the deployed FinInsight REST API as MCP tools, so Claude Desktop
(or claude.ai, or any MCP client) can read and manage a user's
watchlist, portfolios, and research directly in conversation.

Deliberately a thin HTTP client, not a reimplementation — every tool
here calls the same production API, with the same auth, the same
business logic, the same tests, already built and deployed. Adding a
tool here should never mean writing new backend logic; if it does,
that logic belongs in the API, not here.

Setup:
    1. pip install -r requirements.txt (in this directory)
    2. Get an API key: POST to {API_URL}/auth/signup with {"email", "password"}
    3. Add to Claude Desktop's config (see README.md in this directory)

Environment variables:
    FININSIGHT_API_URL  — defaults to the production deployment
    FININSIGHT_API_KEY  — required, no default (never hardcode a key here)
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server import MCPServer

API_BASE_URL = os.environ.get(
    "FININSIGHT_API_URL", "https://p8xpcshdn9.us-east-1.awsapprunner.com"
)
API_KEY = os.environ.get("FININSIGHT_API_KEY")

# Deliberately NOT validated here — a module-level raise makes this file
# impossible to import at all without a real key set, which breaks
# testing (nothing in tests/ needs a real key; every HTTP call is
# mocked). Confirmed in practice: pytest failed to even COLLECT this
# file before this was moved. The same protection for real usage is
# enforced in main() instead, which is the only thing that actually
# needs a real key to do anything useful.

mcp = MCPServer(
    name="fininsight",
    description="AI financial intelligence platform — watchlists, portfolios, "
    "company research, valuation, and risk analysis grounded in real S&P 500 data.",
)


async def _request(
    method: str, path: str, params: dict[str, Any] | None = None, json: dict[str, Any] | None = None
) -> str:
    """Shared HTTP call + error handling for every tool below. Returns a
    string either way (JSON on success, a plain-English error message on
    failure) since MCP tool results are text — never raises, so a failed
    call becomes information the model can react to, not a crash.
    """
    async with httpx.AsyncClient(
        base_url=API_BASE_URL, headers={"X-Api-Key": API_KEY}, timeout=60.0
    ) as client:
        try:
            response = await client.request(method, path, params=params, json=json)
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as exc:
            return f"Error {exc.response.status_code}: {exc.response.text}"
        except httpx.HTTPError as exc:
            return f"Request failed: {exc}"


# --- Watchlist -------------------------------------------------------------

@mcp.tool()
async def get_watchlist() -> str:
    """Get the user's current stock watchlist, including any notes attached
    to each ticker."""
    return await _request("GET", "/watchlist")


@mcp.tool()
async def add_to_watchlist(ticker: str, notes: str = "") -> str:
    """Add a ticker to the watchlist. The ticker must already be ingested
    into the platform (see ingest_company if it isn't)."""
    params = {"notes": notes} if notes else None
    return await _request("POST", f"/watchlist/{ticker}", params=params)


@mcp.tool()
async def remove_from_watchlist(ticker: str) -> str:
    """Remove a ticker from the watchlist."""
    return await _request("DELETE", f"/watchlist/{ticker}")


# --- Portfolios --------------------------------------------------------------

@mcp.tool()
async def list_portfolios() -> str:
    """List all of the user's portfolios (summary only — use get_portfolio
    for full holdings detail on one portfolio)."""
    return await _request("GET", "/portfolios")


@mcp.tool()
async def get_portfolio(portfolio_id: str) -> str:
    """Get one portfolio's full detail, including every holding."""
    return await _request("GET", f"/portfolios/{portfolio_id}")


@mcp.tool()
async def create_portfolio(name: str) -> str:
    """Create a new, empty portfolio with the given name."""
    return await _request("POST", "/portfolios", params={"name": name})


@mcp.tool()
async def add_holding(
    portfolio_id: str, ticker: str, shares: float, cost_basis_per_share: float
) -> str:
    """Add or update a position in a portfolio. Calling this again for a
    ticker already in the portfolio REPLACES the position (shares and cost
    basis), it does not add to it — this represents current holdings, not
    a transaction log."""
    return await _request(
        "POST",
        f"/portfolios/{portfolio_id}/holdings/{ticker}",
        params={"shares": shares, "cost_basis_per_share": cost_basis_per_share},
    )


@mcp.tool()
async def remove_holding(portfolio_id: str, ticker: str) -> str:
    """Remove a holding from a portfolio entirely."""
    return await _request("DELETE", f"/portfolios/{portfolio_id}/holdings/{ticker}")


@mcp.tool()
async def get_portfolio_valuation(portfolio_id: str) -> str:
    """Get live market valuation for a portfolio — current price, market
    value, and unrealized gain/loss for every position, plus totals."""
    return await _request("GET", f"/portfolios/{portfolio_id}/valuation")


@mcp.tool()
async def get_portfolio_risk(portfolio_id: str) -> str:
    """Get risk metrics for a portfolio — concentration (Herfindahl index),
    largest position weight, sector exposure, and weighted-average leverage."""
    return await _request("GET", f"/portfolios/{portfolio_id}/risk")


# --- Company data ------------------------------------------------------------

@mcp.tool()
async def ingest_company(ticker: str, years: int = 5) -> str:
    """Ingest a company's profile and financial statements from Financial
    Modeling Prep. Required before a ticker can be watchlisted, added to a
    portfolio, or have research/analysis/valuation run on it. Safe to call
    even if the ticker is already ingested (re-ingests fresh data)."""
    return await _request("POST", f"/companies/{ticker}/ingest", params={"years": years})


@mcp.tool()
async def get_company_financials(ticker: str, years: int = 5) -> str:
    """Get a company's raw ingested financial statements (income statement,
    balance sheet, cash flow) for the given number of most recent years."""
    return await _request("GET", f"/companies/{ticker}", params={"years": years})


@mcp.tool()
async def get_company_analysis(ticker: str, years: int = 5) -> str:
    """Get deterministic financial ratios and trends for a company — margins,
    growth rates, ROE/ROA, leverage — computed from ingested statements. No
    cost, no LLM call."""
    return await _request("GET", f"/companies/{ticker}/analysis", params={"years": years})


@mcp.tool()
async def get_company_valuation(ticker: str) -> str:
    """Get live valuation multiples for a company (P/E, P/S, P/B, P/FCF,
    EV/EBITDA) against its current market price. No cost, no LLM call."""
    return await _request("GET", f"/companies/{ticker}/valuation")


@mcp.tool()
async def get_company_research(ticker: str) -> str:
    """Get the most recently generated AI research report for a company, if
    one exists. Free — does not generate a new report. Returns a 404-style
    message if no report has been generated yet; use generate_company_research
    for that."""
    return await _request("GET", f"/companies/{ticker}/research")


@mcp.tool()
async def generate_company_research(ticker: str) -> str:
    """Generate a NEW AI research report for a company, grounded in its
    ingested financial data. This makes a real LLM call and has a real
    cost — prefer get_company_research first to check if a recent report
    already exists."""
    return await _request("POST", f"/companies/{ticker}/research")


# --- Alerts and daily brief --------------------------------------------------

@mcp.tool()
async def get_alerts(unread_only: bool = False) -> str:
    """Get the user's price-move alerts from continuous monitoring."""
    return await _request("GET", "/alerts", params={"unread_only": unread_only})


@mcp.tool()
async def get_daily_brief() -> str:
    """Generate a short AI narrative summarizing watchlist price moves,
    portfolio performance, and unread alerts. This makes a real LLM call and
    has a real cost — don't call it more than once per conversation unless
    the user explicitly asks for a refresh."""
    return await _request("GET", "/brief")


@mcp.tool()
async def delete_portfolio(portfolio_id: str) -> str:
    """Permanently delete a portfolio and all its holdings. This cannot
    be undone — confirm with the user before calling this."""
    return await _request("DELETE", f"/portfolios/{portfolio_id}")


@mcp.tool()
async def mark_alert_read(alert_id: int) -> str:
    """Mark one alert as read."""
    return await _request("POST", f"/alerts/{alert_id}/read")


@mcp.tool()
async def run_monitoring_check() -> str:
    """Run a monitoring check right now (price moves, entry targets,
    upcoming earnings) instead of waiting for the next scheduled cron
    run. Returns any new alerts generated."""
    return await _request("POST", "/alerts/check")


# --- Watchlist extras: named lists, triage, news, earnings ------------------

@mcp.tool()
async def triage_watchlist(list_name: str = "") -> str:
    """Rank watchlist items by attention-worthiness using live data: day
    move, move since added, P/E drift vs. add-time baseline, and whether
    an entry target was crossed. HIGHER score means MORE attention-
    worthy, NOT better quality — a stock can rank first because it's
    collapsing. Optionally scope to one named list."""
    params = {"list_name": list_name} if list_name else None
    return await _request("GET", "/watchlist/triage", params=params)


@mcp.tool()
async def get_watchlist_news(list_name: str = "", limit_per_ticker: int = 5) -> str:
    """Get recent news headlines for every ticker on the watchlist (or
    one named list). Real, sourced, dated headlines — never invent one
    beyond what's returned."""
    params: dict[str, Any] = {"limit_per_ticker": limit_per_ticker}
    if list_name:
        params["list_name"] = list_name
    return await _request("GET", "/watchlist/news", params=params)


@mcp.tool()
async def get_upcoming_earnings(list_name: str = "", lookahead_days: int = 14) -> str:
    """Get upcoming earnings announcements for the watchlist (or one
    named list) within the given number of days. Real dates and analyst
    EPS estimates from the data provider — never invent one."""
    params: dict[str, Any] = {"lookahead_days": lookahead_days}
    if list_name:
        params["list_name"] = list_name
    return await _request("GET", "/watchlist/earnings", params=params)


# --- Factor scoring ------------------------------------------------------------

@mcp.tool()
async def get_factor_score(ticker: str) -> str:
    """Cross-sectional factor score for one ticker: Value, Quality,
    Growth, Momentum, Size, each standardized (z-scored) against the
    rest of the S&P 500 at the same point in time. DIFFERENT from a
    fixed-band screen — a positive z-score always means "more
    attractive than the universe average," never an absolute judgment.
    A null value means that factor's data was unavailable, not that it
    scored exactly average."""
    return await _request("GET", f"/companies/{ticker}/factor-score")


@mcp.tool()
async def rank_universe_by_factors(top_n: int = 10) -> str:
    """Rank the S&P 500 universe by composite factor score (equal-
    weighted across Value/Quality/Growth/Momentum/Size). Use for "what
    are the best value/growth/momentum names right now" — a live
    cross-sectional ranking, not a fixed screen."""
    return await _request("GET", "/companies/factor-rankings", params={"top_n": top_n})


# --- Curated investment universe (global themes) ------------------------------

@mcp.tool()
async def create_universe_theme(name: str, description: str = "") -> str:
    """Create a new global curated theme (e.g. "AI Infrastructure",
    "China") that companies can be tagged into. Themes are shared
    across every user — a system-wide taxonomy, not a personal list."""
    params = {"description": description} if description else None
    return await _request("POST", f"/universe/themes/{name}", params=params)


@mcp.tool()
async def list_universe_themes() -> str:
    """List every curated theme with its member count."""
    return await _request("GET", "/universe/themes")


@mcp.tool()
async def get_theme_tickers(theme_name: str) -> str:
    """Get every ticker tagged into a given theme."""
    return await _request("GET", f"/universe/themes/{theme_name}/tickers")


@mcp.tool()
async def add_ticker_to_theme(theme_name: str, ticker: str) -> str:
    """Tag a ticker into a theme. A ticker can belong to multiple themes
    at once. The ticker must already be ingested; the theme must
    already exist."""
    return await _request("POST", f"/universe/themes/{theme_name}/tickers/{ticker}")


@mcp.tool()
async def remove_ticker_from_theme(theme_name: str, ticker: str) -> str:
    """Untag a ticker from one theme (does not affect its other
    themes)."""
    return await _request("DELETE", f"/universe/themes/{theme_name}/tickers/{ticker}")


@mcp.tool()
async def generate_theme_synthesis(theme_name: str) -> str:
    """Generate an AI-written narrative synthesis across an ENTIRE
    theme — common threads, notable divergences, and risks visible
    across the group as a whole. Grounded in real screening/factor
    data. Makes a real LLM call and has a real cost; not persisted, so
    it regenerates fresh each time."""
    return await _request("POST", f"/universe/themes/{theme_name}/synthesis")


@mcp.tool()
async def suggest_theme(user_hint: str = "") -> str:
    """Propose a NEW investment theme, grounded in real recent general
    market news. Optionally take a topic hint (e.g. "reshoring") or
    infer purely from what's currently in the news. This is a
    SUGGESTION for review — it never creates the theme or tags any
    ticker itself. Some candidate tickers may not be ingested yet
    (already_ingested: false) — those need ingest_company or ingest_etf
    first, which will also fail cleanly if a ticker turns out not to
    be real. Makes a real LLM call and has a real cost."""
    params = {"user_hint": user_hint} if user_hint else None
    return await _request("POST", "/universe/suggest-theme", params=params)


# --- Risk-parity portfolio construction ---------------------------------------

@mcp.tool()
async def construct_risk_parity_portfolio(tickers: list[str], total_investment: float) -> str:
    """Propose a FROM-SCRATCH dollar allocation across a list of
    tickers using risk parity: lower-volatility tickers get more
    capital, higher-volatility tickers get less. NOT a return forecast
    and NOT a recommendation of which tickers to buy — only how to
    size positions across ones already chosen."""
    return await _request(
        "POST", "/portfolios/construct-risk-parity",
        json={"tickers": [t.upper() for t in tickers], "total_investment": total_investment},
    )


# --- ETF support ---------------------------------------------------------------

@mcp.tool()
async def get_sp500_constituents() -> str:
    """Live, authoritative current S&P 500 membership from the data
    provider — not a static list, reflects index rebalances
    automatically."""
    return await _request("GET", "/companies/sp500-constituents")


@mcp.tool()
async def ingest_etf(ticker: str) -> str:
    """Ingest an ETF's profile (name, expense ratio, AUM) — separate
    from ingest_company, since a fund has no income statement. Once
    ingested, an ETF can be watchlisted, tagged into a theme, and
    factor-scored (Momentum and Size only — Value/Quality/Growth will
    always be null for a fund, honestly, not a data gap)."""
    return await _request("POST", f"/companies/{ticker}/ingest-etf")


def main() -> None:
    """Real entry point — this is where FININSIGHT_API_KEY actually
    needs to exist, not at import time. Running this file directly
    (the normal way Claude Desktop launches it) still gets the exact
    same early, clear error it always did if the key is missing."""
    if not API_KEY:
        raise RuntimeError(
            "FININSIGHT_API_KEY environment variable is required. "
            "Create one via: curl -X POST "
            f"'{API_BASE_URL}/auth/signup' -H 'Content-Type: application/json' "
            "-d '{\"email\": \"you@example.com\", \"password\": \"yourpassword\"}'"
        )
    mcp.run()


if __name__ == "__main__":
    main()
