from __future__ import annotations

from datetime import date

from src.application.use_cases.ingest_company_data import IngestCompanyDataUseCase
from src.domain.entities.company import Company, Sector
from src.domain.entities.financial_statement import (
    FiscalPeriodKey,
    IncomeStatement,
    Period,
)
from tests.unit.fakes import (
    FakeCompanyRepository,
    FakeDataProvider,
    FakeFinancialStatementRepository,
)


def _sample_company() -> Company:
    return Company(
        ticker="aapl",  # deliberately lowercase to test normalization
        name="Apple Inc.",
        sector=Sector.TECHNOLOGY,
        industry="Consumer Electronics",
        exchange="NASDAQ",
        country="US",
    )


def test_ingest_saves_company_profile() -> None:
    company_repo = FakeCompanyRepository()
    statement_repo = FakeFinancialStatementRepository()
    provider = FakeDataProvider(company=_sample_company())
    use_case = IngestCompanyDataUseCase(provider, company_repo, statement_repo)

    use_case.execute("AAPL")

    saved = company_repo.get_by_ticker("AAPL")
    assert saved is not None
    assert saved.name == "Apple Inc."
    assert saved.ticker == "AAPL"  # normalized


def test_ingest_saves_income_statements_and_counts_result() -> None:
    company_repo = FakeCompanyRepository()
    statement_repo = FakeFinancialStatementRepository()
    income_statement = IncomeStatement(
        key=FiscalPeriodKey("AAPL", 2024, Period.ANNUAL),
        fiscal_date_ending=date(2024, 9, 30),
        reported_currency="USD",
        revenue=391_035_000_000,
        net_income=93_736_000_000,
    )
    provider = FakeDataProvider(
        company=_sample_company(), income_statements=[income_statement]
    )
    use_case = IngestCompanyDataUseCase(provider, company_repo, statement_repo)

    result = use_case.execute("AAPL", years=1)

    assert result.income_statements_ingested == 1
    assert result.balance_sheets_ingested == 0
    stored = statement_repo.get_income_statements("AAPL", Period.ANNUAL, limit=1)
    assert stored[0].revenue == 391_035_000_000


def test_ticker_is_normalized_regardless_of_input_case() -> None:
    company_repo = FakeCompanyRepository()
    statement_repo = FakeFinancialStatementRepository()
    provider = FakeDataProvider(company=_sample_company())
    use_case = IngestCompanyDataUseCase(provider, company_repo, statement_repo)

    result = use_case.execute("  aapl  ")

    assert result.ticker == "AAPL"
