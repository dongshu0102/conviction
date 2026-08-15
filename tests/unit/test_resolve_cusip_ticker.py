from src.application.use_cases.resolve_cusip_ticker import ResolveCusipTickerUseCase
from src.domain.services.cusip_ticker_resolution import CusipSearchResult
from tests.unit.fakes import FakeCusipSearchProvider, FakeCusipTickerMapRepository


def test_execute_calls_fmp_and_saves_a_new_resolution() -> None:
    provider = FakeCusipSearchProvider(results_by_cusip={
        "037833100": [
            CusipSearchResult(symbol="AAPL.MX", company_name="Apple Inc.", market_cap=78_694_853_448_000),
            CusipSearchResult(symbol="AAPL", company_name="Apple Inc.", market_cap=4_537_071_141_960),
        ],
    })
    repo = FakeCusipTickerMapRepository()
    use_case = ResolveCusipTickerUseCase(repo, provider)

    result = use_case.execute("037833100")

    assert result.ticker == "AAPL"
    assert result.company_name == "Apple Inc."
    assert provider.search_cusip_calls == ["037833100"]
    # And it was actually saved, not just returned.
    assert repo.get("037833100") is not None
    assert repo.get("037833100").ticker == "AAPL"


def test_execute_uses_the_cache_and_never_calls_fmp_a_second_time() -> None:
    provider = FakeCusipSearchProvider(results_by_cusip={
        "037833100": [CusipSearchResult(symbol="AAPL", company_name="Apple Inc.", market_cap=1)],
    })
    repo = FakeCusipTickerMapRepository()
    use_case = ResolveCusipTickerUseCase(repo, provider)

    first = use_case.execute("037833100")
    second = use_case.execute("037833100")

    assert first == second
    assert provider.search_cusip_calls == ["037833100"], "FMP should only be called once, not twice"


def test_execute_force_true_re_queries_fmp_even_when_cached() -> None:
    provider = FakeCusipSearchProvider(results_by_cusip={
        "037833100": [CusipSearchResult(symbol="AAPL", company_name="Apple Inc.", market_cap=1)],
    })
    repo = FakeCusipTickerMapRepository()
    use_case = ResolveCusipTickerUseCase(repo, provider)

    use_case.execute("037833100")
    use_case.execute("037833100", force=True)

    assert provider.search_cusip_calls == ["037833100", "037833100"]


def test_execute_saves_a_none_ticker_when_no_us_listing_exists() -> None:
    """A real, meaningful, permanent result -- not something to
    silently retry on every future run."""
    provider = FakeCusipSearchProvider(results_by_cusip={
        "999999999": [CusipSearchResult(symbol="XYZ.DE", company_name="Foreign Co", market_cap=1)],
    })
    repo = FakeCusipTickerMapRepository()
    use_case = ResolveCusipTickerUseCase(repo, provider)

    result = use_case.execute("999999999")

    assert result.ticker is None
    assert repo.get("999999999") is not None  # saved, not treated as a failure to retry


def test_execute_handles_a_cusip_fmp_has_no_data_for_at_all() -> None:
    provider = FakeCusipSearchProvider(results_by_cusip={})  # empty results for any CUSIP
    repo = FakeCusipTickerMapRepository()
    use_case = ResolveCusipTickerUseCase(repo, provider)

    result = use_case.execute("000000000")

    assert result.ticker is None
    assert result.company_name is None
