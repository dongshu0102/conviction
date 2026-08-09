"""Pure functions for turning real insider/political trading data into
CapitalFlowEvents — filtering out noise, parsing disclosure ranges,
and deciding what counts as "unusually large."

Kept free of any repository/provider imports — same principle as
valuation_math.py, rate_signal_math.py, and sahm_rule_math.py: this is
deterministic logic with an exact right answer given its inputs,
hand-verifiable and unit-testable in isolation, independent of how
InsiderTrade/PoliticianTrade objects get fetched.

Every threshold here is an explicit, named constant — never a silently
buried magic number — and every one is a genuine judgment call about
what counts as "notable," not a scientifically derived cutoff. A user
who wants a different bar should be able to see exactly what this
module currently uses and why.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone

from src.domain.entities.capital_flow import (
    CapitalFlowDirection,
    CapitalFlowEvent,
    CapitalFlowSource,
    InsiderTrade,
    PoliticianTrade,
)
from src.domain.entities.economic_indicator import EconomicIndicatorReading

# Most insider-trading rows are noise from this codebase's perspective:
# stock/option grants, plan conversions, exempt transactions — not real
# open-market conviction. FMP's own transactionType codes for genuine
# open-market activity start with these two letters.
MEANINGFUL_INSIDER_TRANSACTION_PREFIXES = ("P", "S")

# An insider trade below this real dollar value isn't unusual enough to
# surface — a director buying $5,000 of stock is routine, not a signal.
DEFAULT_INSIDER_MIN_VALUE_USD = 1_000_000.0

# A politician disclosure below this real dollar value (using the
# LOWER bound of the legally-required range, the conservative estimate)
# isn't unusual enough to surface.
DEFAULT_POLITICIAN_MIN_VALUE_USD = 50_000.0

_AMOUNT_RANGE_PATTERN = re.compile(r"\$?([\d,]+)\s*-\s*\$?([\d,]+)")


def parse_amount_range(amount_range: str) -> tuple[float, float] | None:
    """Parses a legally-required disclosure range like
    '$15,001 - $50,000' into (low, high). Returns None for genuinely
    unparseable formats (e.g. open-ended 'Over $50,000,000' ranges,
    which do appear in real data) rather than guessing — a caller that
    can't get a real number should treat the value as unknown, not
    silently substitute one."""
    match = _AMOUNT_RANGE_PATTERN.match(amount_range.strip())
    if not match:
        return None
    low = float(match.group(1).replace(",", ""))
    high = float(match.group(2).replace(",", ""))
    return (low, high)


def is_meaningful_insider_trade(trade: InsiderTrade) -> bool:
    """True only for real open-market purchases/sales — excludes
    grants, exercises, conversions, and other non-market-signal rows
    that make up the bulk of the raw feed."""
    return trade.transaction_type[:1] in MEANINGFUL_INSIDER_TRANSACTION_PREFIXES


def insider_trade_value(trade: InsiderTrade) -> float:
    return trade.securities_transacted * trade.price


# How large a real quarter-over-quarter (or month-over-month, series
# dependent) percent change in a macro-flow series must be to count as
# "unusual." A real, explicit judgment call — international
# capital-flow series are naturally noisier than, say, GDP, so this is
# deliberately a higher bar than a typical "beat/miss" threshold.
DEFAULT_MACRO_FLOW_CHANGE_THRESHOLD = 0.25


def compute_macro_flow_change(current: float, prior: float) -> float | None:
    """A real percent change, signed — deliberately NOT a "Nx" spike
    multiple like build_volume_event uses, since macro-flow series
    (e.g. the current account balance) can be negative, where a
    multiple is meaningless or actively misleading. Returns None when
    prior is exactly 0 — genuinely undefined, never fabricated as an
    infinite or capped value."""
    if prior == 0:
        return None
    return (current - prior) / abs(prior)


def _fmt_millions_usd(value_in_millions: float) -> str:
    """Formats a value already expressed in millions of USD (the real,
    confirmed unit for every series in DEFAULT_MACRO_SERIES below —
    verified directly against each series' own FRED page, not
    assumed) into a human-readable $M/$B/$T string. A prior version of
    this module's headline printed the raw number with no unit label
    at all — "434,808.0" — which is genuinely ambiguous/misleading
    without knowing it's millions, not raw dollars."""
    sign = "-" if value_in_millions < 0 else ""
    abs_val = abs(value_in_millions)
    if abs_val >= 1_000_000:
        return f"{sign}${abs_val / 1_000_000:,.2f}T"
    elif abs_val >= 1_000:
        return f"{sign}${abs_val / 1_000:,.1f}B"
    else:
        return f"{sign}${abs_val:,.1f}M"


def build_macro_flow_event(
    series_id: str,
    series_label: str,
    current_reading: EconomicIndicatorReading,
    prior_reading: EconomicIndicatorReading,
    change_threshold: float = DEFAULT_MACRO_FLOW_CHANGE_THRESHOLD,
    values_are_millions_usd: bool = True,
) -> CapitalFlowEvent | None:
    """current_reading/prior_reading are EconomicIndicatorReading
    objects (date + value) — see get_series_history's real, existing
    shape. Returns None when the change can't be computed or doesn't
    clear the threshold. values_are_millions_usd defaults to True
    because every series currently in DEFAULT_MACRO_SERIES is
    confirmed to report in millions of USD — explicit and overridable
    rather than silently assumed, in case a future series added to
    that dict uses different units."""
    change = compute_macro_flow_change(current_reading.value, prior_reading.value)
    if change is None or abs(change) < change_threshold:
        return None

    direction = CapitalFlowDirection.BUY if change > 0 else CapitalFlowDirection.SELL
    current_str = _fmt_millions_usd(current_reading.value) if values_are_millions_usd else f"{current_reading.value:,.1f}"
    prior_str = _fmt_millions_usd(prior_reading.value) if values_are_millions_usd else f"{prior_reading.value:,.1f}"
    headline = f"{series_label} moved {change:+.1%} — {current_str} vs {prior_str} the prior period"

    return CapitalFlowEvent(
        source=CapitalFlowSource.MACRO,
        symbol=None,  # a macro series isn't about any one ticker
        event_date=current_reading.as_of,
        direction=direction,
        headline=headline,
        detail_url=None,
        detected_at=datetime.now(timezone.utc),
        dedup_key=f"macro:{series_id}:{current_reading.as_of.isoformat()}",
    )


def build_insider_event(
    trade: InsiderTrade, min_value_usd: float = DEFAULT_INSIDER_MIN_VALUE_USD,
) -> CapitalFlowEvent | None:
    """Returns None for trades that aren't meaningful (grants,
    exercises) or aren't large enough to be unusual — never forces a
    CapitalFlowEvent out of a genuinely routine row."""
    if not is_meaningful_insider_trade(trade):
        return None

    value = insider_trade_value(trade)
    if value < min_value_usd:
        return None

    direction = (
        CapitalFlowDirection.BUY if trade.acquisition_or_disposition == "A"
        else CapitalFlowDirection.SELL if trade.acquisition_or_disposition == "D"
        else CapitalFlowDirection.UNKNOWN
    )
    verb = "bought" if direction == CapitalFlowDirection.BUY else "sold" if direction == CapitalFlowDirection.SELL else "transacted"
    headline = (
        f"{trade.reporting_name} ({trade.type_of_owner}) {verb} "
        f"{trade.securities_transacted:,.0f} shares of {trade.symbol} "
        f"at ${trade.price:,.2f} (${value:,.0f} total)"
    )

    return CapitalFlowEvent(
        source=CapitalFlowSource.INSIDER,
        symbol=trade.symbol,
        event_date=trade.transaction_date,
        direction=direction,
        headline=headline,
        detail_url=trade.url,
        detected_at=datetime.now(timezone.utc),
        dedup_key=f"insider:{trade.symbol}:{trade.reporting_name}:{trade.transaction_date.isoformat()}:{trade.securities_transacted}",
    )


DEFAULT_VOLUME_LOOKBACK_DAYS = 20
# Below this many prior trading days, an "average" isn't a real
# baseline — a 2-day average is too noisy to call anything a genuine
# spike against. Same principle as sahm_rule_math.py's
# MIN_MONTHS_OF_DATA_REQUIRED: never compute a ratio from insufficient
# history and present it as if it were meaningful.
MIN_PRIOR_DAYS_REQUIRED = 10
# How many times above the prior average today's volume must be to
# count as "unusual" — a real, explicit judgment call, not a
# statistically derived cutoff.
DEFAULT_VOLUME_SPIKE_MULTIPLE = 3.0


def average_prior_volume(
    volumes_most_recent_first: list[float], lookback_days: int = DEFAULT_VOLUME_LOOKBACK_DAYS,
) -> float | None:
    """volumes_most_recent_first[0] is treated as "today" and is
    NEVER included in its own baseline — the average is strictly the
    N prior days. Returns None if there's genuinely too little history
    to form a real baseline."""
    prior = volumes_most_recent_first[1 : 1 + lookback_days]
    if len(prior) < MIN_PRIOR_DAYS_REQUIRED:
        return None
    return sum(prior) / len(prior)


def build_volume_event(
    symbol: str,
    bar_date: date,
    volumes_most_recent_first: list[float],
    lookback_days: int = DEFAULT_VOLUME_LOOKBACK_DAYS,
    spike_multiple: float = DEFAULT_VOLUME_SPIKE_MULTIPLE,
) -> CapitalFlowEvent | None:
    """Returns None when there's insufficient history for a real
    baseline, or today's volume doesn't clear the spike threshold —
    never a fabricated or under-provisioned event."""
    if not volumes_most_recent_first:
        return None

    current_volume = volumes_most_recent_first[0]
    average_prior = average_prior_volume(volumes_most_recent_first, lookback_days)
    if average_prior is None or average_prior == 0:
        return None

    ratio = current_volume / average_prior
    if ratio < spike_multiple:
        return None

    headline = (
        f"{symbol} volume is {ratio:.1f}x its {lookback_days}-day average "
        f"({current_volume:,.0f} vs {average_prior:,.0f})"
    )

    return CapitalFlowEvent(
        source=CapitalFlowSource.VOLUME,
        symbol=symbol,
        event_date=bar_date,
        # A volume spike alone doesn't say which direction money moved
        # — that needs price direction too, which this function
        # deliberately doesn't have (it only receives volumes). Never
        # guessed at.
        direction=CapitalFlowDirection.UNKNOWN,
        headline=headline,
        detail_url=None,
        detected_at=datetime.now(timezone.utc),
        dedup_key=f"volume:{symbol}:{bar_date.isoformat()}",
    )


# The real STOCK Act deadline: a covered transaction must be disclosed
# no later than 45 days after the transaction date (30 days after
# notice, if earlier — but the transaction date is the one real,
# fixed anchor available in this data, so 45 days from it is the
# genuine hard cap this codebase can actually check).
STOCK_ACT_DISCLOSURE_DEADLINE_DAYS = 45


def is_late_filing(transaction_date: date, disclosure_date: date) -> bool:
    """True when a real disclosure arrived more than 45 days after the
    real transaction it discloses — a genuine STOCK Act violation, not
    a judgment call or a configurable threshold like the other
    thresholds in this module."""
    return (disclosure_date - transaction_date).days > STOCK_ACT_DISCLOSURE_DEADLINE_DAYS


def build_politician_event(
    trade: PoliticianTrade, min_value_usd: float = DEFAULT_POLITICIAN_MIN_VALUE_USD,
) -> CapitalFlowEvent | None:
    """Returns None when the disclosure range can't be parsed, or its
    conservative lower bound doesn't clear the threshold."""
    parsed = parse_amount_range(trade.amount_range)
    if parsed is None:
        return None

    low_bound, _high_bound = parsed
    if low_bound < min_value_usd:
        return None

    direction = (
        CapitalFlowDirection.BUY if trade.transaction_type.lower() == "purchase"
        else CapitalFlowDirection.SELL if trade.transaction_type.lower() == "sale"
        else CapitalFlowDirection.UNKNOWN
    )
    chamber_label = "Senator" if trade.chamber == CapitalFlowSource.SENATE else "Representative"
    late = is_late_filing(trade.transaction_date, trade.disclosure_date)
    headline = (
        f"{chamber_label} {trade.person_name} ({trade.office}) disclosed a "
        f"{trade.transaction_type.lower()} of {trade.asset_description} "
        f"({trade.symbol}), {trade.amount_range}"
        + (
            f" — filed {(trade.disclosure_date - trade.transaction_date).days} days "
            f"after the trade, past the STOCK Act's 45-day deadline"
            if late else ""
        )
    )

    return CapitalFlowEvent(
        source=trade.chamber,
        symbol=trade.symbol,
        event_date=trade.transaction_date,
        direction=direction,
        headline=headline,
        detail_url=trade.link,
        detected_at=datetime.now(timezone.utc),
        dedup_key=f"{trade.chamber.value.lower()}:{trade.symbol}:{trade.person_name}:{trade.transaction_date.isoformat()}:{trade.amount_range}",
        is_late_filing=late,
    )


# Real, confirmed-live FRED series (see FredProvider) — a deliberately
# curated, explicit list of international capital-flow series, not
# "every BOP-tagged series FRED has" (734 of them), most of which are
# too narrow or too slow-moving to be a real signal here. Lives here,
# not in the REST router, so both the router AND the standalone
# scan script can import it without either depending on the other —
# this module has zero framework dependencies (no FastAPI, no
# SQLAlchemy), which is exactly why run_capital_flow_scan.py runs as a
# lightweight standalone process outside the FastAPI app in the first
# place.
DEFAULT_MACRO_SERIES: dict[str, str] = {
    "IEABC": "Balance on current account",
    "ROWFDIQ027S": "Foreign Direct Investment in U.S. (transactions)",
    "USLTTOTALPOS99996": "U.S. portfolio holdings of foreign long-term securities",
    "FORLTTOTALPOS69995": "Foreign portfolio holdings of U.S. long-term securities",
}


# Exact, real Form 13F filing deadlines, copied directly from the
# SEC's own FAQ (sec.gov, "Frequently Asked Questions About Form
# 13F", Question 25, table for quarters ending 2026-2028, last
# reviewed March 13, 2026) — not computed algorithmically. The real
# rule (45 calendar days after each quarter-end, rolled forward past
# both weekends AND federal holidays) is genuinely complex enough that
# a from-scratch implementation risks silently drifting wrong; the
# SEC's own published table is the authoritative, verifiable source,
# at the cost of needing a manual update once the SEC publishes dates
# beyond 2028.
FORM_13F_DEADLINES: list[date] = [
    date(2026, 5, 15),  # 1Q 2026
    date(2026, 8, 14),  # 2Q 2026
    date(2026, 11, 16),  # 3Q 2026
    date(2027, 2, 16),  # 4Q 2026
    date(2027, 5, 17),  # 1Q 2027
    date(2027, 8, 16),  # 2Q 2027
    date(2027, 11, 15),  # 3Q 2027
    date(2028, 2, 14),  # 4Q 2027
    date(2028, 5, 15),  # 1Q 2028
    date(2028, 8, 14),  # 2Q 2028
    date(2028, 11, 14),  # 3Q 2028
    date(2029, 2, 14),  # 4Q 2028
]


def next_13f_deadline(as_of: date) -> date | None:
    """The next real Form 13F filing deadline on or after as_of.
    Returns None past the last date the SEC has published (currently
    Feb 14, 2029) — an honest "we genuinely don't know yet," never a
    guessed or extrapolated date."""
    for deadline in FORM_13F_DEADLINES:
        if deadline >= as_of:
            return deadline
    return None
