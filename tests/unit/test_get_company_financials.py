from __future__ import annotations

import pytest

from src.application.use_cases.get_company_financials import (
    CompanyNotFoundError,
    GetCompanyFinancialsUseCase,
)
from src.domain.entities.company import Company, Sector
from tests.unit.fakes import FakeCompanyRepository, FakeFinancialStatementRepository


def test_raises_when_company_not_found() -> None:
    use_case = GetCompanyFinancialsUseCase(
        FakeCompanyRepository(), FakeFinancialStatementRepository()
    )

    with pytest.raises(CompanyNotFoundError):
        use_case.execute("NONEXISTENT")


def test_returns_company_and_empty_statements_when_none_ingested() -> None:
    company_repo = FakeCompanyRepository()
    company_repo.save(
        Company(
            ticker="MSFT",
            name="Microsoft Corporation",
            sector=Sector.TECHNOLOGY,
            industry="Software",
            exchange="NASDAQ",
            country="US",
        )
    )
    use_case = GetCompanyFinancialsUseCase(company_repo, FakeFinancialStatementRepository())

    result = use_case.execute("msft")

    assert result.company.ticker == "MSFT"
    assert result.income_statements == []
    assert result.balance_sheets == []
    assert result.cash_flow_statements == []
