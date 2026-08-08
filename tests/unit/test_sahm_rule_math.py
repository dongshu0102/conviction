from datetime import date, timedelta

from src.domain.services.sahm_rule_math import (
    MIN_MONTHS_OF_DATA_REQUIRED,
    SAHM_RULE_TRIGGER_THRESHOLD,
    compute_sahm_rule,
)


def _readings(values_oldest_to_newest: list[float]) -> list[tuple[date, float]]:
    """Builds most-recent-first (date, value) tuples, matching this
    codebase's established convention for economic-indicator history."""
    return [
        (date(2026, 1, 1) - timedelta(days=30 * i), v)
        for i, v in enumerate(reversed(values_oldest_to_newest))
    ]


def test_sahm_rule_triggers_on_a_real_genuine_unemployment_upturn() -> None:
    """Hand-verified by hand before this test was written: 3-month
    averages computed manually give current=4.600, trailing-12mo
    min=3.567, gap=1.033 — well above the 0.50 threshold."""
    values = [3.5, 3.5, 3.6, 3.6, 3.7, 3.6, 3.5, 3.6, 3.7, 3.8, 4.0, 4.2, 4.4, 4.6, 4.8]
    result = compute_sahm_rule(_readings(values))

    assert result is not None
    assert abs(result.current_3mo_avg - 4.6) < 1e-9
    assert abs(result.trailing_12mo_min_3mo_avg - 3.5666666666666667) < 1e-9
    assert abs(result.gap - 1.0333333333333332) < 1e-9
    assert result.is_triggered is True
    assert "triggered" in result.interpretation.lower()


def test_sahm_rule_does_not_trigger_on_stable_or_declining_unemployment() -> None:
    """Hand-verified: monotonically declining unemployment means the
    most recent 3-month average IS the trailing 12-month minimum,
    giving a gap of exactly 0."""
    values = [4.0, 3.9, 3.9, 3.8, 3.8, 3.7, 3.7, 3.6, 3.6, 3.5, 3.5, 3.5, 3.4, 3.4, 3.4]
    result = compute_sahm_rule(_readings(values))

    assert result is not None
    assert abs(result.gap - 0.0) < 1e-9
    assert result.is_triggered is False
    assert "not triggered" in result.interpretation.lower()


def test_sahm_rule_returns_none_rather_than_a_fabricated_result_with_insufficient_data() -> None:
    """The core property this function exists to protect: never
    compute a partial or approximated Sahm Rule result from less data
    than the real, published rule actually requires."""
    for count in range(0, MIN_MONTHS_OF_DATA_REQUIRED):
        readings = _readings([4.0] * count)
        assert compute_sahm_rule(readings) is None, f"Expected None with only {count} months of data"


def test_sahm_rule_computes_correctly_with_exactly_the_minimum_required_data() -> None:
    """The boundary case right at MIN_MONTHS_OF_DATA_REQUIRED — should
    compute a real result, not treat the minimum as still insufficient."""
    values = [4.0] * MIN_MONTHS_OF_DATA_REQUIRED
    result = compute_sahm_rule(_readings(values))
    assert result is not None
    assert result.gap == 0.0


def test_sahm_rule_triggers_at_exactly_the_threshold_not_only_strictly_above_it() -> None:
    """The rule's real definition is >=, not >. A gap of exactly 0.50
    should trigger."""
    # 12 months flat at 3.0, then a jump that lands the 3-month average
    # at exactly 3.50 (0.50 above the 3.00 trailing minimum).
    values = [3.0] * 12 + [4.0, 3.5, 3.0]
    result = compute_sahm_rule(_readings(values))
    assert result is not None
    assert abs(result.gap - SAHM_RULE_TRIGGER_THRESHOLD) < 1e-9
    assert result.is_triggered is True
