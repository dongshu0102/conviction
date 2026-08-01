"""Hand-verified arithmetic tests for portfolio volatility/correlation
math — same discipline as test_factor_math.py."""
from __future__ import annotations

from src.domain.services.portfolio_risk_math import (
    annualize_volatility,
    compute_simple_returns,
    correlation,
    parametric_var,
    portfolio_variance,
    trim_to_common_length,
)


def test_simple_returns_hand_verified() -> None:
    # Most-recent-first: [110, 100, 121] -> returns[0] = (110-100)/100=0.10
    # returns[1] = (100-121)/121 = -0.17355...
    returns = compute_simple_returns([110.0, 100.0, 121.0])
    assert abs(returns[0] - 0.10) < 1e-9
    assert abs(returns[1] - (-0.173553719)) < 1e-6


def test_simple_returns_skips_zero_close() -> None:
    returns = compute_simple_returns([10.0, 0.0, 5.0])
    assert len(returns) == 1  # the (10-0)/0 division skipped, only (0-5)/5 computed
    assert abs(returns[0] - (-1.0)) < 1e-9


def test_single_asset_portfolio_variance_equals_its_own_sample_variance() -> None:
    # returns = [0.01, -0.01, 0.01, -0.01], mean=0, sample variance
    # (n-1=3 denominator) = sum(sq devs)/3 = (4 * 0.0001)/3 = 0.00013333...
    returns = [0.01, -0.01, 0.01, -0.01]
    var = portfolio_variance({"A": 1.0}, {"A": returns})
    assert abs(var - (0.0004 / 3)) < 1e-12


def test_two_identical_assets_diversification_does_nothing() -> None:
    """B has EXACTLY the same returns as A. A 50/50 portfolio's return
    at every point is avg(x, x) = x, so portfolio variance must equal
    that shared series' own variance — diversification adds nothing
    when correlation is perfect and scale identical."""
    returns = [0.02, -0.01, 0.03, 0.00, -0.02]
    var_single = portfolio_variance({"A": 1.0}, {"A": returns})
    var_combined = portfolio_variance({"A": 0.5, "B": 0.5}, {"A": returns, "B": list(returns)})
    assert abs(var_single - var_combined) < 1e-12


def test_perfect_negative_correlation_hedges_to_zero_variance() -> None:
    """B is the exact negation of A. A 50/50 portfolio's return at
    every point is 0.5*x + 0.5*(-x) = 0 for every single observation —
    portfolio variance must be EXACTLY zero. This is the cleanest
    possible proof the covariance wiring (not just the diagonal
    variance terms) is actually being used."""
    a_returns = [0.02, -0.01, 0.03, 0.00, -0.02]
    b_returns = [-r for r in a_returns]
    var = portfolio_variance({"A": 0.5, "B": 0.5}, {"A": a_returns, "B": b_returns})
    assert abs(var - 0.0) < 1e-12


def test_correlation_of_identical_series_is_exactly_one() -> None:
    returns = [0.02, -0.01, 0.03, 0.00, -0.02]
    assert abs(correlation(returns, list(returns)) - 1.0) < 1e-9


def test_correlation_of_negated_series_is_exactly_negative_one() -> None:
    returns = [0.02, -0.01, 0.03, 0.00, -0.02]
    negated = [-r for r in returns]
    assert abs(correlation(returns, negated) - (-1.0)) < 1e-9


def test_correlation_undefined_for_zero_variance_series() -> None:
    flat = [0.01, 0.01, 0.01]
    normal = [0.02, -0.01, 0.03]
    assert correlation(flat, normal) is None


def test_annualize_volatility_hand_verified() -> None:
    # daily_vol=0.01, sqrt(252) ~= 15.8745 -> annualized ~= 0.158745
    result = annualize_volatility(0.01)
    assert abs(result - 0.158745) < 1e-4


def test_parametric_var_hand_verified() -> None:
    # 100000 * 0.01 * 1.645 = 1645.0 exactly
    assert abs(parametric_var(100_000.0, 0.01, 1.645) - 1645.0) < 1e-9


def test_trim_excludes_short_series_and_aligns_kept_ones_to_common_length() -> None:
    returns_by_ticker = {
        "LONG_A": [0.01] * 30,
        "LONG_B": [0.02] * 25,
        "SHORT": [0.03] * 5,
    }
    kept, excluded = trim_to_common_length(returns_by_ticker, min_observations=20)
    assert excluded == ["SHORT"]
    assert set(kept.keys()) == {"LONG_A", "LONG_B"}
    assert len(kept["LONG_A"]) == len(kept["LONG_B"]) == 25  # trimmed to shortest KEPT series


def test_trim_all_short_returns_empty_not_crash() -> None:
    kept, excluded = trim_to_common_length({"A": [0.01, 0.02]}, min_observations=20)
    assert kept == {}
    assert excluded == ["A"]


# ---- inverse_volatility_weights (naive risk parity) ----

from src.domain.services.portfolio_risk_math import inverse_volatility_weights


def test_inverse_volatility_weights_hand_verified_two_ticker() -> None:
    # vol A=0.01 -> inv=100; vol B=0.02 -> inv=50; total=150
    # weight_A = 100/150 = 0.666..., weight_B = 50/150 = 0.333...
    weights = inverse_volatility_weights({"A": 0.01, "B": 0.02})
    assert abs(weights["A"] - (2 / 3)) < 1e-9
    assert abs(weights["B"] - (1 / 3)) < 1e-9
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_inverse_volatility_weights_equal_vol_gives_equal_weight() -> None:
    weights = inverse_volatility_weights({"A": 0.02, "B": 0.02, "C": 0.02})
    assert all(abs(w - (1 / 3)) < 1e-9 for w in weights.values())


def test_inverse_volatility_weights_lower_vol_gets_more_weight() -> None:
    # Three tickers, decreasing volatility -> increasing weight
    weights = inverse_volatility_weights({"LOW": 0.005, "MID": 0.01, "HIGH": 0.02})
    assert weights["LOW"] > weights["MID"] > weights["HIGH"]


def test_inverse_volatility_weights_excludes_zero_or_negative_vol() -> None:
    weights = inverse_volatility_weights({"A": 0.01, "ZERO": 0.0, "B": 0.02})
    assert "ZERO" not in weights
    assert abs(sum(weights.values()) - 1.0) < 1e-9  # remaining two still normalize to 1


def test_inverse_volatility_weights_empty_input_returns_empty() -> None:
    assert inverse_volatility_weights({}) == {}
    assert inverse_volatility_weights({"A": 0.0}) == {}
