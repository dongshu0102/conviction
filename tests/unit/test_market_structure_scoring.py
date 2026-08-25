from src.domain.services.market_structure_scoring import (
    classify_market_structure,
    compute_hhi,
    compute_market_shares,
)


def test_compute_market_shares_excludes_non_positive_or_missing_revenue() -> None:
    shares = compute_market_shares({"A": 100.0, "B": 0.0, "C": None, "D": -5.0, "E": 300.0})

    assert set(shares.keys()) == {"A", "E"}
    assert round(shares["A"], 4) == 0.25
    assert round(shares["E"], 4) == 0.75


def test_compute_market_shares_returns_empty_for_no_positive_revenue_at_all() -> None:
    assert compute_market_shares({"A": 0.0, "B": None}) == {}


def test_compute_hhi_hand_verified_near_monopoly() -> None:
    """900+50+50=1000 total -> shares 0.9/0.05/0.05 -> HHI = 90^2 + 5^2 + 5^2 = 8150."""
    shares = compute_market_shares({"A": 900.0, "B": 50.0, "C": 50.0})
    assert compute_hhi(shares) == 8150.0


def test_compute_hhi_hand_verified_duopoly() -> None:
    """45+45+10=100 -> shares 0.45/0.45/0.10 -> HHI = 45^2 + 45^2 + 10^2 = 4150."""
    shares = compute_market_shares({"A": 45.0, "B": 45.0, "C": 10.0})
    assert compute_hhi(shares) == 4150.0


def test_compute_hhi_is_10000_for_a_genuine_single_firm_monopoly() -> None:
    shares = compute_market_shares({"A": 100.0})
    assert compute_hhi(shares) == 10000.0


def test_classify_returns_monopoly_for_a_genuinely_dominant_single_firm() -> None:
    shares = compute_market_shares({"A": 90.0, "B": 5.0, "C": 5.0})
    hhi = compute_hhi(shares)
    assert classify_market_structure(hhi, shares["A"], 3) == "Monopoly"


def test_classify_returns_oligopoly_for_a_real_duopoly_with_no_single_dominant_firm() -> None:
    shares = compute_market_shares({"A": 45.0, "B": 45.0, "C": 10.0})
    hhi = compute_hhi(shares)
    # Neither firm individually exceeds 50%, but HHI (4150) is well above the real DOJ 2500 threshold.
    assert classify_market_structure(hhi, shares["A"], 3) == "Oligopoly"


def test_classify_returns_monopolistic_competition_for_a_moderately_fragmented_market() -> None:
    shares = compute_market_shares({"A": 20.0, "B": 20.0, "C": 20.0, "D": 20.0, "E": 20.0})
    hhi = compute_hhi(shares)  # 5 equal firms at 20% each -> HHI = 5 * 400 = 2000
    assert classify_market_structure(hhi, shares["A"], 5) == "Monopolistic Competition"


def test_classify_returns_perfect_competition_only_for_genuinely_many_small_equal_firms() -> None:
    shares = compute_market_shares({f"T{i}": 4.0 for i in range(25)})
    hhi = compute_hhi(shares)  # 25 equal firms at 4% each -> HHI = 25 * 16 = 400
    assert classify_market_structure(hhi, shares["T0"], 25) == "Perfect Competition"


def test_classify_is_honestly_unclassifiable_with_too_few_real_peers() -> None:
    assert classify_market_structure(None, None, 1) == "Unclassifiable (insufficient ingested peer data)"
    assert classify_market_structure(10000.0, 1.0, 1) == "Unclassifiable (insufficient ingested peer data)"
