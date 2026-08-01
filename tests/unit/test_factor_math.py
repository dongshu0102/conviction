"""Hand-verified arithmetic tests for cross-sectional z-scoring and
composite weighting — same discipline as the Greeks/option-P&L tests."""
from __future__ import annotations

from src.domain.entities.factor_scores import FactorWeights, FactorZScores
from src.domain.services.factor_math import composite_score, zscore_cross_section


def test_zscore_hand_verified_three_ticker_population() -> None:
    # Values: 10, 20, 30 -> mean=20, population stdev = sqrt(((10-20)^2+(0)+(10)^2)/3)
    #        = sqrt((100+0+100)/3) = sqrt(66.667) = 8.16496...
    # z(10) = (10-20)/8.16496 = -1.224745
    # z(20) = 0
    # z(30) = (30-20)/8.16496 = 1.224745
    result = zscore_cross_section({"A": 10.0, "B": 20.0, "C": 30.0})
    assert abs(result["A"] - (-1.224745)) < 1e-4
    assert abs(result["B"] - 0.0) < 1e-9
    assert abs(result["C"] - 1.224745) < 1e-4


def test_zscore_invert_flips_sign_for_lower_is_better_factors() -> None:
    result = zscore_cross_section({"A": 10.0, "B": 20.0, "C": 30.0}, invert=True)
    assert abs(result["A"] - 1.224745) < 1e-4  # was most negative, now most positive
    assert abs(result["C"] - (-1.224745)) < 1e-4


def test_zscore_missing_value_stays_none_and_is_excluded_from_stats() -> None:
    # B is missing -> excluded from mean/stdev computation entirely.
    # Remaining: 10, 30 -> mean=20, pstdev = sqrt(((10-20)^2+(30-20)^2)/2) = sqrt(100) = 10
    # z(10) = (10-20)/10 = -1.0, z(30) = (30-20)/10 = 1.0
    result = zscore_cross_section({"A": 10.0, "B": None, "C": 30.0})
    assert result["B"] is None
    assert abs(result["A"] - (-1.0)) < 1e-9
    assert abs(result["C"] - 1.0) < 1e-9


def test_zscore_fewer_than_two_known_values_all_none() -> None:
    assert zscore_cross_section({"A": 10.0, "B": None}) == {"A": None, "B": None}
    assert zscore_cross_section({"A": None, "B": None}) == {"A": None, "B": None}


def test_zscore_zero_stdev_is_exactly_zero_not_none() -> None:
    # Every ticker identical -> perfectly average, a known fact, not an unknown one
    result = zscore_cross_section({"A": 5.0, "B": 5.0, "C": 5.0})
    assert result == {"A": 0.0, "B": 0.0, "C": 0.0}


def test_composite_equal_weight_hand_verified() -> None:
    # z = (1.0, 2.0, 3.0, None, -1.0), equal weights 0.2 each.
    # Growth is None -> excluded from BOTH sum and weight total.
    # weighted_sum = 1.0*0.2 + 2.0*0.2 + 3.0*0.2 + (-1.0)*0.2 = 0.2+0.4+0.6-0.2 = 1.0
    # weight_total = 0.2*4 = 0.8 -> composite = 1.0 / 0.8 = 1.25
    z = FactorZScores(value=1.0, quality=2.0, growth=None, momentum=3.0, size=-1.0)
    composite, used = composite_score(z, FactorWeights())
    assert used == 4
    assert abs(composite - 1.25) < 1e-9


def test_composite_all_missing_returns_none() -> None:
    z = FactorZScores(value=None, quality=None, growth=None, momentum=None, size=None)
    composite, used = composite_score(z, FactorWeights())
    assert composite is None and used == 0


def test_composite_custom_weights_hand_verified() -> None:
    # value=2.0 weight=0.5, quality=4.0 weight=0.1, rest None
    # weighted_sum = 2.0*0.5 + 4.0*0.1 = 1.0 + 0.4 = 1.4
    # weight_total = 0.5 + 0.1 = 0.6 -> composite = 1.4/0.6 = 2.333...
    z = FactorZScores(value=2.0, quality=4.0, growth=None, momentum=None, size=None)
    weights = FactorWeights(value=0.5, quality=0.1, growth=0.1, momentum=0.1, size=0.1)
    composite, used = composite_score(z, weights)
    assert used == 2
    assert abs(composite - (1.4 / 0.6)) < 1e-9


def test_composite_zero_weight_total_on_present_factors_returns_none() -> None:
    z = FactorZScores(value=1.0, quality=None, growth=None, momentum=None, size=None)
    weights = FactorWeights(value=0.0, quality=0.2, growth=0.2, momentum=0.2, size=0.2)
    composite, used = composite_score(z, weights)
    assert composite is None
    assert used == 1  # one factor was present, just weighted to zero
