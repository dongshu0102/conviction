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
from datetime import date

from src.application.interfaces.chat_agent import ChatAgent, ChatMessage, ToolDefinition
from src.application.interfaces.options_data_provider import (
    OptionsDataProvider,
    OptionsDataProviderError,
)
from src.application.use_cases.compute_financial_analysis import (
    ComputeFinancialAnalysisUseCase,
)
from src.application.use_cases.compute_option_portfolio_valuation import (
    ComputeOptionPortfolioValuationUseCase,
)
from src.application.use_cases.compute_portfolio_greeks import ComputePortfolioGreeksUseCase
from src.application.use_cases.compute_portfolio_risk import ComputePortfolioRiskUseCase
from src.application.use_cases.compute_portfolio_valuation import (
    ComputePortfolioValuationUseCase,
)
from src.application.use_cases.compute_valuation import ComputeValuationUseCase
from src.application.use_cases.get_company_financials import CompanyNotFoundError
from src.application.use_cases.manage_option_holdings import (
    AddOptionHoldingUseCase,
    InvalidOptionTypeError,
    RemoveOptionHoldingUseCase,
)
from src.application.use_cases.manage_portfolio import (
    AddHoldingUseCase,
    CreatePortfolioUseCase,
    DeletePortfolioUseCase,
    GetPortfolioUseCase,
    ListPortfoliosUseCase,
    PortfolioNotFoundError,
    TickerNotIngestedError,
)
from src.application.use_cases.manage_watchlist import (
    AddToWatchlistUseCase,
    GetWatchlistUseCase,
    ListWatchlistNamesUseCase,
    RemoveFromWatchlistUseCase,
    UpdateWatchlistItemUseCase,
)
from src.application.use_cases.triage_watchlist import TriageWatchlistUseCase
from src.application.use_cases.recommend_stocks import RecommendStocksUseCase
from src.application.use_cases.screen_stocks import ScreenStocksUseCase
from src.application.use_cases.suggest_hedging import SuggestHedgingUseCase
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
sector diversification.

delete_portfolio is permanent and cannot be undone. Never call it unless the \
user has clearly confirmed which specific portfolio to delete — if there's \
any ambiguity about which one they mean, ask first rather than guessing.

suggest_hedging describes what a delta-neutral trade would mechanically \
require, not a recommendation. Present the numbers as a fact about their \
current exposure, and let them decide whether hedging fits their goals — \
avoid phrasing like "you should hedge" or "I recommend."

Watchlists support multiple named lists (default list is "Default"), \
per-ticker entry targets (alert when price falls to or below the target), \
custom alert thresholds, and a thesis in notes. triage_watchlist ranks \
items by how much ATTENTION they deserve — a high score is NOT a buy \
signal or quality rank; a stock can rank first because it is collapsing. \
Present triage results as "what changed / what to look at," never as \
recommendations. If an item has a thesis in notes and its P/E has drifted \
far from the add-time baseline, point out that the original thesis may \
deserve a re-check — as an observation, not advice."""

_TOOLS = [
    ToolDefinition(
        "get_watchlist",
        "Get the user's watchlist items across all named lists, or one list if "
        "list_name is given. Includes per-item entry targets, alert thresholds, "
        "thesis notes, and add-time price/PE baselines.",
        {"type": "object", "properties": {"list_name": {"type": "string"}}},
    ),
    ToolDefinition(
        "add_to_watchlist",
        "Add a ticker to a named watchlist (default list is 'Default'). The ticker "
        "must already be ingested. Optionally set an entry target_price (alerts when "
        "price falls to or below it), a custom alert_threshold_pct as a fraction "
        "(0.03 = 3% move alerts), and notes (the user's investment thesis). The "
        "current price and P/E are captured automatically as baselines.",
        {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "list_name": {"type": "string"},
                "target_price": {"type": "number"},
                "alert_threshold_pct": {"type": "number"},
                "notes": {"type": "string"},
            },
            "required": ["ticker"],
        },
    ),
    ToolDefinition(
        "remove_from_watchlist",
        "Remove a ticker from one named list (if list_name given) or from ALL of "
        "the user's lists (if omitted).",
        {
            "type": "object",
            "properties": {"ticker": {"type": "string"}, "list_name": {"type": "string"}},
            "required": ["ticker"],
        },
    ),
    ToolDefinition(
        "update_watchlist_item",
        "Update an existing watchlist item's target_price, alert_threshold_pct, or "
        "notes without touching its add-time baselines. Only the fields provided "
        "are changed. list_name defaults to 'Default'.",
        {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "list_name": {"type": "string"},
                "target_price": {"type": "number"},
                "alert_threshold_pct": {"type": "number"},
                "notes": {"type": "string"},
            },
            "required": ["ticker"],
        },
    ),
    ToolDefinition(
        "list_watchlists",
        "List the user's named watchlists with item counts.",
        {"type": "object", "properties": {}},
    ),
    ToolDefinition(
        "triage_watchlist",
        "Rank watchlist items by attention-worthiness using live data: day move "
        "since last monitoring check, move since the item was added, P/E drift vs "
        "the add-time baseline, and whether the entry target was crossed. "
        "Optionally scope to one list_name.",
        {"type": "object", "properties": {"list_name": {"type": "string"}}},
    ),
    ToolDefinition(
        "list_portfolios", "List the user's portfolios (name and id, no holdings detail).",
        {"type": "object", "properties": {}},
    ),
    ToolDefinition(
        "create_portfolio",
        "Create a new, empty portfolio with the given name. Use add_holding "
        "afterward to actually put positions in it.",
        {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
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
        "delete_portfolio",
        "PERMANENTLY delete one of the user's portfolios, including all its "
        "holdings. This cannot be undone. Only call this after the user has "
        "clearly confirmed they want to delete a SPECIFIC portfolio (use "
        "list_portfolios first if you only know a name, not an id) — never "
        "call this speculatively or without explicit confirmation.",
        {
            "type": "object",
            "properties": {"portfolio_id": {"type": "string"}},
            "required": ["portfolio_id"],
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
    ToolDefinition(
        "recommend_stocks",
        "Find and rank stock candidates to fill REAL gaps in one of the "
        "user's portfolios — sectors they have little or no exposure to, "
        "based on actual computed sector exposure, not a guess. Unlike "
        "screen_stocks, you do NOT name the tickers here — this tool finds "
        "them itself from the real ingested company universe. Use this when "
        "asked for recommendations, diversification ideas, or 'what should "
        "I add' without the user naming specific candidates.",
        {
            "type": "object",
            "properties": {
                "portfolio_id": {"type": "string"},
                "max_recommendations": {
                    "type": "integer",
                    "description": "Optional. Defaults to 5.",
                },
            },
            "required": ["portfolio_id"],
        },
    ),
    ToolDefinition(
        "add_option_holding",
        "Add or replace an option position in one of the user's portfolios. "
        "contracts_held can be negative for a short position. 1 contract "
        "= 100 shares of the underlying, standard convention.",
        {
            "type": "object",
            "properties": {
                "portfolio_id": {"type": "string"},
                "underlying_ticker": {"type": "string"},
                "strike": {"type": "number"},
                "expiration": {"type": "string", "description": "ISO date, e.g. '2026-12-18'."},
                "option_type": {"type": "string", "description": "'call' or 'put'."},
                "contracts_held": {
                    "type": "integer",
                    "description": "Positive = long, negative = short.",
                },
                "cost_basis_per_contract": {"type": "number"},
            },
            "required": [
                "portfolio_id", "underlying_ticker", "strike", "expiration",
                "option_type", "contracts_held", "cost_basis_per_contract",
            ],
        },
    ),
    ToolDefinition(
        "remove_option_holding",
        "Remove an option position from one of the user's portfolios, "
        "identified by the full contract (underlying, strike, expiration, type).",
        {
            "type": "object",
            "properties": {
                "portfolio_id": {"type": "string"},
                "underlying_ticker": {"type": "string"},
                "strike": {"type": "number"},
                "expiration": {"type": "string", "description": "ISO date, e.g. '2026-12-18'."},
                "option_type": {"type": "string", "description": "'call' or 'put'."},
            },
            "required": ["portfolio_id", "underlying_ticker", "strike", "expiration", "option_type"],
        },
    ),
    ToolDefinition(
        "compute_portfolio_greeks",
        "Get the portfolio-level aggregated Greeks (delta, gamma, theta, "
        "vega) across all of a portfolio's option holdings, using LIVE "
        "quotes. Deterministic — do not estimate Greeks yourself. If a "
        "position has no live quote available, it's excluded from the "
        "total and listed separately — mention this to the user rather "
        "than presenting the total as if it covered everything.",
        {
            "type": "object",
            "properties": {"portfolio_id": {"type": "string"}},
            "required": ["portfolio_id"],
        },
    ),
    ToolDefinition(
        "compute_option_portfolio_valuation",
        "Get the current market value and unrealized P&L for a "
        "portfolio's option holdings, using LIVE quotes. Deterministic — "
        "do not estimate values yourself. Positions with no live quote "
        "available are excluded and listed separately, same as "
        "compute_portfolio_greeks. This is for OPTION positions only — "
        "use get_portfolio_valuation for stock positions.",
        {
            "type": "object",
            "properties": {"portfolio_id": {"type": "string"}},
            "required": ["portfolio_id"],
        },
    ),
    ToolDefinition(
        "suggest_hedging",
        "Suggest a MECHANICAL delta hedge, per underlying: the exact "
        "share count to buy/sell in the underlying itself to bring net "
        "delta exposure (combined stock holdings + option holdings on "
        "that ticker) to zero. Deterministic exact arithmetic, not an "
        "estimate. This describes what a delta-neutral position would "
        "require — present it as that mechanical fact, not as "
        "investment advice or a recommendation to actually make the "
        "trade; the user decides whether hedging fits their goals.",
        {
            "type": "object",
            "properties": {"portfolio_id": {"type": "string"}},
            "required": ["portfolio_id"],
        },
    ),
]


class ChatWithAgentUseCase:
    def __init__(
        self,
        chat_agent: ChatAgent,
        get_watchlist: GetWatchlistUseCase,
        add_to_watchlist: AddToWatchlistUseCase,
        remove_from_watchlist: RemoveFromWatchlistUseCase,
        list_portfolios: ListPortfoliosUseCase,
        create_portfolio: CreatePortfolioUseCase,
        get_portfolio: GetPortfolioUseCase,
        compute_valuation: ComputePortfolioValuationUseCase,
        compute_risk: ComputePortfolioRiskUseCase,
        add_holding: AddHoldingUseCase,
        delete_portfolio: DeletePortfolioUseCase,
        compute_analysis: ComputeFinancialAnalysisUseCase,
        compute_company_valuation: ComputeValuationUseCase,
        research_repo: ResearchReportRepository,
        suggest_rebalancing: SuggestRebalancingUseCase,
        screen_stocks: ScreenStocksUseCase,
        recommend_stocks: RecommendStocksUseCase,
        add_option_holding: AddOptionHoldingUseCase,
        remove_option_holding: RemoveOptionHoldingUseCase,
        compute_portfolio_greeks: ComputePortfolioGreeksUseCase,
        compute_option_portfolio_valuation: ComputeOptionPortfolioValuationUseCase,
        suggest_hedging: SuggestHedgingUseCase,
        update_watchlist_item: UpdateWatchlistItemUseCase,
        list_watchlists: ListWatchlistNamesUseCase,
        triage_watchlist: TriageWatchlistUseCase,
    ) -> None:
        self._chat_agent = chat_agent
        self._get_watchlist = get_watchlist
        self._add_to_watchlist = add_to_watchlist
        self._remove_from_watchlist = remove_from_watchlist
        self._list_portfolios = list_portfolios
        self._create_portfolio = create_portfolio
        self._get_portfolio = get_portfolio
        self._compute_valuation = compute_valuation
        self._compute_risk = compute_risk
        self._add_holding = add_holding
        self._delete_portfolio = delete_portfolio
        self._compute_analysis = compute_analysis
        self._compute_company_valuation = compute_company_valuation
        self._research_repo = research_repo
        self._suggest_rebalancing = suggest_rebalancing
        self._screen_stocks = screen_stocks
        self._recommend_stocks = recommend_stocks
        self._add_option_holding = add_option_holding
        self._remove_option_holding = remove_option_holding
        self._compute_portfolio_greeks = compute_portfolio_greeks
        self._compute_option_portfolio_valuation = compute_option_portfolio_valuation
        self._suggest_hedging = suggest_hedging
        self._update_watchlist_item = update_watchlist_item
        self._list_watchlists = list_watchlists
        self._triage_watchlist = triage_watchlist
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
            items = self._get_watchlist.execute(self._user_id, tool_input.get("list_name"))
            return {
                "items": [
                    {
                        "ticker": i.ticker,
                        "list_name": i.list_name,
                        "notes": i.notes,
                        "target_price": i.target_price,
                        "alert_threshold_pct": i.alert_threshold_pct,
                        "added_price": i.added_price,
                        "added_pe": i.added_pe,
                    }
                    for i in items
                ]
            }

        if tool_name == "add_to_watchlist":
            try:
                item = self._add_to_watchlist.execute(
                    self._user_id,
                    tool_input["ticker"],
                    notes=tool_input.get("notes"),
                    list_name=tool_input.get("list_name", "Default"),
                    target_price=tool_input.get("target_price"),
                    alert_threshold_pct=tool_input.get("alert_threshold_pct"),
                )
                return {
                    "ticker": item.ticker,
                    "list_name": item.list_name,
                    "status": "added",
                    "added_price": item.added_price,
                    "added_pe": item.added_pe,
                    "baseline_note": (
                        "added_price/added_pe are the captured baselines; None means "
                        "the baseline could not be captured (this never blocks adding)."
                    ),
                }
            except Exception as exc:
                return {"error": str(exc)}

        if tool_name == "remove_from_watchlist":
            list_name = tool_input.get("list_name")
            removed = self._remove_from_watchlist.execute(
                self._user_id, tool_input["ticker"], list_name
            )
            if not removed:
                where = f"list '{list_name}'" if list_name else "any watchlist"
                return {"error": f"'{tool_input['ticker']}' was not on {where}."}
            return {"ticker": tool_input["ticker"], "status": "removed"}

        if tool_name == "update_watchlist_item":
            kwargs = {}
            if "notes" in tool_input:
                kwargs["notes"] = tool_input["notes"]
            if "target_price" in tool_input:
                kwargs["target_price"] = tool_input["target_price"]
            if "alert_threshold_pct" in tool_input:
                kwargs["alert_threshold_pct"] = tool_input["alert_threshold_pct"]
            try:
                item = self._update_watchlist_item.execute(
                    self._user_id,
                    tool_input["ticker"],
                    list_name=tool_input.get("list_name", "Default"),
                    **kwargs,
                )
                return {
                    "ticker": item.ticker,
                    "list_name": item.list_name,
                    "status": "updated",
                    "target_price": item.target_price,
                    "alert_threshold_pct": item.alert_threshold_pct,
                    "notes": item.notes,
                }
            except Exception as exc:
                return {"error": str(exc)}

        if tool_name == "list_watchlists":
            counts = self._list_watchlists.execute(self._user_id)
            return {"watchlists": [{"name": n, "item_count": c} for n, c in counts.items()]}

        if tool_name == "triage_watchlist":
            result = self._triage_watchlist.execute(
                self._user_id, tool_input.get("list_name")
            )

            def _pct(v):
                return round(v * 100, 2) if v is not None else None

            return {
                "scoring_note": (
                    "triage_score is an ATTENTION ranking — HIGHER means more "
                    "attention-worthy, NOT better quality or a buy signal; a stock "
                    "can rank first because it is collapsing. Signals that are null "
                    "mean the underlying data doesn't exist (no baseline or no "
                    "prior snapshot), not zero."
                ),
                "items": [
                    {
                        "ticker": t.ticker,
                        "list_name": t.list_name,
                        "triage_score": round(t.triage_score, 2),
                        "current_price": t.signals.current_price,
                        "day_move_percent": _pct(t.signals.day_move_pct),
                        "move_since_added_percent": _pct(t.signals.move_since_added_pct),
                        "pe_drift_percent": _pct(t.signals.pe_drift_pct),
                        "current_pe": t.signals.current_pe,
                        "target_crossed": t.signals.target_crossed,
                        "thesis_notes": t.notes,
                    }
                    for t in result.items
                ],
                "tickers_excluded_no_quote": result.tickers_excluded,
            }

        if tool_name == "list_portfolios":
            portfolios = self._list_portfolios.execute(self._user_id)
            return {
                "portfolios": [
                    {"portfolio_id": p.portfolio_id, "name": p.name} for p in portfolios
                ]
            }

        if tool_name == "create_portfolio":
            portfolio = self._create_portfolio.execute(self._user_id, tool_input["name"])
            return {"portfolio_id": portfolio.portfolio_id, "name": portfolio.name, "status": "created"}

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

        if tool_name == "delete_portfolio":
            err = self._own_portfolio_or_error(tool_input["portfolio_id"])
            if err:
                return err
            deleted = self._delete_portfolio.execute(tool_input["portfolio_id"])
            if not deleted:
                return {"error": "Portfolio was not found or already deleted."}
            return {"portfolio_id": tool_input["portfolio_id"], "status": "deleted"}

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

        if tool_name == "recommend_stocks":
            err = self._own_portfolio_or_error(tool_input["portfolio_id"])
            if err:
                return err
            max_recs = tool_input.get("max_recommendations", 5)
            result = self._recommend_stocks.execute(tool_input["portfolio_id"], max_recs)
            if not result.gap_sectors:
                return {
                    "gap_sectors": [],
                    "picks": [],
                    "note": "Portfolio already has meaningful exposure across all sectors — no gaps to fill.",
                }
            return {
                "gap_sectors": result.gap_sectors,
                "scoring_note": "Within picks, lower value_score/quality_score/composite_score is better.",
                "picks": [
                    {
                        "ticker": p.stock.ticker,
                        "gap_sector": p.gap_sector,
                        "current_sector_weight": p.current_sector_weight,
                        "price": p.stock.price,
                        "price_to_earnings": p.stock.price_to_earnings,
                        "return_on_equity": p.stock.return_on_equity,
                        "composite_score": p.stock.composite_score,
                    }
                    for p in result.picks
                ],
            }

        if tool_name == "add_option_holding":
            err = self._own_portfolio_or_error(tool_input["portfolio_id"])
            if err:
                return err
            try:
                expiration = date.fromisoformat(tool_input["expiration"])
            except ValueError:
                return {"error": f"'{tool_input['expiration']}' is not a valid ISO date (YYYY-MM-DD)."}
            try:
                holding = self._add_option_holding.execute(
                    tool_input["portfolio_id"],
                    tool_input["underlying_ticker"],
                    tool_input["strike"],
                    expiration,
                    tool_input["option_type"],
                    tool_input["contracts_held"],
                    tool_input["cost_basis_per_contract"],
                )
                return {
                    "underlying_ticker": holding.contract.underlying_ticker,
                    "strike": holding.contract.strike,
                    "expiration": holding.contract.expiration.isoformat(),
                    "option_type": holding.contract.option_type,
                    "contracts_held": holding.contracts_held,
                    "status": "added",
                }
            except InvalidOptionTypeError as exc:
                return {"error": str(exc)}

        if tool_name == "remove_option_holding":
            err = self._own_portfolio_or_error(tool_input["portfolio_id"])
            if err:
                return err
            try:
                expiration = date.fromisoformat(tool_input["expiration"])
            except ValueError:
                return {"error": f"'{tool_input['expiration']}' is not a valid ISO date (YYYY-MM-DD)."}
            try:
                removed = self._remove_option_holding.execute(
                    tool_input["portfolio_id"],
                    tool_input["underlying_ticker"],
                    tool_input["strike"],
                    expiration,
                    tool_input["option_type"],
                )
            except InvalidOptionTypeError as exc:
                return {"error": str(exc)}
            if not removed:
                return {"error": "No matching option position found to remove."}
            return {"status": "removed"}

        if tool_name == "compute_portfolio_greeks":
            err = self._own_portfolio_or_error(tool_input["portfolio_id"])
            if err:
                return err
            try:
                result = self._compute_portfolio_greeks.execute(tool_input["portfolio_id"])
            except OptionsDataProviderError as exc:
                return {"error": f"Couldn't fetch live options data: {exc}"}
            return {
                "total_delta": result.total_delta,
                "total_gamma": result.total_gamma,
                "total_theta": result.total_theta,
                "total_vega": result.total_vega,
                "positions_included": result.positions_included,
                "positions_excluded": result.positions_excluded,
            }

        if tool_name == "compute_option_portfolio_valuation":
            err = self._own_portfolio_or_error(tool_input["portfolio_id"])
            if err:
                return err
            try:
                result = self._compute_option_portfolio_valuation.execute(tool_input["portfolio_id"])
            except OptionsDataProviderError as exc:
                return {"error": f"Couldn't fetch live options data: {exc}"}
            return {
                "total_market_value": result.total_market_value,
                "total_cost_basis": result.total_cost_basis,
                "total_unrealized_gain": result.total_unrealized_gain,
                "total_unrealized_gain_pct": result.total_unrealized_gain_pct,
                "positions": [
                    {
                        "contract": p.contract.occ_symbol_fragment,
                        "contracts_held": p.contracts_held,
                        "current_price": p.current_price,
                        "market_value": p.market_value,
                        "unrealized_gain": p.unrealized_gain,
                        "unrealized_gain_pct": p.unrealized_gain_pct,
                    }
                    for p in result.positions
                ],
                "positions_excluded": result.positions_excluded,
            }

        if tool_name == "suggest_hedging":
            err = self._own_portfolio_or_error(tool_input["portfolio_id"])
            if err:
                return err
            try:
                plan = self._suggest_hedging.execute(tool_input["portfolio_id"])
            except OptionsDataProviderError as exc:
                return {"error": f"Couldn't fetch live options data: {exc}"}
            if not plan.suggestions:
                return {
                    "suggestions": [],
                    "positions_excluded": plan.positions_excluded,
                    "note": "No underlying has meaningful net delta exposure — nothing to hedge.",
                }
            return {
                "suggestions": [
                    {
                        "underlying_ticker": s.underlying_ticker,
                        "net_delta": s.net_delta,
                        "shares_to_trade": s.shares_to_trade,
                        "resulting_delta": s.resulting_delta,
                    }
                    for s in plan.suggestions
                ],
                "positions_excluded": plan.positions_excluded,
            }

        return {"error": f"Unknown tool: {tool_name}"}
