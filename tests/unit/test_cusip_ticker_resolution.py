from src.domain.services.cusip_ticker_resolution import (
    CusipSearchResult,
    pick_primary_us_ticker,
)


def test_picks_the_no_dot_us_listing_among_multiple_foreign_listings() -> None:
    """Regression guard for the exact real FMP response confirmed
    tonight for Apple's CUSIP (037833100): four rows come back, one
    US ("AAPL") and three foreign exchange listings with dot suffixes
    ("AAPL.MX", "APC.DE", "APC.F"). The foreign Mexican listing's raw
    marketCap number is actually LARGER than the real US one (a
    currency/data quirk) -- so market cap alone cannot be the primary
    disambiguator; the no-dot filter must run first."""
    results = [
        CusipSearchResult(symbol="AAPL.MX", company_name="Apple Inc.", market_cap=78_694_853_448_000),
        CusipSearchResult(symbol="APC.DE", company_name="Apple Inc.", market_cap=3_863_520_570_000),
        CusipSearchResult(symbol="AAPL", company_name="Apple Inc.", market_cap=4_537_071_141_960),
        CusipSearchResult(symbol="APC.F", company_name="Apple Inc.", market_cap=3_942_086_350_399.9995),
    ]

    assert pick_primary_us_ticker(results) == "AAPL"


def test_returns_none_when_no_us_listing_exists_at_all() -> None:
    """Never guesses by falling back to a foreign listing -- a wrong
    ticker is worse than no ticker at all."""
    results = [
        CusipSearchResult(symbol="XYZ.DE", company_name="Some Foreign Co", market_cap=1_000_000_000),
        CusipSearchResult(symbol="XYZ.PA", company_name="Some Foreign Co", market_cap=1_000_000_000),
    ]

    assert pick_primary_us_ticker(results) is None


def test_returns_none_for_an_empty_result_list() -> None:
    assert pick_primary_us_ticker([]) is None


def test_returns_the_single_us_candidate_directly() -> None:
    results = [CusipSearchResult(symbol="MSFT", company_name="Microsoft Corp", market_cap=3_000_000_000_000)]
    assert pick_primary_us_ticker(results) == "MSFT"


def test_multiple_us_listed_candidates_picks_the_largest_by_market_cap() -> None:
    """A real, if rare, scenario -- e.g. different share classes both
    without a dot suffix. Picks the largest as the most likely primary,
    most liquid listing."""
    results = [
        CusipSearchResult(symbol="BRKA", company_name="Berkshire Hathaway", market_cap=500_000_000_000),
        CusipSearchResult(symbol="BRKB", company_name="Berkshire Hathaway", market_cap=900_000_000_000),
    ]

    assert pick_primary_us_ticker(results) == "BRKB"


def test_handles_a_missing_market_cap_gracefully_without_crashing() -> None:
    results = [
        CusipSearchResult(symbol="AAA", company_name="A Co", market_cap=None),
        CusipSearchResult(symbol="BBB", company_name="B Co", market_cap=1_000_000_000),
    ]

    assert pick_primary_us_ticker(results) == "BBB"
