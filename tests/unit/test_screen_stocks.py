from __future__ import annotations

from datetime import date, datetime, timezone

from src.application.use_cases.compute_financial_analysis import (
    ComputeFinancialAnalysisUseCase,
)
from src.application.use_cases.compute_valuation import ComputeValuationUseCase
from src.application.use_cases.get_company_financials import GetCompanyFinancialsUseCase
from src.application.use_cases.screen_stocks import ScreenStocksUseCase, _ranks
from src.domain.entities.company import Company, Sector
from src.domain.entities.financial_statement import (
    BalanceSheet,
    FiscalPeriodKey,
    IncomeStatement,
    Period,
)
from src.domain.entities.market_quote import MarketQuote
from tests.unit.fakes import FakeCompanyRepository, FakeDataProvider, FakeFinancialStatementRepository


# --- Pure ranking function — exact, hand-verified ---------------------------

def test_ranks_ascending_lowest_value_gets_rank_one() -> None:
    ranks = _ranks([30.0, 10.0, 20.0], ascending=True)
    # 10.0 is smallest -> rank 1; 20.0 -> rank 2; 30.0 -> rank 3
    assert ranks == [3.0, 1.0, 2.0]


def test_ranks_descending_highest_value_gets_rank_one() -> None:
    ranks = _ranks([30.0, 10.0, 20.0], ascending=False)
    # 30.0 is largest -> rank 1 (best) when higher-is-better
    assert ranks == [1.0, 3.0, 2.0]


def test_ranks_handles_single_value() -> None:
    assert _ranks([42.0], ascending=True) == [1.0]


# --- Integration through the real valuation + analysis pipeline -------------

def _company(ticker: str) -> Company:
    return Company(
        ticker=ticker, name=f"{ticker} Inc.", sector=Sector.TECHNOLOGY,
        industry="Software", exchange="NASDAQ", country="US",
    )


def _build_use_case():
    company_repo = FakeCompanyRepository()
    statement_repo = FakeFinancialStatementRepository()
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    return company_repo, statement_repo, get_financials


def test_negative_pe_company_is_excluded_not_ranked() -> None:
    company_repo, statement_repo, get_financials = _build_use_case()
    company_repo.save(_company("LOSS"))
    statement_repo.save_income_statement(
        IncomeStatement(
            key=FiscalPeriodKey("LOSS", 2024, Period.ANNUAL),
            fiscal_date_ending=date(2024, 12, 31), reported_currency="USD",
            revenue=1000.0, net_income=-50.0,  # a loss — negative P/E territory
        )
    )
    provider = FakeDataProvider(
        company=_company("LOSS"),
        quotes_by_ticker={"LOSS": MarketQuote(ticker="LOSS", price=10.0, market_cap=500.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))},
    )
    compute_valuation = ComputeValuationUseCase(get_financials, provider)
    compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)
    use_case = ScreenStocksUseCase(compute_valuation, compute_analysis)

    result = use_case.execute(["LOSS"])

    assert result.results == []
    assert "LOSS" in result.excluded


def test_dominant_company_ranks_above_weaker_one() -> None:
    """WINNER beats LOSER on every single metric (cheaper valuation,
    higher ROE, higher margin, lower leverage) — its composite_score
    must be strictly lower (better) regardless of the exact weighting
    formula, since it dominates on every input."""
    company_repo, statement_repo, get_financials = _build_use_case()
    company_repo.save(_company("WINNER"))
    company_repo.save(_company("LOSER"))

    statement_repo.save_income_statement(
        IncomeStatement(
            key=FiscalPeriodKey("WINNER", 2024, Period.ANNUAL),
            fiscal_date_ending=date(2024, 12, 31), reported_currency="USD",
            revenue=1000.0, net_income=200.0, ebitda=300.0,
        )
    )
    statement_repo.save_balance_sheet(
        BalanceSheet(
            key=FiscalPeriodKey("WINNER", 2024, Period.ANNUAL),
            fiscal_date_ending=date(2024, 12, 31), reported_currency="USD",
            total_equity=1000.0, total_debt=200.0, cash_and_equivalents=100.0,
        )
    )
    statement_repo.save_income_statement(
        IncomeStatement(
            key=FiscalPeriodKey("LOSER", 2024, Period.ANNUAL),
            fiscal_date_ending=date(2024, 12, 31), reported_currency="USD",
            revenue=1000.0, net_income=20.0, ebitda=40.0,
        )
    )
    statement_repo.save_balance_sheet(
        BalanceSheet(
            key=FiscalPeriodKey("LOSER", 2024, Period.ANNUAL),
            fiscal_date_ending=date(2024, 12, 31), reported_currency="USD",
            total_equity=200.0, total_debt=800.0, cash_and_equivalents=10.0,
        )
    )

    provider = FakeDataProvider(
        company=_company("WINNER"),
        quotes_by_ticker={
            # WINNER: cheap (low P/E, P/S, EV/EBITDA) relative to its own fundamentals
            "WINNER": MarketQuote(ticker="WINNER", price=10.0, market_cap=1000.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
            # LOSER: expensive relative to its (much weaker) fundamentals
            "LOSER": MarketQuote(ticker="LOSER", price=100.0, market_cap=5000.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        },
    )
    compute_valuation = ComputeValuationUseCase(get_financials, provider)
    compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)
    use_case = ScreenStocksUseCase(compute_valuation, compute_analysis)

    result = use_case.execute(["WINNER", "LOSER"])

    assert [s.ticker for s in result.results] == ["WINNER", "LOSER"]
    assert result.results[0].composite_score < result.results[1].composite_score
