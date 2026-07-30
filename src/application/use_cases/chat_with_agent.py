"""Use case: chat with an AI agent that can act on the user's own data.

Deliberately composes EXISTING use cases rather than introducing new
business logic — every tool here is a thin wrapper around a use case
that's already built, tested, and used elsewhere (the REST API, the MCP
server). Adding a chat tool should never mean writing new domain logic,
only exposing what already exists to the model.

Ownership enforcement: portfolio-scoped tools re-check that the
authenticated user owns the referenced portfolio_id, exactly matching
the REST API's _verify_ownership check in portfolios.py. A message could
in principle ask the model to look up any portfolio_id; without this
check here, that would bypass the same security boundary the API
enforces. 404-style errors are returned to the model (not raised) so it
can react gracefully rather than crashing the conversation.
"""
from __future__ import annotations

import logging
from dataclasses import asdict

from src.application.interfaces.chat_agent import ChatAgent, ChatMessage, ToolDefinition
from src.application.use_cases.compute_financial_analysis import (
    ComputeFinancialAnalysisUseCase,
)
from src.application.use_cases.compute_portfolio_risk import ComputePortfolioRiskUseCase
from src.application.use_cases.compute_portfolio_valuation import (
    ComputePortfolioValuationUseCase,
)
from src.application.use_cases.compute_valuation import ComputeValuationUseCase
from src.application.use_cases.get_company_financials import CompanyNotFoundError
from src.application.use_cases.manage_portfolio import (
    AddHoldingUseCase,
    GetPortfolioUseCase,
    ListPortfoliosUseCase,
    PortfolioNotFoundError,
    TickerNotIngestedError,
)
from src.application.use_cases.manage_watchlist import (
    AddToWatchlistUseCase,
    GetWatchlistUseCase,
)
from src.application.use_cases.screen_stocks import ScreenStocksUseCase
from src.application.use_cases.suggest_rebalancing import SuggestRebalancingUseCase
from src.domain.repositories.research_report_repository import ResearchReportRepository

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are FinInsight's assistant, embedded in the user's own \
financial dashboard. You can read and act on THEIR watchlist and portfolios \
using the tools provided — always use a tool rather than guessing or recalling \
from general knowledge. Never state a number you didn't get from a tool result. \
If a tool call fails or a portfolio isn't found, say so plainly rather than \
making up data. Keep replies concise — this is a chat sidebar, not a report.

If asked about rebalancing, diversification, or whether a portfolio is too \
concentrated, use suggest_rebalancing rather than reasoning about position \
sizes yourself — it computes exact share counts, which you should not \
estimate. It only flags single-position over-concentration, not sector-level \
exposure; mention that scope limit if the user's question is really about \
sector diversification."""

_TOOLS = [
    ToolDefinition("get_watchlist", "Get the user's watchlist.", {"type": "object", "properties": {}}),
    ToolDefinition(
        "add_to_watchlist",
        "Add a ticker to the user's watchlist. The ticker must already be ingested.",
        {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]},
    ),
    ToolDefinition(
        "list_portfolios", "List the user's portfolios (name and id, no holdings detail).",
        {"type": "object", "properties": {}},
    ),
    ToolDefinition(
        "get_portfolio_valuation",
        "Get live market valuation for one of the user's portfolios, by its id "
        "(use list_portfolios first if you only know the name).",
        {
            "type": "object",
            "properties": {"portfolio_id": {"type": "string"}},
            "required": ["portfolio_id"],
        },
    ),
    ToolDefinition(
        "get_portfolio_risk",
        "Get risk metrics (concentration, sector exposure, leverage) for one of the user's portfolios.",
        {
            "type": "object",
            "properties": {"portfolio_id": {"type": "string"}},
            "required": ["portfolio_id"],
        },
    ),
    ToolDefinition(
        "add_holding",
        "Add or replace a position in one of the user's portfolios.",
        {
            "type": "object",
            "properties": {
                "portfolio_id": {"type": "string"},
                "ticker": {"type": "string"},
                "shares": {"type": "number"},
                "cost_basis_per_share": {"type": "number"},
            },
            "required": ["portfolio_id", "ticker", "shares", "cost_basis_per_share"],
        },
    ),
    ToolDefinition(
        "get_company_analysis",
        "Get deterministic financial ratios/trends (margins, growth, leverage) for any company.",
        {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]},
    ),
    ToolDefinition(
        "get_company_valuation",
        "Get live valuation multiples (P/E, P/S, EV/EBITDA, etc.) for any company.",
        {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]},
    ),
    ToolDefinition(
        "get_company_research",
        "Get the most recent AI research report for a company, if one exists. Free, does not generate a new one.",
        {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]},
    ),
    ToolDefinition(
        "suggest_rebalancing",
        "Suggest exact share counts to trim from over-concentrated positions in one "
        "of the user's portfolios. Deterministic — the model must not compute these "
        "numbers itself. Only flags single positions above the target weight "
        "(default 30% of the portfolio), not sector-level concentration.",
        {
            "type": "object",
            "properties": {
                "portfolio_id": {"type": "string"},
                "target_max_weight": {
                    "type": "number",
                    "description": "Optional. Defaults to 0.30 (no position above 30%).",
                },
            },
            "required": ["portfolio_id"],
        },
    ),
    ToolDefinition(
        "screen_stocks",
        "Rank a SPECIFIC, bounded list of tickers (you must name them — this "
        "does not scan the whole market) by value (cheapness: P/E, P/S, "
        "EV/EBITDA) and quality (ROE, margins, leverage). Returns value_score, "
        "quality_score, and composite_score for each — LOWER IS ALWAYS BETTER "
        "on these scores (rank 1 = best in the group). Use this to compare "
        "or rank a handful of candidates the user named or you're proposing "
        "— e.g. after suggesting a few tickers for a sector. Keep the list "
        "short (under ~15 tickers) — each one requires a live data lookup.",
        {
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "The specific tickers to screen, e.g. ['JNJ', 'PFE', 'JPM'].",
                },
            },
            "required": ["tickers"],
        },
    ),
]


class ChatWithAgentUseCase:
    def __init__(
        self,
        chat_agent: ChatAgent,
        get_watchlist: GetWatchlistUseCase,
        add_to_watchlist: AddToWatchlistUseCase,
        list_portfolios: ListPortfoliosUseCase,
        get_portfolio: GetPortfolioUseCase,
        compute_valuation: ComputePortfolioValuationUseCase,
        compute_risk: ComputePortfolioRiskUseCase,
        add_holding: AddHoldingUseCase,
        compute_analysis: ComputeFinancialAnalysisUseCase,
        compute_company_valuation: ComputeValuationUseCase,
        research_repo: ResearchReportRepository,
        suggest_rebalancing: SuggestRebalancingUseCase,
        screen_stocks: ScreenStocksUseCase,
    ) -> None:
        self._chat_agent = chat_agent
        self._get_watchlist = get_watchlist
        self._add_to_watchlist = add_to_watchlist
        self._list_portfolios = list_portfolios
        self._get_portfolio = get_portfolio
        self._compute_valuation = compute_valuation
        self._compute_risk = compute_risk
        self._add_holding = add_holding
        self._compute_analysis = compute_analysis
        self._compute_company_valuation = compute_company_valuation
        self._research_repo = research_repo
        self._suggest_rebalancing = suggest_rebalancing
        self._screen_stocks = screen_stocks
        self._user_id: str = ""  # set per-request in execute()

    def execute(self, user_id: str, message: str, history: list[ChatMessage]) -> str:
        self._user_id = user_id
        messages = [*history, ChatMessage(role="user", content=message)]
        result = self._chat_agent.run(_SYSTEM_PROMPT, messages, _TOOLS, self._dispatch)
        return result.reply

    def execute_streaming(self, user_id: str, message: str, history: list[ChatMessage]):
        """Same as execute(), but yields text chunks as they're generated
        instead of returning the whole reply at once. Reuses the exact
        same _dispatch method — tool logic is identical either way, only
        the LLM call shape differs."""
        self._user_id = user_id
        messages = [*history, ChatMessage(role="user", content=message)]
        yield from self._chat_agent.stream(_SYSTEM_PROMPT, messages, _TOOLS, self._dispatch)

    def _own_portfolio_or_error(self, portfolio_id: str) -> dict | None:
        """Returns an error dict if the portfolio doesn't exist or isn't
        owned by the current user; None if the check passes."""
        try:
            portfolio = self._get_portfolio.execute(portfolio_id)
        except PortfolioNotFoundError:
            return {"error": f"No portfolio found with id '{portfolio_id}'"}
        if portfolio.user_id != self._user_id:
            return {"error": f"No portfolio found with id '{portfolio_id}'"}
        return None

    def _dispatch(self, tool_name: str, tool_input: dict):
        if tool_name == "get_watchlist":
            items = self._get_watchlist.execute(self._user_id)
            return {"tickers": [{"ticker": i.ticker, "notes": i.notes} for i in items]}

        if tool_name == "add_to_watchlist":
            try:
                item = self._add_to_watchlist.execute(self._user_id, tool_input["ticker"])
                return {"ticker": item.ticker, "status": "added"}
            except Exception as exc:
                return {"error": str(exc)}

        if tool_name == "list_portfolios":
            portfolios = self._list_portfolios.execute(self._user_id)
            return {
                "portfolios": [
                    {"portfolio_id": p.portfolio_id, "name": p.name} for p in portfolios
                ]
            }

        if tool_name == "get_portfolio_valuation":
            err = self._own_portfolio_or_error(tool_input["portfolio_id"])
            if err:
                return err
            v = self._compute_valuation.execute(tool_input["portfolio_id"])
            return {
                "name": v.name,
                "total_market_value": v.total_market_value,
                "total_unrealized_gain_pct": v.total_unrealized_gain_pct,
                "positions": [
                    {"ticker": p.ticker, "market_value": p.market_value, "weight": p.weight}
                    for p in v.positions
                ],
            }

        if tool_name == "get_portfolio_risk":
            err = self._own_portfolio_or_error(tool_input["portfolio_id"])
            if err:
                return err
            r = self._compute_risk.execute(tool_input["portfolio_id"])
            return {
                "largest_position_weight": r.largest_position_weight,
                "herfindahl_index": r.herfindahl_index,
                "sector_exposures": [
                    {"sector": s.sector, "weight": s.weight} for s in r.sector_exposures
                ],
                "weighted_avg_debt_to_equity": r.weighted_avg_debt_to_equity,
            }

        if tool_name == "add_holding":
            err = self._own_portfolio_or_error(tool_input["portfolio_id"])
            if err:
                return err
            try:
                h = self._add_holding.execute(
                    tool_input["portfolio_id"],
                    tool_input["ticker"],
                    tool_input["shares"],
                    tool_input["cost_basis_per_share"],
                )
                return {"ticker": h.ticker, "shares": h.shares, "status": "added"}
            except TickerNotIngestedError as exc:
                return {"error": str(exc)}

        if tool_name == "get_company_analysis":
            try:
                a = self._compute_analysis.execute(tool_input["ticker"], years=3)
            except CompanyNotFoundError as exc:
                return {"error": str(exc)}
            return {"ticker": a.ticker, "yearly_ratios": [asdict(r) for r in a.yearly_ratios]}

        if tool_name == "get_company_valuation":
            try:
                v = self._compute_company_valuation.execute(tool_input["ticker"])
            except CompanyNotFoundError as exc:
                return {"error": str(exc)}
            return {
                "price": v.price,
                "price_to_earnings": v.price_to_earnings,
                "price_to_sales": v.price_to_sales,
                "ev_to_ebitda": v.ev_to_ebitda,
            }

        if tool_name == "get_company_research":
            report = self._research_repo.get_latest(tool_input["ticker"])
            if report is None:
                return {"error": "No research report exists yet for this ticker."}
            return {
                "business_overview": report.business_overview,
                "financial_highlights": report.financial_highlights,
                "key_risks": report.key_risks,
            }

        if tool_name == "suggest_rebalancing":
            err = self._own_portfolio_or_error(tool_input["portfolio_id"])
            if err:
                return err
            target = tool_input.get("target_max_weight", 0.30)
            plan = self._suggest_rebalancing.execute(tool_input["portfolio_id"], target)
            if not plan.suggestions:
                return {
                    "target_max_weight": plan.target_max_weight,
                    "suggestions": [],
                    "note": "No position exceeds the target weight — nothing to suggest.",
                }
            return {
                "target_max_weight": plan.target_max_weight,
                "suggestions": [
                    {
                        "ticker": s.ticker,
                        "current_weight": s.current_weight,
                        "target_weight": s.target_weight,
                        "shares_to_trim": s.shares_to_trim,
                        "estimated_proceeds": s.estimated_proceeds,
                    }
                    for s in plan.suggestions
                ],
            }

        if tool_name == "screen_stocks":
            tickers = tool_input.get("tickers", [])[:15]  # hard cap regardless of what's asked
            if not tickers:
                return {"error": "No tickers provided to screen."}
            result = self._screen_stocks.execute(tickers)
            return {
                "scoring_note": (
                    "LOWER score is ALWAYS better/more attractive for value_score, "
                    "quality_score, and composite_score. A score of 1 means this "
                    "ticker ranked BEST (cheapest for value, highest-quality for "
                    "quality) among the group screened; a higher score means it "
                    "ranked worse. Do not describe a high score as 'best' or 'top' — "
                    "sort ascending by these scores when presenting a ranking."
                ),
                "excluded": result.excluded,
                "results": [
                    {
                        "ticker": s.ticker,
                        "price": s.price,
                        "price_to_earnings": s.price_to_earnings,
                        "price_to_sales": s.price_to_sales,
                        "ev_to_ebitda": s.ev_to_ebitda,
                        "return_on_equity": s.return_on_equity,
                        "net_margin": s.net_margin,
                        "debt_to_equity": s.debt_to_equity,
                        "value_score": s.value_score,
                        "quality_score": s.quality_score,
                        "composite_score": s.composite_score,
                    }
                    for s in result.results
                ],
            }

        return {"error": f"Unknown tool: {tool_name}"}
