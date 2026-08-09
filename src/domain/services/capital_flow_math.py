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
from datetime import datetime, timezone

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


def build_macro_flow_event(
    series_id: str,
    series_label: str,
    current_reading: EconomicIndicatorReading,
    prior_reading: EconomicIndicatorReading,
    change_threshold: float = DEFAULT_MACRO_FLOW_CHANGE_THRESHOLD,
) -> CapitalFlowEvent | None:
    """current_reading/prior_reading are EconomicIndicatorReading
    objects (date + value) — see get_series_history's real, existing
    shape. Returns None when the change can't be computed or doesn't
    clear the threshold."""
    change = compute_macro_flow_change(current_reading.value, prior_reading.value)
    if change is None or abs(change) < change_threshold:
        return None

    direction = CapitalFlowDirection.BUY if change > 0 else CapitalFlowDirection.SELL
    headline = (
        f"{series_label} moved {change:+.1%} — {current_reading.value:,.1f} "
        f"vs {prior_reading.value:,.1f} the prior period"
    )

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
    bar_date,
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
    headline = (
        f"{chamber_label} {trade.person_name} ({trade.office}) disclosed a "
        f"{trade.transaction_type.lower()} of {trade.asset_description} "
        f"({trade.symbol}), {trade.amount_range}"
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
    )
