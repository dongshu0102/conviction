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
    2. Get an API key: POST to {API_URL}/api-keys?user_id=...&name=...
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

if not API_KEY:
    raise RuntimeError(
        "FININSIGHT_API_KEY environment variable is required. "
        "Create one via: curl -X POST "
        f"'{API_BASE_URL}/api-keys?user_id=YOUR_NAME&name=mcp-client'"
    )

mcp = MCPServer(
    name="fininsight",
    description="AI financial intelligence platform — watchlists, portfolios, "
    "company research, valuation, and risk analysis grounded in real S&P 500 data.",
)


async def _request(method: str, path: str, params: dict[str, Any] | None = None) -> str:
    """Shared HTTP call + error handling for every tool below. Returns a
    string either way (JSON on success, a plain-English error message on
    failure) since MCP tool results are text — never raises, so a failed
    call becomes information the model can react to, not a crash.
    """
    async with httpx.AsyncClient(
        base_url=API_BASE_URL, headers={"X-Api-Key": API_KEY}, timeout=60.0
    ) as client:
        try:
            response = await client.request(method, path, params=params)
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


if __name__ == "__main__":
    mcp.run()
