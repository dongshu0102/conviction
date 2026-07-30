from __future__ import annotations

from datetime import date

import pytest

from src.application.use_cases.generate_company_research import (
    GenerateCompanyResearchUseCase,
    NoFinancialDataError,
)
from src.application.use_cases.get_company_financials import (
    CompanyNotFoundError,
    GetCompanyFinancialsUseCase,
)
from src.domain.entities.company import Company, Sector
from src.domain.entities.financial_statement import FiscalPeriodKey, IncomeStatement, Period
from tests.unit.fakes import (
    FakeCompanyRepository,
    FakeFinancialStatementRepository,
    FakeResearchGenerator,
    FakeResearchReportRepository,
)


def _company() -> Company:
    return Company(
        ticker="AAPL", name="Apple Inc.", sector=Sector.TECHNOLOGY,
        industry="Consumer Electronics", exchange="NASDAQ", country="US",
    )


def _build_use_case(company_repo, statement_repo, generator):
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    report_repo = FakeResearchReportRepository()
    return (
        GenerateCompanyResearchUseCase(get_financials, generator, report_repo),
        report_repo,
    )


def test_raises_when_company_does_not_exist() -> None:
    use_case, _ = _build_use_case(
        FakeCompanyRepository(), FakeFinancialStatementRepository(), FakeResearchGenerator()
    )
    with pytest.raises(CompanyNotFoundError):
        use_case.execute("NONEXISTENT")


def test_raises_when_company_exists_but_has_no_financial_data() -> None:
    company_repo = FakeCompanyRepository()
    company_repo.save(_company())
    use_case, _ = _build_use_case(
        company_repo, FakeFinancialStatementRepository(), FakeResearchGenerator()
    )
    with pytest.raises(NoFinancialDataError):
        use_case.execute("AAPL")


def test_generator_is_never_called_without_financial_data() -> None:
    """The core grounding guarantee: no financial data means the LLM
    adapter must never be reached at all."""
    company_repo = FakeCompanyRepository()
    company_repo.save(_company())
    generator = FakeResearchGenerator()
    use_case, _ = _build_use_case(company_repo, FakeFinancialStatementRepository(), generator)

    with pytest.raises(NoFinancialDataError):
        use_case.execute("AAPL")

    assert generator.received_financials is None


def test_generator_receives_real_ingested_financials() -> None:
    company_repo = FakeCompanyRepository()
    company_repo.save(_company())
    statement_repo = FakeFinancialStatementRepository()
    statement_repo.save_income_statement(
        IncomeStatement(
            key=FiscalPeriodKey("AAPL", 2024, Period.ANNUAL),
            fiscal_date_ending=date(2024, 9, 30),
            reported_currency="USD",
            revenue=391_035_000_000,
        )
    )
    generator = FakeResearchGenerator()
    use_case, report_repo = _build_use_case(company_repo, statement_repo, generator)

    report = use_case.execute("aapl")

    assert generator.received_financials is not None
    assert generator.received_financials.income_statements[0].revenue == 391_035_000_000
    assert report.ticker == "AAPL"
    assert report.grounded_fiscal_year == 2024
    assert report_repo.get_latest("AAPL") is not None
