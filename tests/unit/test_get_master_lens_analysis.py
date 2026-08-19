from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from src.application.use_cases.compute_financial_analysis import ComputeFinancialAnalysisUseCase
from src.application.use_cases.compute_valuation import ComputeValuationUseCase
from src.application.use_cases.get_company_financials import (
    CompanyNotFoundError,
    GetCompanyFinancialsUseCase,
)
from src.application.use_cases.get_master_lens_analysis import GetMasterLensAnalysisUseCase
from src.domain.entities.company import Company, Sector
from src.domain.entities.financial_statement import (
    BalanceSheet, CashFlowStatement, FiscalPeriodKey, IncomeStatement, Period,
)
from src.domain.entities.market_quote import MarketQuote
from tests.unit.fakes import (
    FakeCompanyRepository,
    FakeDataProvider,
    FakeFinancialStatementRepository,
    FakeMasterLensNarrativeGenerator,
)


def _company() -> Company:
    return Company(
        ticker="AAPL", name="Apple Inc.", sector=Sector.TECHNOLOGY,
        industry="Consumer Electronics", exchange="NASDAQ", country="US",
    )


def _income(year: int, revenue: float, net_income: float) -> IncomeStatement:
    return IncomeStatement(
        key=FiscalPeriodKey("AAPL", year, Period.ANNUAL), fiscal_date_ending=date(year, 9, 30),
        reported_currency="USD", revenue=revenue, gross_profit=revenue * 0.5,
        operating_income=revenue * 0.25, net_income=net_income, ebitda=revenue * 0.3,
    )


def _balance(year: int) -> BalanceSheet:
    return BalanceSheet(
        key=FiscalPeriodKey("AAPL", year, Period.ANNUAL), fiscal_date_ending=date(year, 9, 30),
        reported_currency="USD", total_assets=1_000_000, total_current_assets=400_000,
        cash_and_equivalents=200_000, total_liabilities=400_000, total_current_liabilities=200_000,
        total_debt=200_000, total_equity=600_000,
    )


def _cashflow(year: int) -> CashFlowStatement:
    return CashFlowStatement(
        key=FiscalPeriodKey("AAPL", year, Period.ANNUAL), fiscal_date_ending=date(year, 9, 30),
        reported_currency="USD", operating_cash_flow=300_000, free_cash_flow=200_000,
    )


def _build_use_case(company_repo, statement_repo, data_provider, generator):
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)
    compute_valuation = ComputeValuationUseCase(get_financials, data_provider)
    return GetMasterLensAnalysisUseCase(compute_analysis, compute_valuation, generator)


def _quote() -> MarketQuote:
    return MarketQuote(ticker="AAPL", price=150.0, market_cap=2_000_000, as_of=datetime.now(timezone.utc))


def test_raises_when_company_does_not_exist() -> None:
    use_case = _build_use_case(
        FakeCompanyRepository(), FakeFinancialStatementRepository(),
        FakeDataProvider(_company()), FakeMasterLensNarrativeGenerator(),
    )
    with pytest.raises(CompanyNotFoundError):
        use_case.execute("NONEXISTENT")


def test_produces_all_ten_lenses_in_the_documented_order() -> None:
    company_repo = FakeCompanyRepository()
    company_repo.save(_company())
    statement_repo = FakeFinancialStatementRepository()
    statement_repo.save_income_statement(_income(2024, 1_000_000, 200_000))
    statement_repo.save_balance_sheet(_balance(2024))
    statement_repo.save_cash_flow_statement(_cashflow(2024))
    data_provider = FakeDataProvider(_company(), quote=_quote())
    generator = FakeMasterLensNarrativeGenerator()
    use_case = _build_use_case(company_repo, statement_repo, data_provider, generator)

    result = use_case.execute("aapl")

    assert result.ticker == "AAPL"
    assert len(result.results) == 10
    expected_order = [
        "Buffett", "Munger", "Graham", "Lynch", "Dalio",
        "Marks", "Klarman", "Fisher", "Templeton", "Soros",
    ]
    assert [r.master_name for r in result.results] == expected_order


def test_narrative_generator_receives_the_real_deterministic_scores() -> None:
    """The core grounding guarantee: the narrative for each master must
    reflect the score that was actually, deterministically computed --
    never a value the LLM adapter invents independently."""
    company_repo = FakeCompanyRepository()
    company_repo.save(_company())
    statement_repo = FakeFinancialStatementRepository()
    statement_repo.save_income_statement(_income(2024, 1_000_000, 200_000))
    statement_repo.save_balance_sheet(_balance(2024))
    statement_repo.save_cash_flow_statement(_cashflow(2024))
    data_provider = FakeDataProvider(_company(), quote=_quote())
    generator = FakeMasterLensNarrativeGenerator()
    use_case = _build_use_case(company_repo, statement_repo, data_provider, generator)

    result = use_case.execute("AAPL")

    assert generator.received_scored_inputs is not None
    munger_result = next(r for r in result.results if r.master_name == "Munger")
    munger_input = next(s for s in generator.received_scored_inputs if s.master_name == "Munger")
    assert munger_result.score == munger_input.score
    assert munger_result.score_basis in munger_result.narrative


def test_degrades_honestly_when_valuation_is_unavailable() -> None:
    """Valuation-grounded lenses (Graham, Marks, Templeton) must report
    None, not fail the entire analysis, when a live quote can't be
    fetched -- the other seven lenses don't need valuation at all."""
    company_repo = FakeCompanyRepository()
    company_repo.save(_company())
    statement_repo = FakeFinancialStatementRepository()
    statement_repo.save_income_statement(_income(2022, 800_000, 160_000))
    statement_repo.save_income_statement(_income(2023, 900_000, 180_000))
    statement_repo.save_income_statement(_income(2024, 1_000_000, 200_000))
    statement_repo.save_balance_sheet(_balance(2024))
    statement_repo.save_cash_flow_statement(_cashflow(2024))
    data_provider = FakeDataProvider(_company())  # no quote configured -- get_quote will raise
    generator = FakeMasterLensNarrativeGenerator()
    use_case = _build_use_case(company_repo, statement_repo, data_provider, generator)

    result = use_case.execute("AAPL")

    valuation_grounded = {"Graham", "Marks", "Templeton"}
    for r in result.results:
        if r.master_name in valuation_grounded:
            assert r.score is None
        else:
            assert r.score is not None  # these lenses never depended on the missing quote


def test_propagates_narrative_generation_failure() -> None:
    company_repo = FakeCompanyRepository()
    company_repo.save(_company())
    statement_repo = FakeFinancialStatementRepository()
    statement_repo.save_income_statement(_income(2024, 1_000_000, 200_000))
    statement_repo.save_balance_sheet(_balance(2024))
    statement_repo.save_cash_flow_statement(_cashflow(2024))
    data_provider = FakeDataProvider(_company(), quote=_quote())
    generator = FakeMasterLensNarrativeGenerator(fail=True)
    use_case = _build_use_case(company_repo, statement_repo, data_provider, generator)

    from src.application.interfaces.master_lens_narrative_generator import MasterLensGenerationError
    with pytest.raises(MasterLensGenerationError):
        use_case.execute("AAPL")
