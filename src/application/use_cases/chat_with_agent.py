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
from src.application.use_cases.get_company_financials import (
    CompanyNotFoundError,
    GetCompanyFinancialsUseCase,
)
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
    RemoveHoldingUseCase,
    TickerNotIngestedError,
)
from src.application.use_cases.manage_alerts import GetAlertsUseCase
from src.application.use_cases.generate_daily_brief import GenerateDailyBriefUseCase
from src.application.use_cases.ingest_company_data import IngestCompanyDataUseCase
from src.application.use_cases.assess_speculative_growth import (
    AssessSpeculativeGrowthUseCase,
)
from src.application.use_cases.manage_watchlist import (
    AddToWatchlistUseCase,
    GetWatchlistUseCase,
    ListWatchlistNamesUseCase,
    RemoveFromWatchlistUseCase,
    UpdateWatchlistItemUseCase,
)
from src.application.use_cases.construct_risk_parity_portfolio import (
    ConstructRiskParityPortfolioUseCase,
)
from src.application.use_cases.generate_theme_synthesis import GenerateThemeSynthesisUseCase
from src.application.use_cases.get_upcoming_earnings import GetUpcomingEarningsUseCase
from src.application.use_cases.ingest_etf_data import IngestEtfDataUseCase
from src.application.use_cases.suggest_theme import SuggestThemeUseCase
from src.application.use_cases.get_factor_scores import GetFactorScoresUseCase
from src.application.use_cases.manage_universe_theme import (
    AddTickerToThemeUseCase,
    CreateUniverseThemeUseCase,
    DeleteUniverseThemeUseCase,
    GetThemeTickersUseCase,
    ListUniverseThemesUseCase,
    RemoveTickerFromThemeUseCase,
    ThemeNotFoundError,
)
from src.application.use_cases.get_watchlist_news import GetWatchlistNewsUseCase
from src.domain.entities.factor_scores import FactorWeights
from src.application.use_cases.triage_watchlist import TriageWatchlistUseCase
from src.application.use_cases.recommend_stocks import RecommendStocksUseCase
from src.application.use_cases.screen_stocks import ScreenStocksUseCase
from src.application.use_cases.suggest_hedging import SuggestHedgingUseCase
from src.application.use_cases.suggest_rebalancing import SuggestRebalancingUseCase
from src.domain.repositories.research_report_repository import ResearchReportRepository

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are Conviction's assistant, embedded in the user's own \
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
deserve a re-check — as an observation, not advice.

get_factor_scores and rank_universe_by_factors are DIFFERENT from \
screen_stocks: screen_stocks scores against fixed absolute bands, these score \
each ticker against the REST OF THE S&P 500 at the same moment — a positive \
z-score always means "more attractive than the universe average" on that \
factor, never an absolute judgment. A null z-score means that factor's data \
was unavailable for this ticker, never that it scored exactly average — say \
so explicitly rather than omitting it.

Value and Size are SIGN-FLIPPED (inverted) before you ever see them — \
value_z and size_z are NOT raw z-scores of P/E or market cap/AUM, they are \
already negated so positive always means attractive. This makes it easy to \
re-derive the wrong plain-English direction by intuition — don't. A NEGATIVE \
size_z means the raw market cap/AUM is ABOVE the universe average (a large, \
not small, company or fund) — the opposite of what "negative" would suggest \
if you reasoned about it as a plain z-score. Concretely: a mega-cap or a \
large fund with a negative size_z should be described as "large — this factor \
penalizes size, and it's a big one," never as "smaller than average." Same \
logic for value_z: negative means a HIGH P/E (expensive), not cheap. When in \
doubt, describe the RAW figure (the actual P/E, market cap, or AUM number) \
alongside the z-score rather than translating the sign into English from \
memory.

The snapshot refreshes at most once \
every 24 hours (composite weights recompute instantly and freely; the \
underlying universe scores do not), so mention the as_of timestamp if the \
user asks how current the ranking is. If get_factor_scores or \
rank_universe_by_factors returns an error mentioning factor scores are "not \
ready" or haven't been computed yet, say plainly that this feature refreshes \
on a schedule rather than on demand and to check back shortly — this is \
expected behavior on a fresh instance or right after a scheduled refresh \
window, not a broken feature.

Universe themes (create_universe_theme, add/remove_ticker_to/from_theme, \
list_universe_themes, get_theme_tickers) are GLOBAL — shared across every \
user, not personal to whoever is chatting. Treat creating or editing a theme \
as a shared, durable change, not a private preference; if the request seems \
like it's meant to be personal, a watchlist is very likely the better fit — \
ask if unsure. ETFs are ingested via ingest_etf, a separate tool from company \
ingestion (they have no financial statements — a fund holds other companies' \
shares, it doesn't run an operation). Once ingested, an ETF can be tagged \
into a theme just like any company. Its Value, Quality, and Growth factor \
scores will always be null — not a data gap, just honestly not applicable — \
while Momentum and Size (using AUM in place of market cap) work normally.


get_portfolio_risk's volatility fields are a standard parametric (variance-\
covariance) estimate assuming normally-distributed returns — a well-known \
approximation, not a guarantee; say so if the user asks about its \
reliability. parametric_var_95_1day_dollar is scoped to \
volatility_covered_weight of the portfolio, not necessarily all of it — if \
volatility_covered_weight is meaningfully below 1.0, say the analysis covers \
only that fraction of the portfolio's value rather than presenting the VaR \
figure as if it applied to the whole thing. Present this as risk information \
to help understand exposure, not as a trading signal.

construct_risk_parity_portfolio is a SIZING tool, not a stock-picking tool — \
it takes tickers already chosen (by the user, or from a theme) and proposes \
how much capital each should get based on volatility alone. It never \
predicts returns and never implies one ticker will outperform another. \
Lower volatility gets more weight; that is a risk choice, not a quality \
judgment — a boring, low-volatility company is not necessarily a better \
investment than a volatile one, just a smaller position under this \
methodology.

get_upcoming_earnings returns real dates and analyst EPS estimates from the \
data provider — never invent or guess an earnings date that isn't in the \
returned data, and never speculate about what a company will report. If the \
tool returns an error saying the earnings calendar isn't supported, say so \
plainly rather than trying to answer from general knowledge about when a \
company "usually" reports.

suggest_theme is a SUGGESTION tool, not an action tool — it proposes a theme \
grounded in real news, it never creates the theme or tags any ticker itself. \
Always present it as something for the user to review and decide on, using \
language like "here's a candidate theme" rather than "I've created." Some \
candidate tickers may have already_ingested: false — say plainly that those \
need to be ingested first (ingest_company or ingest_etf) before they can be \
tagged into a theme, and that this step will also reveal if a suggested \
ticker turns out not to be real. Never skip straight to create_universe_theme \
or add_ticker_to_theme after a suggestion without the user confirming they \
want it — that confirmation is what keeps this a suggestion, not an action \
taken on the user's behalf without being asked."""

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
        "since last monitoring check, move since the item was added, 1-month "
        "momentum, P/E drift vs the add-time baseline, and whether the entry "
        "target was crossed. Optionally scope to one list_name.",
        {"type": "object", "properties": {"list_name": {"type": "string"}}},
    ),
    ToolDefinition(
        "get_factor_scores",
        "Cross-sectional factor score for one ticker: Value, Quality, Growth, "
        "Momentum, and Size, each standardized (z-scored) against the rest of "
        "the S&P 500 at the same point in time — a positive z-score always means "
        "'more attractive than the universe average' on that factor, regardless "
        "of which raw metric drives it. This is DIFFERENT from screen_stocks, "
        "which scores against fixed absolute bands, not the live universe. "
        "Optionally pass custom weights (each 0-1) to reweight the composite; "
        "omitted weights default to equal (0.2 each). A missing z-score means "
        "that factor's underlying data was unavailable for this ticker — never "
        "treat it as zero/average.",
        {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "weight_value": {"type": "number"},
                "weight_quality": {"type": "number"},
                "weight_growth": {"type": "number"},
                "weight_momentum": {"type": "number"},
                "weight_size": {"type": "number"},
            },
            "required": ["ticker"],
        },
    ),
    ToolDefinition(
        "rank_universe_by_factors",
        "Rank the S&P 500 universe by composite factor score (Value/Quality/"
        "Growth/Momentum/Size, weighted). Returns the top N tickers. Same "
        "weighting rules as get_factor_scores. Use this for 'what are the best "
        "value stocks right now' or 'top momentum names' style questions — it "
        "is a live cross-sectional ranking, not a fixed screen. Optionally pass "
        "theme_name to restrict results to a curated theme's tickers — note "
        "this FILTERS the full-S&P-500 ranking down to that theme's members, "
        "it does NOT re-standardize scores against just the theme, so a "
        "z-score still reflects standing against the whole universe, not just "
        "the theme; say so if asked.",
        {
            "type": "object",
            "properties": {
                "top_n": {"type": "integer"},
                "theme_name": {"type": "string"},
                "weight_value": {"type": "number"},
                "weight_quality": {"type": "number"},
                "weight_growth": {"type": "number"},
                "weight_momentum": {"type": "number"},
                "weight_size": {"type": "number"},
            },
        },
    ),
    ToolDefinition(
        "create_universe_theme",
        "Create a new global curated theme (e.g. 'AI Infrastructure', 'China', "
        "'Fintech') that companies can be tagged into. Themes are shared across "
        "all users — a system-wide taxonomy, not a personal list. Idempotent: "
        "creating an existing theme name is a no-op.",
        {
            "type": "object",
            "properties": {"name": {"type": "string"}, "description": {"type": "string"}},
            "required": ["name"],
        },
    ),
    ToolDefinition(
        "add_ticker_to_theme",
        "Tag a ticker into a theme. A ticker can belong to multiple themes at "
        "once (e.g. NVDA can be in both 'AI Infrastructure' and "
        "'Semiconductors'). The ticker must already be ingested, and the theme "
        "must already exist.",
        {
            "type": "object",
            "properties": {"theme_name": {"type": "string"}, "ticker": {"type": "string"}},
            "required": ["theme_name", "ticker"],
        },
    ),
    ToolDefinition(
        "remove_ticker_from_theme",
        "Untag a ticker from one theme (does not affect its other themes).",
        {
            "type": "object",
            "properties": {"theme_name": {"type": "string"}, "ticker": {"type": "string"}},
            "required": ["theme_name", "ticker"],
        },
    ),
    ToolDefinition(
        "delete_theme",
        "PERMANENTLY delete an entire universe theme, including every "
        "ticker tagged into it. This cannot be undone, and — unlike "
        "deleting a portfolio — themes are shared across every user, so "
        "this removes it for everyone, not just the person asking. Only "
        "call this after the user has clearly, explicitly confirmed they "
        "want to delete a SPECIFIC theme by name — never call this "
        "speculatively, as a side effect of some other request, or "
        "without explicit confirmation.",
        {
            "type": "object",
            "properties": {"theme_name": {"type": "string"}},
            "required": ["theme_name"],
        },
    ),
    ToolDefinition(
        "list_universe_themes",
        "List every curated theme with its member count.",
        {"type": "object", "properties": {}},
    ),
    ToolDefinition(
        "get_theme_tickers",
        "Get every ticker tagged into a given theme.",
        {"type": "object", "properties": {"theme_name": {"type": "string"}}, "required": ["theme_name"]},
    ),
    ToolDefinition(
        "generate_theme_synthesis",
        "Generate an AI-written narrative synthesis across an ENTIRE curated "
        "theme — what ties the group together, common threads, notable "
        "outliers, and risks visible across the theme as a whole. Different "
        "from get_company_research (single ticker, deep dive): this is a "
        "cross-sectional view of a group. Grounded in real screening and "
        "factor-scoring data for every ticker in the theme; not persisted, "
        "regenerated fresh each call. Can take a few seconds for a large theme.",
        {"type": "object", "properties": {"theme_name": {"type": "string"}}, "required": ["theme_name"]},
    ),
    ToolDefinition(
        "construct_risk_parity_portfolio",
        "Propose a FROM-SCRATCH dollar allocation across a list of tickers "
        "using risk parity: lower-volatility tickers get more capital, "
        "higher-volatility tickers get less, so no single holding dominates "
        "the portfolio's risk. This does NOT use any expected-return "
        "forecast — it is a risk-based allocation, not a return-maximizing "
        "one, and it is NOT a recommendation of which tickers to buy, only "
        "how to size positions across ones already chosen (e.g. a theme's "
        "members, or names the user is considering). Present the weights "
        "and the methodology_note; never imply this predicts which will "
        "perform best.",
        {
            "type": "object",
            "properties": {
                "tickers": {"type": "array", "items": {"type": "string"}},
                "total_investment": {"type": "number"},
            },
            "required": ["tickers", "total_investment"],
        },
    ),
    ToolDefinition(
        "get_upcoming_earnings",
        "Upcoming earnings announcements for the user's watchlist (or one named "
        "list), within the next 14 days by default. Returns real dates and "
        "analyst EPS estimates — never invent an earnings date not returned "
        "here. If the data provider doesn't support this, say so plainly "
        "rather than guessing at dates.",
        {
            "type": "object",
            "properties": {
                "list_name": {"type": "string"},
                "lookahead_days": {"type": "integer"},
            },
        },
    ),
    ToolDefinition(
        "get_stock_news",
        "Latest news headlines. With a ticker: news for that ticker. Without: "
        "news for every ticker on the user's watchlist (optionally one "
        "list_name). Returns real published headlines with sources and dates — "
        "never invent or embellish headlines beyond what is returned.",
        {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "list_name": {"type": "string"},
                "limit_per_ticker": {"type": "integer"},
            },
        },
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
        "get_portfolio",
        "Get a portfolio's raw detail — every holding (stock/ETF and "
        "option) with no computed valuation or risk. Use "
        "get_portfolio_valuation or get_portfolio_risk instead when the "
        "user actually wants numbers on how it's doing; use this when they "
        "just want to see what's in it.",
        {
            "type": "object",
            "properties": {"portfolio_id": {"type": "string"}},
            "required": ["portfolio_id"],
        },
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
        "Get risk metrics for one of the user's portfolios: concentration "
        "(largest position, Herfindahl index), sector exposure, weighted-"
        "average leverage, AND (when price history is available) portfolio "
        "volatility, pairwise correlations between holdings, and parametric "
        "95% 1-day VaR. Volatility fields may be null if price history "
        "couldn't be fetched for enough holdings — check "
        "volatility_covered_weight and excluded_from_volatility_calc before "
        "presenting a volatility figure as covering the whole portfolio.",
        {
            "type": "object",
            "properties": {"portfolio_id": {"type": "string"}},
            "required": ["portfolio_id"],
        },
    ),
    ToolDefinition(
        "suggest_theme",
        "Propose a NEW investment theme, grounded in real recent general "
        "market news. Optionally take a user-supplied topic hint (e.g. "
        "\"reshoring\") or infer purely from what's currently in the news. "
        "This is a SUGGESTION for the user to review — it never creates the "
        "theme or tags any ticker itself. Some suggested tickers may not be "
        "ingested yet (already_ingested: false) — those need ingest_company "
        "or ingest_etf before they can be tagged into a theme; that step "
        "will also fail cleanly if a ticker turns out not to be real. Makes "
        "a real LLM call and has a real cost.",
        {"type": "object", "properties": {"user_hint": {"type": "string"}}},
    ),
    ToolDefinition(
        "ingest_company",
        "Ingest a company's profile and financial statements (income "
        "statement, balance sheet, cash flow) so it can be watchlisted, "
        "added to a portfolio, or have research/analysis/valuation run on "
        "it. Not for ETFs/funds — use ingest_etf for those. Safe to call "
        "even if already ingested (re-ingests fresh data).",
        {
            "type": "object",
            "properties": {"ticker": {"type": "string"}, "years": {"type": "integer"}},
            "required": ["ticker"],
        },
    ),
    ToolDefinition(
        "assess_speculative_growth",
        "Assess a ticker as a speculative early-stage growth candidate — "
        "the honest way to look for a stock with genuinely large upside "
        "potential (a '100x' or 'multibagger' style search), NOT the same "
        "as get_factor_scores. Standard factor scoring penalizes negative "
        "ROE and a meaningless P/E — exactly what a real early-stage "
        "company looks like before a growth story plays out — so this "
        "runs a deliberately different, growth-and-risk-focused analysis "
        "instead: revenue growth trend (accelerating vs decelerating), "
        "profitability status, cash runway if burning cash, and an "
        "explicit list of real risk flags. Never returns a single "
        "confidence score, and NEVER frame the result as a prediction or "
        "recommendation — genuine 100x outcomes are extremely rare, and "
        "the same characteristics that produce big winners also produce "
        "total losses. The ticker must already be ingested first.",
        {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    ),
    ToolDefinition(
        "ingest_etf",
        "Ingest an ETF's profile (name, expense ratio, AUM) so it can be added "
        "to watchlists, themes, and screened/factor-scored. ETFs have no "
        "income statement — Value, Quality, and Growth factors will always be "
        "null for an ETF (nothing dishonest about that, there's no earnings "
        "to compute them from); Momentum and Size (using AUM) work normally. "
        "Use this instead of the regular ingest tool for a fund ticker.",
        {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]},
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
        "remove_holding",
        "Remove a stock/ETF position from a portfolio entirely. Not for "
        "options — use remove_option_holding for those.",
        {
            "type": "object",
            "properties": {
                "portfolio_id": {"type": "string"},
                "ticker": {"type": "string"},
            },
            "required": ["portfolio_id", "ticker"],
        },
    ),
    ToolDefinition(
        "get_alerts",
        "Get the user's price-move alerts from continuous monitoring — "
        "includes earnings alerts too. Set unread_only=true to see only "
        "alerts the user hasn't seen yet.",
        {
            "type": "object",
            "properties": {"unread_only": {"type": "boolean"}},
        },
    ),
    ToolDefinition(
        "get_daily_brief",
        "Generate a short AI narrative summarizing watchlist price moves, "
        "portfolio performance, and unread alerts. This makes a real LLM "
        "call with a real cost — don't call it more than once per "
        "conversation unless the user explicitly asks for a refresh.",
        {"type": "object", "properties": {}},
    ),
    ToolDefinition(
        "get_company_financials",
        "Get a company's raw ingested financial statements (income "
        "statement, balance sheet, cash flow) for the given number of most "
        "recent years — the underlying numbers, not the derived ratios "
        "get_company_analysis returns.",
        {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "years": {"type": "integer"},
            },
            "required": ["ticker"],
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
        "Rank a bounded list of tickers by value (cheapness: P/E, P/S, "
        "EV/EBITDA) and quality (ROE, margins, leverage). Returns value_score, "
        "quality_score, and composite_score for each — LOWER IS ALWAYS BETTER "
        "on these scores (rank 1 = best in the group). Provide EITHER tickers "
        "(name them explicitly, capped at 15 — for a handful of candidates the "
        "user named or you're proposing) OR theme_name (screens every ticker "
        "in that curated universe theme, capped at 40, since theme membership "
        "is already pre-curated rather than named per message).",
        {
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "The specific tickers to screen, e.g. ['JNJ', 'PFE', 'JPM'].",
                },
                "theme_name": {
                    "type": "string",
                    "description": "Screen every ticker in this curated theme instead of a named list.",
                },
            },
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
        get_watchlist_news: GetWatchlistNewsUseCase,
        get_factor_scores: GetFactorScoresUseCase,
        create_universe_theme: CreateUniverseThemeUseCase,
        add_ticker_to_theme: AddTickerToThemeUseCase,
        remove_ticker_from_theme: RemoveTickerFromThemeUseCase,
        list_universe_themes: ListUniverseThemesUseCase,
        get_theme_tickers: GetThemeTickersUseCase,
        generate_theme_synthesis: GenerateThemeSynthesisUseCase,
        get_upcoming_earnings: GetUpcomingEarningsUseCase,
        construct_risk_parity_portfolio: ConstructRiskParityPortfolioUseCase,
        ingest_etf: IngestEtfDataUseCase,
        suggest_theme: SuggestThemeUseCase,
        remove_holding: RemoveHoldingUseCase,
        get_alerts: GetAlertsUseCase,
        generate_daily_brief: GenerateDailyBriefUseCase,
        get_company_financials: GetCompanyFinancialsUseCase,
        ingest_company: IngestCompanyDataUseCase,
        assess_speculative_growth: AssessSpeculativeGrowthUseCase,
        delete_theme: DeleteUniverseThemeUseCase,
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
        self._get_watchlist_news = get_watchlist_news
        self._get_factor_scores = get_factor_scores
        self._create_universe_theme = create_universe_theme
        self._add_ticker_to_theme = add_ticker_to_theme
        self._remove_ticker_from_theme = remove_ticker_from_theme
        self._list_universe_themes = list_universe_themes
        self._get_theme_tickers = get_theme_tickers
        self._generate_theme_synthesis = generate_theme_synthesis
        self._get_upcoming_earnings = get_upcoming_earnings
        self._ingest_etf = ingest_etf
        self._suggest_theme = suggest_theme
        self._remove_holding = remove_holding
        self._get_alerts = get_alerts
        self._generate_daily_brief = generate_daily_brief
        self._get_company_financials = get_company_financials
        self._ingest_company = ingest_company
        self._assess_speculative_growth = assess_speculative_growth
        self._delete_theme = delete_theme
        self._construct_risk_parity_portfolio = construct_risk_parity_portfolio
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

        if tool_name in ("get_factor_scores", "rank_universe_by_factors"):
            weights = FactorWeights(
                value=tool_input.get("weight_value", 0.2),
                quality=tool_input.get("weight_quality", 0.2),
                growth=tool_input.get("weight_growth", 0.2),
                momentum=tool_input.get("weight_momentum", 0.2),
                size=tool_input.get("weight_size", 0.2),
            )

            def _serialize(ranked):
                return {
                    "ticker": ranked.ticker,
                    "composite_score": (
                        round(ranked.composite_score, 3)
                        if ranked.composite_score is not None else None
                    ),
                    "factors_used": ranked.factors_used,
                    "value_z": ranked.score.z_scores.value,
                    "quality_z": ranked.score.z_scores.quality,
                    "growth_z": ranked.score.z_scores.growth,
                    "momentum_z": ranked.score.z_scores.momentum,
                    "size_z": ranked.score.z_scores.size,
                    "raw": {
                        "price_to_earnings": ranked.score.raw.price_to_earnings,
                        "return_on_equity": ranked.score.raw.return_on_equity,
                        "revenue_growth_yoy": ranked.score.raw.revenue_growth_yoy,
                        "momentum_1m_pct": ranked.score.raw.momentum_1m_pct,
                        "market_cap": ranked.score.raw.market_cap,
                    },
                    "as_of": ranked.score.as_of.isoformat(),
                }

            note = (
                "Every z-score is standardized against the S&P 500 universe at "
                "the same point in time — positive always means 'more attractive "
                "than the universe average' on that factor. A null z-score means "
                "the underlying data was unavailable for this ticker, not that it "
                "scored exactly average."
            )

            if tool_name == "get_factor_scores":
                try:
                    ranked = self._get_factor_scores.execute_for_ticker(
                        tool_input["ticker"], weights
                    )
                except Exception as exc:
                    return {"error": str(exc)}
                if ranked is None:
                    return {"error": f"No factor score available for '{tool_input['ticker']}'."}
                return {"scoring_note": note, "result": _serialize(ranked)}

            top_n = tool_input.get("top_n", 10)
            try:
                all_ranked = self._get_factor_scores.execute(weights)
            except Exception as exc:
                return {"error": str(exc)}
            theme_name = tool_input.get("theme_name")
            if theme_name:
                try:
                    theme_tickers = set(self._get_theme_tickers.execute(theme_name))
                except Exception as exc:
                    return {"error": str(exc)}
                all_ranked = [r for r in all_ranked if r.ticker in theme_tickers]
            results = all_ranked[:top_n]
            return {"scoring_note": note, "results": [_serialize(r) for r in results]}

        if tool_name == "create_universe_theme":
            theme = self._create_universe_theme.execute(
                tool_input["name"], tool_input.get("description")
            )
            return {"name": theme.name, "description": theme.description, "status": "created"}

        if tool_name == "add_ticker_to_theme":
            try:
                self._add_ticker_to_theme.execute(tool_input["theme_name"], tool_input["ticker"])
                return {
                    "theme_name": tool_input["theme_name"],
                    "ticker": tool_input["ticker"].strip().upper(),
                    "status": "added",
                }
            except Exception as exc:
                return {"error": str(exc)}

        if tool_name == "remove_ticker_from_theme":
            removed = self._remove_ticker_from_theme.execute(
                tool_input["theme_name"], tool_input["ticker"]
            )
            if not removed:
                return {
                    "error": f"'{tool_input['ticker']}' was not tagged into "
                    f"'{tool_input['theme_name']}'."
                }
            return {"status": "removed"}

        if tool_name == "delete_theme":
            try:
                self._delete_theme.execute(tool_input["theme_name"])
            except ThemeNotFoundError as exc:
                return {"error": str(exc)}
            return {"status": "deleted", "theme_name": tool_input["theme_name"]}

        if tool_name == "list_universe_themes":
            summaries = self._list_universe_themes.execute()
            return {
                "themes": [
                    {"name": s.theme.name, "description": s.theme.description, "member_count": s.member_count}
                    for s in summaries
                ]
            }

        if tool_name == "get_theme_tickers":
            try:
                tickers = self._get_theme_tickers.execute(tool_input["theme_name"])
                return {"theme_name": tool_input["theme_name"], "tickers": tickers}
            except Exception as exc:
                return {"error": str(exc)}

        if tool_name == "generate_theme_synthesis":
            try:
                report = self._generate_theme_synthesis.execute(tool_input["theme_name"])
            except Exception as exc:
                return {"error": str(exc)}
            return {
                "theme_name": report.theme_name,
                "tickers_covered": report.tickers_covered,
                "tickers_excluded": report.tickers_excluded,
                "overview": report.overview,
                "common_threads": report.common_threads,
                "notable_divergences": report.notable_divergences,
                "key_risks": report.key_risks,
                "model_used": report.model_used,
            }

        if tool_name == "construct_risk_parity_portfolio":
            try:
                result = self._construct_risk_parity_portfolio.execute(
                    tool_input["tickers"], tool_input["total_investment"]
                )
            except Exception as exc:
                return {"error": str(exc)}
            return {
                "methodology_note": result.methodology_note,
                "total_investment": result.total_investment,
                "allocations": [
                    {
                        "ticker": a.ticker,
                        "target_weight": round(a.target_weight, 4),
                        "target_dollar_amount": round(a.target_dollar_amount, 2),
                        "daily_volatility": a.daily_volatility,
                        "current_price": a.current_price,
                        "suggested_shares": round(a.suggested_shares, 2),
                    }
                    for a in result.allocations
                ],
                "excluded": result.excluded,
            }

        if tool_name == "suggest_theme":
            try:
                suggestion = self._suggest_theme.execute(tool_input.get("user_hint"))
            except Exception as exc:
                return {"error": str(exc)}
            return {
                "theme_name": suggestion.theme_name,
                "rationale": suggestion.rationale,
                "candidate_tickers": [
                    {
                        "ticker": t.ticker,
                        "company_name": t.company_name,
                        "reasoning": t.reasoning,
                        "already_ingested": t.already_ingested,
                    }
                    for t in suggestion.candidate_tickers
                ],
                "sourced_headlines": suggestion.sourced_headlines,
                "note": (
                    "This is a suggestion only — nothing has been created or "
                    "tagged. Review with the user before calling "
                    "create_universe_theme / add_ticker_to_theme. Any "
                    "already_ingested=false ticker needs ingest_company or "
                    "ingest_etf first."
                ),
            }

        if tool_name == "ingest_company":
            try:
                result = self._ingest_company.execute(
                    tool_input["ticker"], years=tool_input.get("years", 5)
                )
            except Exception as exc:
                return {"error": str(exc)}
            return {
                "ticker": result.ticker,
                "income_statements_ingested": result.income_statements_ingested,
                "balance_sheets_ingested": result.balance_sheets_ingested,
                "cash_flow_statements_ingested": result.cash_flow_statements_ingested,
                "status": "ingested",
            }

        if tool_name == "assess_speculative_growth":
            try:
                result = self._assess_speculative_growth.execute(tool_input["ticker"])
            except CompanyNotFoundError as exc:
                return {"error": str(exc)}
            return {
                "ticker": result.ticker,
                "market_cap": result.market_cap,
                "revenue_growth_latest_yoy": result.revenue_growth_latest_yoy,
                "revenue_growth_prior_yoy": result.revenue_growth_prior_yoy,
                "growth_trend": result.growth_trend,
                "is_profitable": result.is_profitable,
                "net_income_latest": result.net_income_latest,
                "cash_runway_months": result.cash_runway_months,
                "years_of_data_available": result.years_of_data_available,
                "risk_flags": result.risk_flags,
                "note": (
                    "This is a structured risk/growth breakdown, not a prediction "
                    "or a recommendation. Genuine large-multiple outcomes are rare; "
                    "the same traits behind big winners are behind total losses too."
                ),
            }

        if tool_name == "ingest_etf":
            try:
                company = self._ingest_etf.execute(tool_input["ticker"])
            except Exception as exc:
                return {"error": str(exc)}
            return {
                "ticker": company.ticker,
                "name": company.name,
                "expense_ratio": company.expense_ratio,
                "aum": company.aum,
                "status": "ingested",
            }

        if tool_name == "get_upcoming_earnings":
            try:
                events = self._get_upcoming_earnings.execute(
                    self._user_id,
                    list_name=tool_input.get("list_name"),
                    lookahead_days=tool_input.get("lookahead_days", 14),
                )
            except Exception as exc:
                return {"error": str(exc)}
            return {
                "events": [
                    {
                        "ticker": e.ticker,
                        "report_date": e.report_date.isoformat(),
                        "eps_estimated": e.eps_estimated,
                        "eps_actual": e.eps_actual,
                        "revenue_estimated": e.revenue_estimated,
                        "revenue_actual": e.revenue_actual,
                    }
                    for e in events
                ]
            }

        if tool_name == "get_stock_news":
            ticker = tool_input.get("ticker")
            by_ticker, failed = self._get_watchlist_news.execute(
                self._user_id,
                list_name=tool_input.get("list_name"),
                tickers=[ticker] if ticker else None,
                limit_per_ticker=tool_input.get("limit_per_ticker", 5),
            )
            return {
                "news": {
                    t: [
                        {
                            "title": a.title,
                            "published_at": a.published_at.isoformat() if a.published_at else None,
                            "source": a.source,
                            "url": a.url,
                            "snippet": (a.snippet[:300] if a.snippet else None),
                        }
                        for a in articles
                    ]
                    for t, articles in by_ticker.items()
                },
                "tickers_failed": failed,
            }

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
                        "momentum_1m_percent": _pct(t.signals.momentum_1m_pct),
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

        if tool_name == "get_portfolio":
            err = self._own_portfolio_or_error(tool_input["portfolio_id"])
            if err:
                return err
            portfolio = self._get_portfolio.execute(tool_input["portfolio_id"])
            return {
                "portfolio_id": portfolio.portfolio_id,
                "name": portfolio.name,
                "created_at": portfolio.created_at.isoformat(),
                "holdings": [
                    {
                        "ticker": h.ticker, "shares": h.shares,
                        "cost_basis_per_share": h.cost_basis_per_share,
                    }
                    for h in portfolio.holdings
                ],
                "option_holdings": [
                    {
                        "underlying_ticker": h.contract.underlying_ticker,
                        "strike": h.contract.strike,
                        "expiration": h.contract.expiration.isoformat(),
                        "option_type": h.contract.option_type,
                        "contracts_held": h.contracts_held,
                    }
                    for h in portfolio.option_holdings
                ],
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
                "portfolio_daily_volatility": r.portfolio_daily_volatility,
                "portfolio_annualized_volatility": r.portfolio_annualized_volatility,
                "parametric_var_95_1day_dollar": r.parametric_var_95_1day_dollar,
                "volatility_covered_weight": r.volatility_covered_weight,
                "volatility_lookback_days_used": r.volatility_lookback_days_used,
                "pairwise_correlations": [
                    {"ticker_a": c.ticker_a, "ticker_b": c.ticker_b, "correlation": c.correlation}
                    for c in r.pairwise_correlations
                ],
                "excluded_from_volatility_calc": r.excluded_from_volatility_calc,
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

        if tool_name == "remove_holding":
            err = self._own_portfolio_or_error(tool_input["portfolio_id"])
            if err:
                return err
            removed = self._remove_holding.execute(tool_input["portfolio_id"], tool_input["ticker"])
            if not removed:
                return {"error": f"'{tool_input['ticker'].upper()}' is not a holding in this portfolio."}
            return {"ticker": tool_input["ticker"].upper(), "status": "removed"}

        if tool_name == "get_alerts":
            alerts = self._get_alerts.execute(
                self._user_id, unread_only=tool_input.get("unread_only", False)
            )
            return {
                "alerts": [
                    {
                        "ticker": a.ticker, "alert_type": a.alert_type.value, "message": a.message,
                        "change_pct": a.change_pct, "created_at": a.created_at.isoformat(),
                        "is_read": a.is_read,
                    }
                    for a in alerts
                ]
            }

        if tool_name == "get_daily_brief":
            try:
                brief = self._generate_daily_brief.execute(self._user_id)
            except Exception as exc:
                return {"error": str(exc)}
            return {
                "narrative": brief.narrative, "generated_at": brief.generated_at.isoformat(),
                "unread_alert_count": brief.unread_alert_count,
            }

        if tool_name == "get_company_financials":
            try:
                financials = self._get_company_financials.execute(
                    tool_input["ticker"], years=tool_input.get("years", 5)
                )
            except CompanyNotFoundError as exc:
                return {"error": str(exc)}
            return {
                "ticker": financials.company.ticker,
                "income_statements": [asdict(s) for s in financials.income_statements],
                "balance_sheets": [asdict(s) for s in financials.balance_sheets],
                "cash_flow_statements": [asdict(s) for s in financials.cash_flow_statements],
            }

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
            theme_name = tool_input.get("theme_name")
            if theme_name:
                try:
                    tickers = self._get_theme_tickers.execute(theme_name)[:40]
                except Exception as exc:
                    return {"error": str(exc)}
            else:
                tickers = tool_input.get("tickers", [])[:15]  # hard cap regardless of what's asked
            if not tickers:
                return {"error": "No tickers to screen — theme is empty or no tickers were provided."}
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
