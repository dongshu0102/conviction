"""Pure, real logic for the 2 of 11 Capital Flow Monitor modules that
have a genuine free structured API (FRED) — Credit Spreads and
Liquidity Plumbing. The other 9 modules (no free structured API
exists for any of them) are backed by a Claude + web_search agent
instead — see anthropic_capital_flow_monitor_agent.py. Nothing here
guesses; every number is a real FRED reading or a real, disclosed
computation over real FRED readings.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.domain.entities.capital_flow_monitor import (
    CapitalFlowMonitorDetail,
    CapitalFlowMonitorModuleResult,
)
from src.domain.entities.economic_indicator import EconomicIndicatorReading
from src.domain.services.capital_flow_math import _fmt_millions_usd

# BAMLH0A0HYM2 reports in percentage points (2.71 means 2.71%, i.e.
# 271bp) — confirmed directly against FRED's own series page, not
# assumed. FRED itself only distributes a rolling 3-year window for
# this series as of April 2026, which is why the "long-run average"
# below is honestly labeled as a 3-year average, not vaguely "long-run"
# — 3 years is the real maximum available, not an arbitrary choice.
CREDIT_SPREAD_SERIES_ID = "BAMLH0A0HYM2"
CREDIT_SPREAD_AVG_WINDOW_DAYS = 3 * 365
CREDIT_SPREAD_FLAT_DEADBAND_PP = 0.05  # percentage points — below this, call it "flat," not a direction

# WALCL, RRPONTSYD, WTREGEN, WRESBAL all report in millions of USD —
# confirmed directly against each series' own FRED page, not assumed.
LIQUIDITY_SERIES = {
    "WALCL": "Fed total assets (balance sheet)",
    "RRPONTSYD": "Overnight reverse repo",
    "WTREGEN": "Treasury General Account",
    "WRESBAL": "Bank reserves",
}
QT_LOOKBACK_DAYS = 90  # ~3 months — WALCL is weekly, so this is ~13 observations
QT_FLAT_DEADBAND_PCT = 1.0  # percent change over the lookback window — below this, "roughly flat"


def _closest_reading(readings: list[EconomicIndicatorReading], target_date) -> EconomicIndicatorReading:
    """The single reading whose as_of date is closest to target_date —
    robust to real gaps (weekends, holidays, revisions) in a daily or
    weekly series, unlike a fixed index offset."""
    return min(readings, key=lambda r: abs((r.as_of - target_date).days))


def build_credit_spread_module(readings: list[EconomicIndicatorReading]) -> CapitalFlowMonitorModuleResult:
    """readings: BAMLH0A0HYM2 history, most-recent-first (this
    codebase's established FRED convention)."""
    if not readings:
        raise ValueError("build_credit_spread_module requires at least one reading")

    latest = readings[0]
    one_month_target = latest.as_of - timedelta(days=30)
    one_month_ago = _closest_reading(readings, one_month_target)
    change_1mo_pp = latest.value - one_month_ago.value

    avg_cutoff = latest.as_of - timedelta(days=CREDIT_SPREAD_AVG_WINDOW_DAYS)
    window = [r.value for r in readings if r.as_of >= avg_cutoff]
    avg_3yr = sum(window) / len(window) if window else None

    if change_1mo_pp < -CREDIT_SPREAD_FLAT_DEADBAND_PP:
        direction = "supportive"  # spreads narrowing — credit conditions improving
    elif change_1mo_pp > CREDIT_SPREAD_FLAT_DEADBAND_PP:
        direction = "headwind"  # spreads widening — credit conditions deteriorating
    else:
        direction = "mixed"  # roughly flat — genuinely no clear signal from the 1-month change

    details = [
        CapitalFlowMonitorDetail("1-month change", f"{change_1mo_pp * 100:+.0f}bp"),
    ]
    if avg_3yr is not None:
        details.append(
            CapitalFlowMonitorDetail("vs 3-year average", f"{(latest.value - avg_3yr) * 100:+.0f}bp ({avg_3yr * 100:.0f}bp avg)")
        )

    return CapitalFlowMonitorModuleResult(
        module_id="credit",
        headline_value=f"{latest.value * 100:.0f}bp",
        headline_direction=direction,
        headline_label="High-yield OAS (ICE BofA)",
        details=tuple(details),
        read=(
            f"Credit spreads {'narrowed' if change_1mo_pp < 0 else 'widened' if change_1mo_pp > 0 else 'held roughly flat'} "
            f"over the past month — {'a supportive signal for equities' if direction == 'supportive' else 'an early-warning signal worth watching' if direction == 'headwind' else 'no clear signal from this alone'}."
        ),
        source_note=f"FRED series {CREDIT_SPREAD_SERIES_ID}, as of {latest.as_of.isoformat()}",
        as_of=latest.as_of.isoformat(),
        fetched_at=datetime.now(timezone.utc),
        is_agent_estimate=False,
    )


def build_liquidity_module(readings_by_series: dict[str, list[EconomicIndicatorReading]]) -> CapitalFlowMonitorModuleResult:
    """readings_by_series: {series_id: [readings, most-recent-first]}
    for all 4 series in LIQUIDITY_SERIES. A series missing from the
    dict (e.g. a real FRED outage for just that one series) is
    reported as unavailable in its own detail row rather than failing
    the whole module — partial real data beats no data."""
    if "WALCL" not in readings_by_series or not readings_by_series["WALCL"]:
        raise ValueError("build_liquidity_module requires at least WALCL data")

    walcl = readings_by_series["WALCL"]
    latest_walcl = walcl[0]
    qt_target = latest_walcl.as_of - timedelta(days=QT_LOOKBACK_DAYS)
    walcl_3mo_ago = _closest_reading(walcl, qt_target)
    pct_change = (latest_walcl.value - walcl_3mo_ago.value) / abs(walcl_3mo_ago.value) * 100

    if pct_change < -QT_FLAT_DEADBAND_PCT:
        qt_status = "QT ongoing (balance sheet shrinking)"
        direction = "headwind"  # liquidity draining
    elif pct_change > QT_FLAT_DEADBAND_PCT:
        qt_status = "Balance sheet expanding"
        direction = "supportive"  # liquidity being added
    else:
        qt_status = "QT paused / roughly flat"
        direction = "mixed"

    details = [CapitalFlowMonitorDetail("QT status", f"{qt_status} ({pct_change:+.1f}% over ~3mo)")]
    for series_id, label in LIQUIDITY_SERIES.items():
        if series_id == "WALCL":
            continue
        series_readings = readings_by_series.get(series_id)
        if series_readings:
            details.append(CapitalFlowMonitorDetail(label, _fmt_millions_usd(series_readings[0].value)))
        else:
            details.append(CapitalFlowMonitorDetail(label, "unavailable"))

    return CapitalFlowMonitorModuleResult(
        module_id="liquidity",
        headline_value=_fmt_millions_usd(latest_walcl.value),
        headline_direction=direction,
        headline_label="Fed balance sheet (system liquidity)",
        details=tuple(details),
        read=(
            f"{qt_status} — "
            f"{'cash is leaving the system, a real headwind for risk assets' if direction == 'headwind' else 'liquidity is being added, a real tailwind for risk assets' if direction == 'supportive' else 'no clear directional signal from the balance sheet alone right now'}."
        ),
        source_note=f"FRED series WALCL, as of {latest_walcl.as_of.isoformat()}",
        as_of=latest_walcl.as_of.isoformat(),
        fetched_at=datetime.now(timezone.utc),
        is_agent_estimate=False,
    )
