"""Integration tests for the universe factor snapshot batch use case.

The pure z-score/composite arithmetic is already exhaustively
hand-verified in test_factor_math.py — these tests instead confirm the
WIRING: the right raw metric lands on the right factor with the right
sign (inverted vs not), the most recent fiscal year is used for
growth/quality, and one bad ticker never aborts the batch. Expected
z-scores are computed by calling the already-proven pure function
directly on the same raw-metric dict the use case should build, then
compared against the use case's actual output — this exercises the
wiring without re-deriving the arithmetic by hand a second time.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from src.application.use_cases.compute_financial_analysis import (
    ComputeFinancialAnalysisUseCase,
)
from src.application.use_cases.compute_universe_factor_snapshot import (
    ComputeUniverseFactorSnapshotUseCase,
)
from src.application.use_cases.compute_valuation import ComputeValuationUseCase
from src.application.use_cases.get_company_financials import GetCompanyFinancialsUseCase
from src.domain.entities.company import Company, Sector
from src.domain.entities.financial_statement import (
    BalanceSheet,
    FiscalPeriodKey,
    IncomeStatement,
    Period,
)
from src.domain.entities.market_quote import MarketQuote
from src.domain.services.factor_math import zscore_cross_section
from tests.unit.fakes import (
    FakeCompanyRepository,
    FakeDataProvider,
    FakeFactorScoreRepository,
    FakeFinancialStatementRepository,
)

# Deliberately decoupled from each other: net_income varies independently
# of market_cap, so a bug that accidentally swapped the Value and Size
# factors would produce a DIFFERENT ranking, not a coincidentally
# matching one (a risk if PE and market_cap moved in lockstep).
_UNIVERSE = {
    "AAA": {"market_cap": 1000.0, "net_income": 200.0, "equity": 2000.0, "rev_2023": 100.0, "rev_2024": 130.0},
    "BBB": {"market_cap": 3000.0, "net_income": 100.0, "equity": 500.0, "rev_2023": 100.0, "rev_2024": 110.0},
    "CCC": {"market_cap": 2000.0, "net_income": 50.0, "equity": 4000.0, "rev_2023": 100.0, "rev_2024": 105.0},
}


def _build(sp500_tickers: list[str] | None = None, with_momentum: bool = False):
    company_repo = FakeCompanyRepository()
    statement_repo = FakeFinancialStatementRepository()
    quotes = {}

    for ticker, d in _UNIVERSE.items():
        company_repo.save(
            Company(ticker=ticker, name=ticker, sector=Sector.TECHNOLOGY,
                     industry="X", exchange="NASDAQ", country="US")
        )
        statement_repo.save_income_statement(
            IncomeStatement(key=FiscalPeriodKey(ticker, 2023, Period.ANNUAL),
                             fiscal_date_ending=date(2023, 12, 31), reported_currency="USD",
                             revenue=d["rev_2023"], net_income=d["net_income"])
        )
        statement_repo.save_income_statement(
            IncomeStatement(key=FiscalPeriodKey(ticker, 2024, Period.ANNUAL),
                             fiscal_date_ending=date(2024, 12, 31), reported_currency="USD",
                             revenue=d["rev_2024"], net_income=d["net_income"])
        )
        statement_repo.save_balance_sheet(
            BalanceSheet(key=FiscalPeriodKey(ticker, 2024, Period.ANNUAL),
                          fiscal_date_ending=date(2024, 12, 31), reported_currency="USD",
                          total_equity=d["equity"])
        )
        quotes[ticker] = MarketQuote(
            ticker=ticker, price=100.0, market_cap=d["market_cap"],
            as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    provider_cls = FakeDataProvider
    provider = provider_cls(
        company=company_repo.get_by_ticker("AAA"),
        quotes_by_ticker=quotes,
        sp500_tickers=sp500_tickers if sp500_tickers is not None else list(_UNIVERSE.keys()),
    )
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    compute_valuation = ComputeValuationUseCase(get_financials, provider)
    compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)
    factor_repo = FakeFactorScoreRepository()

    use_case = ComputeUniverseFactorSnapshotUseCase(
        provider, compute_valuation, compute_analysis, factor_repo, request_delay_seconds=0.0
    )
    return use_case, factor_repo, company_repo


def _expected_z(raw_by_ticker: dict[str, dict], key: str, invert: bool) -> dict[str, float | None]:
    return zscore_cross_section({t: v[key] for t, v in raw_by_ticker.items()}, invert=invert)


def test_wiring_matches_pure_function_expectations() -> None:
    use_case, factor_repo, _ = _build()
    result = use_case.execute()

    assert result.total_tickers == 3
    assert result.succeeded == 3
    assert result.failed == []

    # PE = market_cap / net_income, computed the same way the use case should.
    raw = {
        t: {
            "pe": d["market_cap"] / d["net_income"],
            "roe": d["net_income"] / d["equity"],
            "growth": (d["rev_2024"] - d["rev_2023"]) / d["rev_2023"],
            "market_cap": d["market_cap"],
        }
        for t, d in _UNIVERSE.items()
    }
    expected_value = _expected_z(raw, "pe", invert=True)
    expected_quality = _expected_z(raw, "roe", invert=False)
    expected_growth = _expected_z(raw, "growth", invert=False)
    expected_size = _expected_z(raw, "market_cap", invert=True)

    scores = {s.ticker: s for s in factor_repo.get_all()}
    for ticker in _UNIVERSE:
        s = scores[ticker]
        assert abs(s.z_scores.value - expected_value[ticker]) < 1e-9
        assert abs(s.z_scores.quality - expected_quality[ticker]) < 1e-9
        assert abs(s.z_scores.growth - expected_growth[ticker]) < 1e-9
        assert abs(s.z_scores.size - expected_size[ticker]) < 1e-9
        assert s.z_scores.momentum is None  # FakeDataProvider has no history wired
        assert s.raw.price_to_earnings == raw[ticker]["pe"]


def test_one_bad_ticker_never_aborts_the_batch() -> None:
    # DEAD is in the sp500 list but never saved to company_repo, so
    # get_financials raises CompanyNotFoundError for it.
    use_case, factor_repo, _ = _build(sp500_tickers=["AAA", "BBB", "DEAD"])
    result = use_case.execute()

    assert result.total_tickers == 3
    assert result.succeeded == 2
    assert [f.ticker for f in result.failed] == ["DEAD"]

    tickers_scored = {s.ticker for s in factor_repo.get_all()}
    assert tickers_scored == {"AAA", "BBB"}


def test_refresh_replaces_the_whole_snapshot() -> None:
    use_case, factor_repo, company_repo = _build()
    use_case.execute()
    assert len(factor_repo.get_all()) == 3

    # Second refresh with a narrower universe, reusing the SAME cache,
    # should fully REPLACE it, not merge — a ticker dropped from the
    # universe must not linger with stale scores forever.
    statement_repo = FakeFinancialStatementRepository()
    d = _UNIVERSE["AAA"]
    statement_repo.save_income_statement(
        IncomeStatement(key=FiscalPeriodKey("AAA", 2024, Period.ANNUAL),
                         fiscal_date_ending=date(2024, 12, 31), reported_currency="USD",
                         revenue=d["rev_2024"], net_income=d["net_income"])
    )
    statement_repo.save_income_statement(
        IncomeStatement(key=FiscalPeriodKey("AAA", 2023, Period.ANNUAL),
                         fiscal_date_ending=date(2023, 12, 31), reported_currency="USD",
                         revenue=d["rev_2023"], net_income=d["net_income"])
    )
    statement_repo.save_balance_sheet(
        BalanceSheet(key=FiscalPeriodKey("AAA", 2024, Period.ANNUAL),
                      fiscal_date_ending=date(2024, 12, 31), reported_currency="USD",
                      total_equity=d["equity"])
    )
    provider = FakeDataProvider(
        company=company_repo.get_by_ticker("AAA"),
        quotes_by_ticker={"AAA": MarketQuote(ticker="AAA", price=100.0, market_cap=d["market_cap"],
                                              as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))},
        sp500_tickers=["AAA"],
    )
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    use_case2 = ComputeUniverseFactorSnapshotUseCase(
        provider,
        ComputeValuationUseCase(get_financials, provider),
        ComputeFinancialAnalysisUseCase(get_financials),
        factor_repo,  # SAME cache instance as the first refresh
        request_delay_seconds=0.0,
    )
    use_case2.execute()

    remaining = factor_repo.get_all()
    assert [s.ticker for s in remaining] == ["AAA"]  # BBB, CCC gone — full replace, not merge


def test_explicit_tickers_never_call_the_live_constituents_endpoint() -> None:
    """Proves the override actually bypasses get_sp500_constituent_tickers
    entirely — not just that it accepts a parameter. Regression test for
    the production incident where /sp500-constituent 402'd on a plan
    that doesn't include it, even though the tickers were already
    ingested and didn't need a live index-membership lookup at all."""
    use_case, factor_repo, company_repo = _build(sp500_tickers=["SHOULD_NEVER_BE_USED"])

    class _RaisesIfCalled:
        def get_sp500_constituent_tickers(self):
            raise AssertionError(
                "get_sp500_constituent_tickers should never be called when "
                "an explicit ticker list is provided"
            )

    # Swap in a provider whose live-constituents call would fail loudly
    # if it were ever reached, while everything else stays wired to the
    # real fixture data via the use case's other already-built dependencies.
    use_case._data_provider = _RaisesIfCalled()

    result = use_case.execute(tickers=["AAA", "BBB"])

    assert result.total_tickers == 2
    assert result.succeeded == 2
    assert {s.ticker for s in factor_repo.get_all()} == {"AAA", "BBB"}


def test_transient_failure_retries_then_succeeds() -> None:
    """A rate-limit-style transient failure (429) should be retried,
    not given up on immediately — proven by making the fake provider
    fail exactly once per ticker then succeed on retry."""
    use_case, factor_repo, company_repo = _build(sp500_tickers=["AAA"])

    call_count = {"n": 0}
    real_get_quote = use_case._data_provider.get_quote

    def _flaky_get_quote(ticker):
        call_count["n"] += 1
        if call_count["n"] == 1:
            from src.application.interfaces.data_provider import DataProviderError
            raise DataProviderError("429 Too Many Requests")
        return real_get_quote(ticker)

    use_case._data_provider.get_quote = _flaky_get_quote
    use_case._base_backoff_seconds = 0.01  # keep the test fast

    result = use_case.execute(tickers=["AAA"])

    assert result.succeeded == 1  # recovered after the retry
    assert call_count["n"] == 2  # failed once, succeeded on attempt 2


def test_permanently_missing_data_does_not_retry() -> None:
    """CompanyNotFoundError/NoFinancialDataError are checked by TYPE,
    not by string-matching an HTTP status code — a ticker that simply
    isn't ingested is exactly as permanent as a 404, and retrying it
    wastes real time on every single production refresh, forever."""
    use_case, factor_repo, company_repo = _build(sp500_tickers=["AAA", "DEAD"])
    use_case._base_backoff_seconds = 5.0  # would make the test slow if a retry were (wrongly) attempted

    import time
    start = time.time()
    result = use_case.execute(tickers=["AAA", "DEAD"])
    elapsed = time.time() - start

    assert elapsed < 1.0  # proves no backoff sleep was ever triggered for DEAD
    assert [f.ticker for f in result.failed] == ["DEAD"]


def test_etf_like_ticker_with_no_statements_gets_partial_momentum_and_size_not_excluded() -> None:
    """The exact ETF case: a Company profile exists (so it's a known,
    ingested ticker), but zero financial statements exist (by
    construction — funds don't file income statements). Must NOT be
    excluded from the batch the way a truly-unknown ticker would be;
    must instead contribute Momentum + Size, honestly None for
    Value/Quality/Growth."""
    company_repo = FakeCompanyRepository()
    company_repo.save(
        Company(ticker="ETF1", name="Some ETF", sector=Sector.ETF,
                 industry="Equity", exchange="", country="US")
    )
    statement_repo = FakeFinancialStatementRepository()  # deliberately empty — no statements saved at all

    quote = MarketQuote(ticker="ETF1", price=100.0, market_cap=5_000_000_000.0,
                          as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))
    provider = FakeDataProvider(
        company=company_repo.get_by_ticker("ETF1"),
        quotes_by_ticker={"ETF1": quote},
        sp500_tickers=["ETF1"],
    )
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    use_case = ComputeUniverseFactorSnapshotUseCase(
        provider,
        ComputeValuationUseCase(get_financials, provider),
        ComputeFinancialAnalysisUseCase(get_financials),
        FakeFactorScoreRepository(),
        request_delay_seconds=0.0,
    )

    result = use_case.execute()

    assert result.succeeded == 1  # NOT excluded, despite zero statements
    assert result.failed == []
    factor_repo = use_case._factor_repo  # noqa: SLF001 — test-only introspection
    score = factor_repo.get_all()[0]
    assert score.raw.market_cap == 5_000_000_000.0  # collected via live quote, not valuation
    assert score.raw.price_to_earnings is None  # honestly absent, not fabricated
    assert score.raw.return_on_equity is None
    assert score.raw.revenue_growth_yoy is None
