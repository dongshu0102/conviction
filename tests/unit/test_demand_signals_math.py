from src.domain.services.demand_signals_math import (
    compute_analyst_consensus_direction,
    compute_revenue_growth_acceleration,
)


def test_growth_genuinely_accelerating_returns_true() -> None:
    assert compute_revenue_growth_acceleration(latest=0.15, prior=0.10) is True


def test_growth_genuinely_decelerating_returns_false() -> None:
    assert compute_revenue_growth_acceleration(latest=0.05, prior=0.10) is False


def test_equal_growth_rates_is_honestly_not_accelerating() -> None:
    assert compute_revenue_growth_acceleration(latest=0.10, prior=0.10) is False


def test_a_genuinely_missing_latest_figure_returns_none_not_a_guess() -> None:
    assert compute_revenue_growth_acceleration(latest=None, prior=0.10) is None


def test_a_genuinely_missing_prior_figure_returns_none_not_a_guess() -> None:
    assert compute_revenue_growth_acceleration(latest=0.10, prior=None) is None


def test_more_real_upgrades_than_downgrades_is_more_bullish() -> None:
    assert compute_analyst_consensus_direction(upgrades=3, downgrades=1) == "More bullish"


def test_more_real_downgrades_than_upgrades_is_more_bearish() -> None:
    assert compute_analyst_consensus_direction(upgrades=1, downgrades=3) == "More bearish"


def test_equal_real_upgrades_and_downgrades_is_mixed() -> None:
    assert compute_analyst_consensus_direction(upgrades=2, downgrades=2) == "Mixed"


def test_zero_of_both_is_honestly_no_recent_activity_not_mixed() -> None:
    assert compute_analyst_consensus_direction(upgrades=0, downgrades=0) == "No recent activity"
