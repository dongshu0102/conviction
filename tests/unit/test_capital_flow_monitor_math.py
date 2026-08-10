from datetime import date, timedelta

from src.domain.entities.economic_indicator import EconomicIndicatorReading
from src.domain.services.capital_flow_monitor_math import (
    CREDIT_SPREAD_SERIES_ID,
    build_credit_spread_module,
    build_liquidity_module,
)

TODAY = date(2026, 8, 8)


def _credit_readings(latest_value: float, daily_delta: float, n_days: int = 760) -> list[EconomicIndicatorReading]:
    """most-recent-first, weekdays only — matches this codebase's real
    FRED provider convention."""
    out = []
    d = TODAY
    v = latest_value
    for _ in range(n_days):
        if d.weekday() < 5:
            out.append(EconomicIndicatorReading(name=CREDIT_SPREAD_SERIES_ID, as_of=d, value=round(v, 4)))
        d -= timedelta(days=1)
        v -= daily_delta  # subtracting a positive delta as we go back = spreads were narrower in the past = widening now
    return out


def test_build_credit_spread_module_raises_on_empty_readings() -> None:
    try:
        build_credit_spread_module([])
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_build_credit_spread_module_widening_case_is_a_real_headwind() -> None:
    readings = _credit_readings(latest_value=3.20, daily_delta=0.005)
    result = build_credit_spread_module(readings)

    assert result.headline_value == "320bp"
    assert result.headline_direction == "headwind"
    assert result.is_agent_estimate is False
    # Hand-verified: ~21 trading days * 0.005pp/day ≈ 0.105pp ≈ +11-16bp range
    assert result.details[0].label == "1-month change"
    change_bp = int(result.details[0].value.replace("bp", "").replace("+", ""))
    assert 5 <= change_bp <= 20


def test_build_credit_spread_module_narrowing_case_is_supportive() -> None:
    readings = _credit_readings(latest_value=2.50, daily_delta=-0.005)  # negative delta = spreads were WIDER in the past = narrowing now
    result = build_credit_spread_module(readings)

    assert result.headline_direction == "supportive"


def test_build_credit_spread_module_tiny_change_is_mixed_not_forced_into_a_direction() -> None:
    """A change smaller than the deadband shouldn't be forced into
    'supportive' or 'headwind' — that would be reading a directional
    signal into what's genuinely noise."""
    readings = _credit_readings(latest_value=2.71, daily_delta=0.0001)
    result = build_credit_spread_module(readings)

    assert result.headline_direction == "mixed"


def test_build_credit_spread_module_bp_conversion_is_hand_verified_correct() -> None:
    """Regression test for a real bug caught during review: the
    1-month-change detail once displayed the raw percentage-point
    value with a 'bp' suffix, without the *100 conversion — so a real
    10bp move rounded down to '+0bp'."""
    readings = _credit_readings(latest_value=2.71, daily_delta=0.01)  # ~21bp/month move, unambiguous
    result = build_credit_spread_module(readings)

    assert result.details[0].value != "+0bp"
    change_bp = int(result.details[0].value.replace("bp", "").replace("+", ""))
    assert change_bp > 10  # a real, clearly non-zero move


def _liquidity_series(latest_value: float, weekly_delta: float, n_weeks: int = 20) -> list[EconomicIndicatorReading]:
    out = []
    d = TODAY
    v = latest_value
    for _ in range(n_weeks):
        out.append(EconomicIndicatorReading(name="WALCL", as_of=d, value=v))
        d -= timedelta(days=7)
        v -= weekly_delta  # subtracting a positive delta as we go back = balance sheet WAS smaller = growing now
    return out


def test_build_liquidity_module_raises_without_walcl() -> None:
    try:
        build_liquidity_module({"RRPONTSYD": [EconomicIndicatorReading(name="RRPONTSYD", as_of=TODAY, value=100.0)]})
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_build_liquidity_module_draining_case_is_a_real_headwind() -> None:
    readings = _liquidity_series(latest_value=6_500_000, weekly_delta=-40_000)  # negative = WAS larger = shrinking now
    result = build_liquidity_module({"WALCL": readings})

    assert result.headline_direction == "headwind"
    assert "QT ongoing" in result.details[0].value
    assert result.headline_value == "$6.50T"


def test_build_liquidity_module_expanding_case_is_supportive() -> None:
    readings = _liquidity_series(latest_value=6_500_000, weekly_delta=40_000)  # positive = WAS smaller = growing now
    result = build_liquidity_module({"WALCL": readings})

    assert result.headline_direction == "supportive"
    assert "expanding" in result.details[0].value


def test_build_liquidity_module_reports_missing_series_honestly() -> None:
    """A missing series (e.g. a real, partial FRED outage) shows as
    'unavailable' in its own row rather than failing the whole module
    or silently omitting the row."""
    readings = _liquidity_series(latest_value=6_500_000, weekly_delta=0)
    result = build_liquidity_module({"WALCL": readings})  # RRPONTSYD, WTREGEN, WRESBAL all missing

    labels_to_values = {d.label: d.value for d in result.details}
    assert labels_to_values["Overnight reverse repo"] == "unavailable"
    assert labels_to_values["Treasury General Account"] == "unavailable"
    assert labels_to_values["Bank reserves"] == "unavailable"


def test_build_liquidity_module_real_values_use_the_hand_verified_millions_formatter() -> None:
    walcl = _liquidity_series(latest_value=6_500_000, weekly_delta=0)
    rrp = [EconomicIndicatorReading(name="RRPONTSYD", as_of=TODAY, value=150_000.0)]
    result = build_liquidity_module({"WALCL": walcl, "RRPONTSYD": rrp})

    labels_to_values = {d.label: d.value for d in result.details}
    assert labels_to_values["Overnight reverse repo"] == "$150.0B"
