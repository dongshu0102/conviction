from __future__ import annotations

from datetime import date, datetime, timezone

from src.application.use_cases.compute_financial_analysis import (
    ComputeFinancialAnalysisUseCase,
)
from src.application.use_cases.compute_portfolio_risk import ComputePortfolioRiskUseCase
from src.application.use_cases.compute_portfolio_valuation import (
    ComputePortfolioValuationUseCase,
)
from src.application.use_cases.get_company_financials import GetCompanyFinancialsUseCase
from src.application.use_cases.manage_portfolio import AddHoldingUseCase, CreatePortfolioUseCase
from src.domain.entities.company import Company, Sector
from src.domain.entities.financial_statement import BalanceSheet, FiscalPeriodKey, Period
from src.domain.entities.market_quote import MarketQuote
from tests.unit.fakes import (
    FakeCompanyRepository,
    FakeDataProvider,
    FakeFinancialStatementRepository,
    FakePortfolioRepository,
)


def _setup(companies_and_sectors: dict[str, Sector]):
    company_repo = FakeCompanyRepository()
    for ticker, sector in companies_and_sectors.items():
        company_repo.save(
            Company(
                ticker=ticker, name=f"{ticker} Inc.", sector=sector,
                industry="X", exchange="NASDAQ", country="US",
            )
        )
    return company_repo


def test_two_equal_positions_give_expected_hhi_and_no_dominant_position() -> None:
    company_repo = _setup({"AAPL": Sector.TECHNOLOGY, "MSFT": Sector.TECHNOLOGY})
    statement_repo = FakeFinancialStatementRepository()
    portfolio_repo = FakePortfolioRepository()

    create = CreatePortfolioUseCase(portfolio_repo)
    add_holding = AddHoldingUseCase(portfolio_repo, company_repo)
    portfolio = create.execute("alice", "Test")
    # Equal dollar amounts: 10 shares @ $100 each = $1000 each position
    add_holding.execute(portfolio.portfolio_id, "AAPL", shares=10, cost_basis_per_share=100)
    add_holding.execute(portfolio.portfolio_id, "MSFT", shares=10, cost_basis_per_share=100)

    provider = FakeDataProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={
            "AAPL": MarketQuote(ticker="AAPL", price=100.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
            "MSFT": MarketQuote(ticker="MSFT", price=100.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        },
    )
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    compute_valuation = ComputePortfolioValuationUseCase(portfolio_repo, provider)
    compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)
    risk_use_case = ComputePortfolioRiskUseCase(compute_valuation, compute_analysis, company_repo)

    result = risk_use_case.execute(portfolio.portfolio_id)

    # Two exactly-equal positions: weight = 0.5 each
    # HHI = 0.5^2 + 0.5^2 = 0.5 (the maximum diversification for 2 positions)
    assert result.largest_position_weight == 0.5
    assert abs(result.herfindahl_index - 0.5) < 1e-9

    # Both in Technology -> 100% sector concentration in one sector
    assert len(result.sector_exposures) == 1
    assert result.sector_exposures[0].sector == "Technology"
    assert abs(result.sector_exposures[0].weight - 1.0) < 1e-9


def test_concentrated_single_position_gives_hhi_of_one() -> None:
    company_repo = _setup({"AAPL": Sector.TECHNOLOGY})
    statement_repo = FakeFinancialStatementRepository()
    portfolio_repo = FakePortfolioRepository()

    create = CreatePortfolioUseCase(portfolio_repo)
    add_holding = AddHoldingUseCase(portfolio_repo, company_repo)
    portfolio = create.execute("alice", "Test")
    add_holding.execute(portfolio.portfolio_id, "AAPL", shares=10, cost_basis_per_share=100)

    provider = FakeDataProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={
            "AAPL": MarketQuote(ticker="AAPL", price=100.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        },
    )
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    compute_valuation = ComputePortfolioValuationUseCase(portfolio_repo, provider)
    compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)
    risk_use_case = ComputePortfolioRiskUseCase(compute_valuation, compute_analysis, company_repo)

    result = risk_use_case.execute(portfolio.portfolio_id)

    assert result.largest_position_weight == 1.0
    assert result.herfindahl_index == 1.0  # maximum concentration


def test_weighted_average_leverage_computed_correctly() -> None:
    company_repo = _setup({"AAPL": Sector.TECHNOLOGY, "MSFT": Sector.TECHNOLOGY})
    statement_repo = FakeFinancialStatementRepository()
    portfolio_repo = FakePortfolioRepository()

    # AAPL: debt/equity = 2.0 (300/150), 75% of portfolio by market value
    statement_repo.save_balance_sheet(
        BalanceSheet(
            key=FiscalPeriodKey("AAPL", 2024, Period.ANNUAL),
            fiscal_date_ending=date(2024, 12, 31), reported_currency="USD",
            total_debt=300.0, total_equity=150.0,
        )
    )
    # MSFT: debt/equity = 0.5 (50/100), 25% of portfolio by market value
    statement_repo.save_balance_sheet(
        BalanceSheet(
            key=FiscalPeriodKey("MSFT", 2024, Period.ANNUAL),
            fiscal_date_ending=date(2024, 12, 31), reported_currency="USD",
            total_debt=50.0, total_equity=100.0,
        )
    )

    create = CreatePortfolioUseCase(portfolio_repo)
    add_holding = AddHoldingUseCase(portfolio_repo, company_repo)
    portfolio = create.execute("alice", "Test")
    # 30 shares @ $100 = $3000 (75% of $4000 total)
    add_holding.execute(portfolio.portfolio_id, "AAPL", shares=30, cost_basis_per_share=100)
    # 10 shares @ $100 = $1000 (25% of $4000 total)
    add_holding.execute(portfolio.portfolio_id, "MSFT", shares=10, cost_basis_per_share=100)

    provider = FakeDataProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={
            "AAPL": MarketQuote(ticker="AAPL", price=100.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
            "MSFT": MarketQuote(ticker="MSFT", price=100.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        },
    )
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    compute_valuation = ComputePortfolioValuationUseCase(portfolio_repo, provider)
    compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)
    risk_use_case = ComputePortfolioRiskUseCase(compute_valuation, compute_analysis, company_repo)

    result = risk_use_case.execute(portfolio.portfolio_id)

    # Weighted avg D/E = 2.0*0.75 + 0.5*0.25 = 1.5 + 0.125 = 1.625
    assert abs(result.weighted_avg_debt_to_equity - 1.625) < 1e-9
    assert result.excluded_from_leverage_calc == []


def test_holding_missing_balance_sheet_is_excluded_not_silently_dropped() -> None:
    company_repo = _setup({"AAPL": Sector.TECHNOLOGY})
    statement_repo = FakeFinancialStatementRepository()  # no balance sheet saved
    portfolio_repo = FakePortfolioRepository()

    create = CreatePortfolioUseCase(portfolio_repo)
    add_holding = AddHoldingUseCase(portfolio_repo, company_repo)
    portfolio = create.execute("alice", "Test")
    add_holding.execute(portfolio.portfolio_id, "AAPL", shares=10, cost_basis_per_share=100)

    provider = FakeDataProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={
            "AAPL": MarketQuote(ticker="AAPL", price=100.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        },
    )
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    compute_valuation = ComputePortfolioValuationUseCase(portfolio_repo, provider)
    compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)
    risk_use_case = ComputePortfolioRiskUseCase(compute_valuation, compute_analysis, company_repo)

    result = risk_use_case.execute(portfolio.portfolio_id)

    assert result.weighted_avg_debt_to_equity is None
    assert result.excluded_from_leverage_calc == ["AAPL"]


# ---- Real risk analysis: volatility / correlation / VaR ----

from src.domain.entities.market_quote import PriceBar
from src.domain.services.portfolio_risk_math import compute_simple_returns
import statistics


class _PricedProvider(FakeDataProvider):
    """Extends the standard fake with get_daily_closes, keyed per
    ticker, for the volatility tests below."""

    def __init__(self, *args, closes_by_ticker=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._closes_by_ticker = closes_by_ticker or {}

    def get_daily_closes(self, ticker: str, limit: int = 30):
        closes = self._closes_by_ticker.get(ticker, [])
        bars = [
            PriceBar(bar_date=date(2026, 1, 1), close=c)  # dates unused by the pure math
            for c in closes
        ]
        return bars[:limit]


# 21 prices (most-recent-first) yielding exactly 20 alternating
# +-1% returns. Sample variance of that returns series is EXACTLY
# 0.002/19 = 0.00010526315789... — verified independently via
# statistics.variance before being hard-coded here.
_ALTERNATING_CLOSES = [
    99.90004498800211, 100.90913635151728, 99.91003599160126, 100.9192282743447,
    99.9200279944007, 100.92932120646535, 99.93002099650035, 100.93941514798014,
    99.94001499800014, 100.94951009899003, 99.95000999900003, 100.959606059596,
    99.9600059996, 100.969703029899, 99.97000299989999, 100.97980100999999,
    99.98000099999999, 100.98989999999999, 99.99, 101.0, 100.0,
]
_EXPECTED_VARIANCE = 0.002 / 19
_EXPECTED_DAILY_VOL = _EXPECTED_VARIANCE ** 0.5


def test_backward_compatible_without_data_provider_volatility_fields_all_none() -> None:
    company_repo = _setup({"AAPL": Sector.TECHNOLOGY})
    statement_repo = FakeFinancialStatementRepository()
    portfolio_repo = FakePortfolioRepository()
    create = CreatePortfolioUseCase(portfolio_repo)
    add_holding = AddHoldingUseCase(portfolio_repo, company_repo)
    portfolio = create.execute("alice", "Test")
    add_holding.execute(portfolio.portfolio_id, "AAPL", shares=10, cost_basis_per_share=100)

    provider = FakeDataProvider(company=company_repo.get_by_ticker("AAPL"),
                                  quotes_by_ticker={"AAPL": MarketQuote(
                                      ticker="AAPL", price=100.0, market_cap=1e9,
                                      as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))})
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    compute_valuation = ComputePortfolioValuationUseCase(portfolio_repo, provider)
    compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)
    # No data_provider passed -> exactly the pre-existing constructor signature
    use_case = ComputePortfolioRiskUseCase(compute_valuation, compute_analysis, company_repo)

    result = use_case.execute(portfolio.portfolio_id)

    assert result.portfolio_daily_volatility is None
    assert result.portfolio_annualized_volatility is None
    assert result.parametric_var_95_1day_dollar is None
    assert result.volatility_covered_weight is None
    assert result.pairwise_correlations == []
    assert result.excluded_from_volatility_calc == []
    # Concentration/leverage still work exactly as before
    assert result.largest_position_weight == 1.0


def test_single_position_volatility_matches_independently_verified_sample_variance() -> None:
    company_repo = _setup({"AAPL": Sector.TECHNOLOGY})
    statement_repo = FakeFinancialStatementRepository()
    portfolio_repo = FakePortfolioRepository()
    create = CreatePortfolioUseCase(portfolio_repo)
    add_holding = AddHoldingUseCase(portfolio_repo, company_repo)
    portfolio = create.execute("alice", "Test")
    add_holding.execute(portfolio.portfolio_id, "AAPL", shares=10, cost_basis_per_share=100)

    provider = _PricedProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={"AAPL": MarketQuote(ticker="AAPL", price=100.0, market_cap=1e9,
                                                as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))},
        closes_by_ticker={"AAPL": _ALTERNATING_CLOSES},
    )
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    compute_valuation = ComputePortfolioValuationUseCase(portfolio_repo, provider)
    compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)
    use_case = ComputePortfolioRiskUseCase(compute_valuation, compute_analysis, company_repo, provider)

    result = use_case.execute(portfolio.portfolio_id)

    assert result.volatility_lookback_days_used == 20
    assert abs(result.portfolio_daily_volatility - _EXPECTED_DAILY_VOL) < 1e-9
    assert abs(result.portfolio_annualized_volatility - _EXPECTED_DAILY_VOL * (252 ** 0.5)) < 1e-8
    assert result.volatility_covered_weight == 1.0  # single position, full weight
    # total_market_value = 10 shares * $100 current price = $1000
    expected_var = 1000.0 * _EXPECTED_DAILY_VOL * 1.645
    assert abs(result.parametric_var_95_1day_dollar - expected_var) < 1e-6
    assert result.excluded_from_volatility_calc == []
    assert result.pairwise_correlations == []  # only one ticker — no pairs to correlate


def test_ticker_with_insufficient_history_excluded_covered_weight_below_one() -> None:
    company_repo = _setup({"AAPL": Sector.TECHNOLOGY, "MSFT": Sector.TECHNOLOGY})
    statement_repo = FakeFinancialStatementRepository()
    portfolio_repo = FakePortfolioRepository()
    create = CreatePortfolioUseCase(portfolio_repo)
    add_holding = AddHoldingUseCase(portfolio_repo, company_repo)
    portfolio = create.execute("alice", "Test")
    # Equal dollar weights: 10 sh @ $100 each
    add_holding.execute(portfolio.portfolio_id, "AAPL", shares=10, cost_basis_per_share=100)
    add_holding.execute(portfolio.portfolio_id, "MSFT", shares=10, cost_basis_per_share=100)

    provider = _PricedProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={
            "AAPL": MarketQuote(ticker="AAPL", price=100.0, market_cap=1e9,
                                  as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
            "MSFT": MarketQuote(ticker="MSFT", price=100.0, market_cap=1e9,
                                  as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        },
        closes_by_ticker={
            "AAPL": _ALTERNATING_CLOSES,  # 21 closes -> 20 returns, enough
            "MSFT": [100.0, 99.0, 98.0],  # only 3 closes -> 2 returns, too short
        },
    )
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    compute_valuation = ComputePortfolioValuationUseCase(portfolio_repo, provider)
    compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)
    use_case = ComputePortfolioRiskUseCase(compute_valuation, compute_analysis, company_repo, provider)

    result = use_case.execute(portfolio.portfolio_id)

    assert result.excluded_from_volatility_calc == ["MSFT"]
    assert abs(result.volatility_covered_weight - 0.5) < 1e-9  # only AAPL's 50% weight covered
    # With only AAPL surviving, normalized weight is 1.0 -> same daily vol as the single-asset case
    assert abs(result.portfolio_daily_volatility - _EXPECTED_DAILY_VOL) < 1e-9


def test_pairwise_correlation_reported_for_two_surviving_tickers() -> None:
    company_repo = _setup({"AAPL": Sector.TECHNOLOGY, "MSFT": Sector.TECHNOLOGY})
    statement_repo = FakeFinancialStatementRepository()
    portfolio_repo = FakePortfolioRepository()
    create = CreatePortfolioUseCase(portfolio_repo)
    add_holding = AddHoldingUseCase(portfolio_repo, company_repo)
    portfolio = create.execute("alice", "Test")
    add_holding.execute(portfolio.portfolio_id, "AAPL", shares=10, cost_basis_per_share=100)
    add_holding.execute(portfolio.portfolio_id, "MSFT", shares=10, cost_basis_per_share=100)

    # MSFT given the IDENTICAL close series as AAPL -> perfectly
    # correlated (correlation == 1.0), same hand-verified guarantee
    # proven in the pure-math tests, now checked through the real
    # use case wiring.
    provider = _PricedProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={
            "AAPL": MarketQuote(ticker="AAPL", price=100.0, market_cap=1e9,
                                  as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
            "MSFT": MarketQuote(ticker="MSFT", price=100.0, market_cap=1e9,
                                  as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        },
        closes_by_ticker={"AAPL": _ALTERNATING_CLOSES, "MSFT": _ALTERNATING_CLOSES},
    )
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    compute_valuation = ComputePortfolioValuationUseCase(portfolio_repo, provider)
    compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)
    use_case = ComputePortfolioRiskUseCase(compute_valuation, compute_analysis, company_repo, provider)

    result = use_case.execute(portfolio.portfolio_id)

    assert len(result.pairwise_correlations) == 1
    pair = result.pairwise_correlations[0]
    assert {pair.ticker_a, pair.ticker_b} == {"AAPL", "MSFT"}
    assert abs(pair.correlation - 1.0) < 1e-9
