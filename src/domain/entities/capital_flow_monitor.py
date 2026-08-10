"""Capital Flow Monitor — a dashboard of market-flow and macro-driver
signals, distinct from the existing Capital Flow Agent
(capital_flow.py), which detects discrete, unusual events (an insider
buy, a late Senate filing). This feature is a periodic snapshot
dashboard, not an event detector, and shares no code with it beyond
both living under the same "capital flow" umbrella name.

11 modules across 2 real data-sourcing strategies:
- 2 modules (CREDIT_SPREADS, LIQUIDITY) are backed by real FRED API
  calls — deterministic, verified, no AI guessing involved.
- 9 modules (no free structured API exists for any of them) are
  backed by a Claude + web_search agent that searches the live web
  and returns its best-effort, source-cited reading. This is
  genuinely different in kind from the rest of this platform's real,
  structured data — an honest best-effort estimate, not a verified
  number — and is labelled as such throughout.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class CapitalFlowMonitorDetail:
    label: str
    value: str


@dataclass(frozen=True, slots=True)
class CapitalFlowMonitorModuleResult:
    """The common, uniform shape every one of the 11 modules produces
    — regardless of whether it came from a real FRED call or a
    web-search agent — so the REST/frontend layers deal with one
    shape, not two."""

    module_id: str
    headline_value: str
    headline_direction: str | None  # "inflow" | "outflow" | "supportive" | "headwind" | "mixed" | None
    headline_label: str
    details: tuple[CapitalFlowMonitorDetail, ...]
    read: str
    source_note: str
    as_of: str  # free-text period label (e.g. "2026-08-08" or "Q2 2026") — not always a clean date
    fetched_at: datetime
    is_agent_estimate: bool  # True for the 9 web-search-backed modules; False for the 2 real-FRED ones


@dataclass(frozen=True, slots=True)
class CapitalFlowMonitorSynthesis:
    regime: str
    stance: str  # "supportive" | "mixed" | "headwind"
    supportive: tuple[str, ...]
    headwinds: tuple[str, ...]
    conflict: str
    watch: str
    synthesized_at: datetime


@dataclass(frozen=True, slots=True)
class CapitalFlowMonitorSnapshot:
    """One saved day's board — a compact record of whatever modules
    were loaded that day plus the regime label, if synthesis ran.
    Mirrors the artifact's original window.storage shape, now backed
    by real Postgres persistence, per-user (matching this platform's
    existing per-user alerts/growth-candidates pattern, not a shared
    global board)."""

    snapshot_date: date
    # module_id -> (headline_value, headline_direction, as_of) — compact
    # by design, matching the original artifact's storage economy.
    signals: dict[str, tuple[str, str | None, str]] = field(default_factory=dict)
    regime_label: str | None = None
    regime_stance: str | None = None


@dataclass(frozen=True, slots=True)
class CapitalFlowMonitorModuleDef:
    """Static metadata for one of the 11 modules. prompt/schema are
    None for the 2 real-FRED modules (credit, liquidity) — they don't
    need an agent prompt at all, since a real FRED API call replaces
    the "search the web and guess" pattern entirely."""

    id: str
    group: str  # "flow" | "macro"
    title: str
    cadence: str
    source: str
    prompt: str | None = None
    schema: str | None = None


# The 2 real, FRED-backed modules — no prompt/schema, since
# capital_flow_monitor_math.py computes these from real FRED readings
# directly, no agent involved.
_FRED_BACKED_DEFS = [
    CapitalFlowMonitorModuleDef(
        id="credit", group="macro", title="Credit Spreads", cadence="Daily",
        source="ICE BofA HY OAS (FRED, real API)",
    ),
    CapitalFlowMonitorModuleDef(
        id="liquidity", group="macro", title="Liquidity Plumbing", cadence="Weekly (Fed H.4.1 Thu)",
        source="Fed balance sheet / RRP / TGA (FRED, real API)",
    ),
]

# The 9 modules with no free structured API — backed by a Claude +
# web_search agent instead. Prompts/schemas ported directly from the
# original artifact design; the "never invent precise numbers" rule
# in fetch's system instruction (see anthropic_capital_flow_monitor_
# agent.py) is the one honesty guardrail available for genuinely
# unstructured, agent-estimated data.
_AGENT_BACKED_DEFS = [
    CapitalFlowMonitorModuleDef(
        id="etf", group="flow", title="ETF Flows", cadence="Daily",
        source="etf.com / issuer data via search",
        prompt=(
            "Search the web for the most recent DAILY US ETF flow data (net creations/redemptions). "
            "Look for the latest total US-listed ETF net flows, and the top 2-3 ETFs by inflow and by "
            "outflow (e.g. SPY, QQQ, VOO, IWM, bond ETFs). Use sources like etf.com, ETF flow trackers, "
            "or financial news from the last few days."
        ),
        schema=(
            '{"as_of": "date string of the data", "headline_value": "net flow figure with units, '
            'e.g. \'+$4.2B\'", "headline_direction": "inflow" or "outflow", "headline_label": "short '
            'label, e.g. \'US-listed ETF net flow (day)\'", "details": [{"label": "e.g. \'Top inflow\'", '
            '"value": "e.g. \'SPY +$1.8B\'"}, ... 3-5 items], "read": "one-sentence interpretation of '
            'what this flow says about market demand", "source_note": "where the data came from"}'
        ),
    ),
    CapitalFlowMonitorModuleDef(
        id="ici", group="flow", title="ICI Fund Flows", cadence="Weekly",
        source="Investment Company Institute",
        prompt=(
            "Search the web for the most recent Investment Company Institute (ICI) WEEKLY estimated "
            "fund flows report for US mutual funds and ETFs. Find the latest weekly net flows for: "
            "domestic equity funds, bond funds, and money market fund total assets if available. "
            "ici.org publishes this weekly."
        ),
        schema=(
            '{"as_of": "week ending date", "headline_value": "domestic equity fund net flow with '
            'units", "headline_direction": "inflow" or "outflow", "headline_label": "Domestic equity '
            'funds (week)", "details": [{"label": "Bond funds", "value": "..."}, {"label": "Money '
            'market assets", "value": "..."}, ...], "read": "one-sentence interpretation", '
            '"source_note": "where the data came from"}'
        ),
    ),
    CapitalFlowMonitorModuleDef(
        id="cftc", group="flow", title="CFTC Positioning", cadence="Weekly",
        source="Commitments of Traders",
        prompt=(
            "Search the web for the most recent CFTC Commitments of Traders (COT) report data for US "
            "EQUITY INDEX FUTURES — especially S&P 500 (E-mini) net positioning of speculators / "
            "leveraged funds / non-commercials. Is positioning net long or net short, how large, and "
            "how did it change vs the prior week? Use CFTC data, Tradingster, or recent COT coverage."
        ),
        schema=(
            '{"as_of": "report date (Tuesday of the reporting week)", "headline_value": "net spec '
            'position, e.g. \'Net short 120k contracts\'", "headline_direction": "inflow" if net '
            'long/getting longer, "outflow" if net short/getting shorter, "headline_label": "S&P 500 '
            'futures — speculator net position", "details": [{"label": "Weekly change", "value": '
            '"..."}, {"label": "Nasdaq futures", "value": "..."}, ...], "read": "one-sentence '
            'interpretation (crowding, contrarian signal, etc.)", "source_note": "where the data came from"}'
        ),
    ),
    CapitalFlowMonitorModuleDef(
        id="margin", group="flow", title="FINRA Margin Debt", cadence="Monthly",
        source="FINRA margin statistics",
        prompt=(
            "Search the web for the most recent FINRA margin statistics — total margin debt (debit "
            "balances in customers' securities margin accounts). Find the latest monthly figure, the "
            "month-over-month change, and how it compares to recent highs. FINRA publishes this "
            "monthly; finance media covers it."
        ),
        schema=(
            '{"as_of": "month of the data", "headline_value": "total margin debt with units, e.g. '
            '\'$935B\'", "headline_direction": "inflow" if rising, "outflow" if falling, '
            '"headline_label": "Total FINRA margin debt", "details": [{"label": "MoM change", "value": '
            '"..."}, {"label": "vs record high", "value": "..."}, ...], "read": "one-sentence '
            'interpretation of leverage in the system", "source_note": "where the data came from"}'
        ),
    ),
    CapitalFlowMonitorModuleDef(
        id="buybacks", group="flow", title="Buybacks", cadence="Quarterly + announcements",
        source="S&P DJ Indices / bank estimates",
        prompt=(
            "Search the web for the most recent data on US corporate stock BUYBACKS: latest quarterly "
            "S&P 500 buyback total (S&P Dow Jones Indices), year-to-date buyback announcement totals "
            "or authorizations (Goldman Sachs / Birinyi estimates), and any notable recent large "
            "buyback announcements. Note whether the market is currently in or near an earnings "
            "blackout window."
        ),
        schema=(
            '{"as_of": "period of the data", "headline_value": "latest quarterly or YTD buyback total '
            'with units", "headline_direction": "inflow", "headline_label": "e.g. \'S&P 500 buybacks '
            '(latest quarter)\'", "details": [{"label": "YTD announcements", "value": "..."}, {"label": '
            '"Blackout window", "value": "..."}, ...], "read": "one-sentence interpretation of '
            'corporate demand for equities", "source_note": "where the data came from"}'
        ),
    ),
    CapitalFlowMonitorModuleDef(
        id="fed", group="macro", title="Fed Expectations", cadence="Live",
        source="CME FedWatch / Fed funds futures",
        prompt=(
            "Search the web for the current Federal Reserve interest rate outlook: the current Fed "
            "funds target range, market-implied odds for the NEXT FOMC meeting (cut / hold / hike, "
            "from CME FedWatch or Fed funds futures coverage), how many cuts or hikes are priced in "
            "for the rest of the year, and the date of the next FOMC meeting."
        ),
        schema=(
            '{"as_of": "date of the data", "headline_value": "e.g. \'78% odds of a 25bp cut\'", '
            '"headline_direction": "supportive" if easing/cuts expected, "headwind" if hikes or '
            'hawkish hold, "headline_label": "Next FOMC meeting pricing", "details": [{"label": '
            '"Current target range", "value": "..."}, {"label": "Next FOMC date", "value": "..."}, '
            '{"label": "Cuts priced this year", "value": "..."}], "read": "one-sentence interpretation '
            'for stocks", "source_note": "where the data came from"}'
        ),
    ),
    CapitalFlowMonitorModuleDef(
        id="sentiment", group="macro", title="Sentiment & Volatility", cadence="Daily / weekly",
        source="VIX, AAII, Fear & Greed",
        prompt=(
            "Search the web for current US stock market sentiment indicators: the latest VIX level, "
            "the most recent AAII bull-bear survey (% bullish vs % bearish), and the CNN Fear & Greed "
            "Index reading if available. Note whether any are at extremes."
        ),
        schema=(
            '{"as_of": "date of the data", "headline_value": "e.g. \'VIX 14.2\'", "headline_direction": '
            '"supportive" if calm/neutral, "headwind" if fear spiking OR greed at contrarian extreme, '
            '"headline_label": "Volatility & sentiment", "details": [{"label": "AAII bulls / bears", '
            '"value": "..."}, {"label": "Fear & Greed", "value": "..."}], "read": "one-sentence '
            'interpretation, flagging contrarian extremes if present", "source_note": "where the data came from"}'
        ),
    ),
    CapitalFlowMonitorModuleDef(
        id="earnings", group="macro", title="Earnings Pulse", cadence="Weekly (FactSet Fri)",
        source="FactSet Earnings Insight / LSEG",
        prompt=(
            "Search the web for the current state of S&P 500 earnings: latest quarter's blended "
            "earnings growth rate (year-over-year), the percent of companies beating estimates this "
            "season, forward EPS estimate direction (are analysts revising up or down), and the "
            "forward P/E ratio. FactSet Earnings Insight (published Fridays) and LSEG are the standard "
            "free sources."
        ),
        schema=(
            '{"as_of": "period / date of the data", "headline_value": "e.g. \'+11.4% YoY earnings '
            'growth\'", "headline_direction": "supportive" if growth solid and revisions up, '
            '"headwind" if declining or revisions down, "headline_label": "S&P 500 blended earnings '
            'growth", "details": [{"label": "Beat rate", "value": "..."}, {"label": "Forward P/E", '
            '"value": "..."}, {"label": "Revisions", "value": "..."}], "read": "one-sentence '
            'interpretation of the fundamental backdrop", "source_note": "where the data came from"}'
        ),
    ),
    CapitalFlowMonitorModuleDef(
        id="calendar", group="macro", title="Event Calendar", cadence="Next 2 weeks",
        source="FOMC / macro data / earnings",
        prompt=(
            "Search the web for the major SCHEDULED US market events over the NEXT TWO WEEKS from "
            "today: the next FOMC meeting or Fed minutes, upcoming CPI and jobs report (nonfarm "
            "payrolls) release dates, any other top-tier data (PCE, retail sales), and the biggest "
            "S&P 500 earnings reports coming up (especially mega-caps). List them with dates."
        ),
        schema=(
            '{"as_of": "today\'s date", "headline_value": "the single biggest upcoming event, e.g. '
            '\'CPI — Aug 12\'", "headline_label": "Next major repricing moment", "details": [{"label": '
            '"date", "value": "event"}, ... 4-6 upcoming events in chronological order], "read": '
            '"one-sentence note on which event carries the most risk and why", "source_note": "where '
            'the data came from"}'
        ),
    ),
]

# Ordering matches the artifact's own section layout (I. flows, II.
# macro drivers) for a natural, familiar reading order.
CAPITAL_FLOW_MONITOR_MODULES: tuple[CapitalFlowMonitorModuleDef, ...] = tuple(
    [
        _AGENT_BACKED_DEFS[0],  # etf
        _AGENT_BACKED_DEFS[1],  # ici
        _AGENT_BACKED_DEFS[2],  # cftc
        _AGENT_BACKED_DEFS[3],  # margin
        _AGENT_BACKED_DEFS[4],  # buybacks
        _AGENT_BACKED_DEFS[5],  # fed
        _FRED_BACKED_DEFS[0],  # credit
        _AGENT_BACKED_DEFS[6],  # sentiment
        _AGENT_BACKED_DEFS[7],  # earnings
        _FRED_BACKED_DEFS[1],  # liquidity
        _AGENT_BACKED_DEFS[8],  # calendar
    ]
)
