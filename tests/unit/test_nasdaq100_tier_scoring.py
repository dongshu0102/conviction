from src.domain.services.nasdaq100_tier_scoring import (
    classify_market_cap_tier,
    classify_maturity_stage,
)


def test_classify_market_cap_tier_mega_cap() -> None:
    assert classify_market_cap_tier(3_000_000_000_000.0) == "Mega-Cap"
    assert classify_market_cap_tier(500_000_000_000.0) == "Mega-Cap"  # boundary, inclusive


def test_classify_market_cap_tier_large_cap() -> None:
    assert classify_market_cap_tier(200_000_000_000.0) == "Large-Cap"
    assert classify_market_cap_tier(100_000_000_000.0) == "Large-Cap"  # boundary, inclusive


def test_classify_market_cap_tier_mid_cap() -> None:
    assert classify_market_cap_tier(20_000_000_000.0) == "Mid-Cap"


def test_classify_market_cap_tier_honestly_none_for_missing_or_invalid_data() -> None:
    assert classify_market_cap_tier(None) is None
    assert classify_market_cap_tier(0.0) is None
    assert classify_market_cap_tier(-100.0) is None


def test_classify_maturity_stage_hyper_growth() -> None:
    assert classify_maturity_stage(0.35) == "Hyper-Growth"
    assert classify_maturity_stage(0.25) == "Hyper-Growth"  # boundary, inclusive


def test_classify_maturity_stage_growth() -> None:
    assert classify_maturity_stage(0.15) == "Growth"
    assert classify_maturity_stage(0.10) == "Growth"  # boundary, inclusive


def test_classify_maturity_stage_mature() -> None:
    assert classify_maturity_stage(0.05) == "Mature"
    assert classify_maturity_stage(-0.10) == "Mature"  # a real, honest revenue decline is still "Mature," not an error


def test_classify_maturity_stage_honestly_none_for_missing_data() -> None:
    assert classify_maturity_stage(None) is None
