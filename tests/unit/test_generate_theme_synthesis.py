"""Tests for GenerateThemeSynthesisUseCase — the grounding guarantee
(no LLM call without real data), the honest-exclusion behavior for
tickers with neither screening nor factor data, and error paths.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from src.application.use_cases.compute_financial_analysis import (
    ComputeFinancialAnalysisUseCase,
)
from src.application.use_cases.compute_valuation import ComputeValuationUseCase
from src.application.use_cases.generate_theme_synthesis import (
    GenerateThemeSynthesisUseCase,
    NoSynthesizableDataError,
    ThemeEmptyError,
)
from src.application.use_cases.get_company_financials import GetCompanyFinancialsUseCase
from src.application.use_cases.get_factor_scores import GetFactorScoresUseCase
from src.application.use_cases.manage_universe_theme import (
    AddTickerToThemeUseCase,
    CreateUniverseThemeUseCase,
    GetThemeTickersUseCase,
    ThemeNotFoundError,
)
from src.application.use_cases.screen_stocks import ScreenStocksUseCase
from src.domain.entities.company import Company, Sector
from src.domain.entities.factor_scores import FactorRawMetrics, FactorScore, FactorZScores
from src.domain.entities.financial_statement import (
    BalanceSheet, FiscalPeriodKey, IncomeStatement, Period,
)
from src.domain.entities.market_quote import MarketQuote
from tests.unit.fakes import (
    FakeCompanyRepository,
    FakeDataProvider,
    FakeFactorScoreRepository,
    FakeFinancialStatementRepository,
    FakeThemeSynthesisGenerator,
    FakeUniverseThemeRepository,
)

NOW = datetime.now(timezone.utc)


class _NoOpRefresh:
    def execute(self):
        pass  # factor_repo is pre-populated fresh; refresh should never be needed


def _build(tickers_with_financials: list[str], tickers_with_factor_only: list[str] = ()):
    """tickers_with_financials get full screen_stocks-ready data.
    tickers_with_factor_only get ONLY a FactorScore entry (no
    statements) — a synthetic but legitimate case for exercising the
    "either source contributes" merge logic."""
    company_repo = FakeCompanyRepository()
    statement_repo = FakeFinancialStatementRepository()
    quotes = {}
    all_tickers = list(tickers_with_financials) + list(tickers_with_factor_only)

    for ticker in all_tickers:
        company_repo.save(Company(ticker=ticker, name=ticker, sector=Sector.TECHNOLOGY,
                                    industry="X", exchange="NASDAQ", country="US"))

    for ticker in tickers_with_financials:
        statement_repo.save_income_statement(
            IncomeStatement(key=FiscalPeriodKey(ticker, 2024, Period.ANNUAL),
                             fiscal_date_ending=date(2024, 12, 31), reported_currency="USD",
                             revenue=1000.0, net_income=100.0, ebitda=200.0)
        )
        statement_repo.save_balance_sheet(
            BalanceSheet(key=FiscalPeriodKey(ticker, 2024, Period.ANNUAL),
                          fiscal_date_ending=date(2024, 12, 31), reported_currency="USD",
                          total_equity=500.0, total_debt=100.0, cash_and_equivalents=50.0)
        )
        quotes[ticker] = MarketQuote(ticker=ticker, price=50.0, market_cap=1000.0, as_of=NOW)

    provider = FakeDataProvider(company=company_repo.get_by_ticker(all_tickers[0]) if all_tickers else None,
                                  quotes_by_ticker=quotes)
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    compute_valuation = ComputeValuationUseCase(get_financials, provider)
    compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)
    screen_stocks = ScreenStocksUseCase(compute_valuation, compute_analysis)

    factor_repo = FakeFactorScoreRepository()
    factor_scores = []
    for ticker in tickers_with_factor_only:
        factor_scores.append(FactorScore(
            ticker=ticker, as_of=NOW,
            raw=FactorRawMetrics(price_to_earnings=15.0, return_on_equity=None,
                                   revenue_growth_yoy=None, momentum_1m_pct=None, market_cap=None),
            z_scores=FactorZScores(value=1.5, quality=None, growth=None, momentum=None, size=None),
        ))
    if factor_scores:
        factor_repo.save_batch(factor_scores)
    get_factor_scores = GetFactorScoresUseCase(factor_repo, _NoOpRefresh())

    theme_repo = FakeUniverseThemeRepository()
    return (
        theme_repo, company_repo,
        GetThemeTickersUseCase(theme_repo), screen_stocks, get_factor_scores, provider,
    )


def test_grounding_merges_both_sources_and_excludes_neither() -> None:
    theme_repo, company_repo, get_theme_tickers, screen_stocks, get_factor_scores, _ = _build(
        tickers_with_financials=["AAA"], tickers_with_factor_only=["BBB"]
    )
    CreateUniverseThemeUseCase(theme_repo).execute("Test Theme", "A test theme")
    add = AddTickerToThemeUseCase(theme_repo, company_repo)
    add.execute("Test Theme", "AAA")
    add.execute("Test Theme", "BBB")

    generator = FakeThemeSynthesisGenerator()
    use_case = GenerateThemeSynthesisUseCase(
        theme_repo, get_theme_tickers, screen_stocks, get_factor_scores, generator
    )
    report = use_case.execute("Test Theme")

    assert set(report.tickers_covered) == {"AAA", "BBB"}
    assert report.tickers_excluded == []
    assert generator.received_theme_name == "Test Theme"
    assert generator.received_theme_description == "A test theme"

    received_by_ticker = {t.ticker: t for t in generator.received_tickers}
    assert received_by_ticker["AAA"].composite_screen_score is not None  # has screen data
    assert received_by_ticker["AAA"].factor_composite_score is None  # no factor entry
    assert received_by_ticker["BBB"].composite_screen_score is None  # no financials
    assert received_by_ticker["BBB"].factor_composite_score is not None  # has factor entry
    assert received_by_ticker["BBB"].value_z == 1.5


def test_ticker_with_neither_source_is_excluded_not_fabricated() -> None:
    theme_repo, company_repo, get_theme_tickers, screen_stocks, get_factor_scores, _ = _build(
        tickers_with_financials=["AAA"]
    )
    CreateUniverseThemeUseCase(theme_repo).execute("Test Theme")
    add = AddTickerToThemeUseCase(theme_repo, company_repo)
    add.execute("Test Theme", "AAA")
    # NOTHING is added for "GHOST" — but let's simulate a ticker with a
    # company profile but zero financials/factor data by adding it too.
    company_repo.save(Company(ticker="GHOST", name="GHOST", sector=Sector.TECHNOLOGY,
                                industry="X", exchange="NASDAQ", country="US"))
    add.execute("Test Theme", "GHOST")

    generator = FakeThemeSynthesisGenerator()
    use_case = GenerateThemeSynthesisUseCase(
        theme_repo, get_theme_tickers, screen_stocks, get_factor_scores, generator
    )
    report = use_case.execute("Test Theme")

    assert report.tickers_covered == ["AAA"]
    assert report.tickers_excluded == ["GHOST"]


def test_unknown_theme_raises() -> None:
    theme_repo, company_repo, get_theme_tickers, screen_stocks, get_factor_scores, _ = _build([])
    generator = FakeThemeSynthesisGenerator()
    use_case = GenerateThemeSynthesisUseCase(
        theme_repo, get_theme_tickers, screen_stocks, get_factor_scores, generator
    )
    try:
        use_case.execute("Nonexistent")
        raise AssertionError("expected ThemeNotFoundError")
    except ThemeNotFoundError:
        pass


def test_empty_theme_raises() -> None:
    theme_repo, company_repo, get_theme_tickers, screen_stocks, get_factor_scores, _ = _build([])
    CreateUniverseThemeUseCase(theme_repo).execute("Empty")
    generator = FakeThemeSynthesisGenerator()
    use_case = GenerateThemeSynthesisUseCase(
        theme_repo, get_theme_tickers, screen_stocks, get_factor_scores, generator
    )
    try:
        use_case.execute("Empty")
        raise AssertionError("expected ThemeEmptyError")
    except ThemeEmptyError:
        pass


def test_no_synthesizable_data_raises_when_all_tickers_ungrounded() -> None:
    theme_repo, company_repo, get_theme_tickers, screen_stocks, get_factor_scores, _ = _build([])
    CreateUniverseThemeUseCase(theme_repo).execute("Ghost Theme")
    company_repo.save(Company(ticker="GHOST", name="GHOST", sector=Sector.TECHNOLOGY,
                                industry="X", exchange="NASDAQ", country="US"))
    AddTickerToThemeUseCase(theme_repo, company_repo).execute("Ghost Theme", "GHOST")

    generator = FakeThemeSynthesisGenerator()
    use_case = GenerateThemeSynthesisUseCase(
        theme_repo, get_theme_tickers, screen_stocks, get_factor_scores, generator
    )
    try:
        use_case.execute("Ghost Theme")
        raise AssertionError("expected NoSynthesizableDataError")
    except NoSynthesizableDataError:
        pass
    assert generator.received_tickers is None  # LLM never called with zero grounding
