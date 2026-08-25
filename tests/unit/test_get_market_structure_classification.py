from datetime import date

import pytest

from src.application.use_cases.get_company_financials import (
    CompanyNotFoundError,
    GetCompanyFinancialsUseCase,
)
from src.application.use_cases.get_market_structure_classification import (
    GetMarketStructureClassificationUseCase,
)
from src.domain.entities.company import Company, Sector
from src.domain.entities.financial_statement import FiscalPeriodKey, IncomeStatement, Period
from tests.unit.fakes import FakeCompanyRepository, FakeFinancialStatementRepository


class FakeMarketStructureNarrativeGenerator:
    def __init__(self, narrative="Test narrative", raise_error=None):
        self._narrative = narrative
        self._raise_error = raise_error
        self.received_calls = []

    def generate(self, ticker, industry, category, hhi, company_share, peer_count, peer_tickers):
        self.received_calls.append(
            (ticker, industry, category, hhi, company_share, peer_count, tuple(peer_tickers))
        )
        if self._raise_error is not None:
            raise self._raise_error
        from src.application.interfaces.market_structure_narrative_generator import (
            MarketStructureNarrativeResult,
        )
        return MarketStructureNarrativeResult(narrative=self._narrative, model_used="fake-model")


def _company(ticker, industry="Semiconductors") -> Company:
    return Company(
        ticker=ticker, name=f"{ticker} Inc.", sector=Sector.TECHNOLOGY, industry=industry,
        exchange="NASDAQ", country="US",
    )


def _income(ticker, revenue, year=2024) -> IncomeStatement:
    return IncomeStatement(
        key=FiscalPeriodKey(ticker, year, Period.ANNUAL), fiscal_date_ending=date(year, 12, 31),
        reported_currency="USD", revenue=revenue,
    )


def _build():
    company_repo = FakeCompanyRepository()
    statement_repo = FakeFinancialStatementRepository()
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    narrative_gen = FakeMarketStructureNarrativeGenerator()
    use_case = GetMarketStructureClassificationUseCase(company_repo, get_financials, narrative_gen)
    return use_case, company_repo, statement_repo, narrative_gen


def test_raises_when_company_does_not_exist() -> None:
    use_case, _, _, _ = _build()
    with pytest.raises(CompanyNotFoundError):
        use_case.execute("NONEXISTENT")


def test_computes_a_real_classification_from_genuine_industry_peers() -> None:
    use_case, company_repo, statement_repo, narrative_gen = _build()
    company_repo.save(_company("NVDA"))
    company_repo.save(_company("AMD"))
    company_repo.save(_company("INTC"))
    statement_repo.save_income_statement(_income("NVDA", 900.0))
    statement_repo.save_income_statement(_income("AMD", 50.0))
    statement_repo.save_income_statement(_income("INTC", 50.0))

    result = use_case.execute("NVDA")

    assert result.industry == "Semiconductors"
    assert result.peer_count == 3
    assert result.company_market_share == pytest.approx(0.9)
    assert result.category == "Monopoly"  # NVDA at 90% share, matching the earlier hand-verified case


def test_excludes_companies_in_a_genuinely_different_industry() -> None:
    use_case, company_repo, statement_repo, narrative_gen = _build()
    company_repo.save(_company("NVDA", industry="Semiconductors"))
    company_repo.save(_company("AAPL", industry="Consumer Electronics"))
    statement_repo.save_income_statement(_income("NVDA", 100.0))
    statement_repo.save_income_statement(_income("AAPL", 900.0))

    result = use_case.execute("NVDA")

    # AAPL's own, much larger revenue must never dilute NVDA's real
    # share -- it's in a genuinely different, real industry.
    assert result.peer_count == 1
    assert result.company_market_share == pytest.approx(1.0)


def test_a_peer_with_no_ingested_revenue_is_honestly_excluded_not_treated_as_zero() -> None:
    use_case, company_repo, statement_repo, narrative_gen = _build()
    company_repo.save(_company("NVDA"))
    company_repo.save(_company("AMD"))  # no income statement saved for AMD at all
    statement_repo.save_income_statement(_income("NVDA", 100.0))

    result = use_case.execute("NVDA")

    assert result.peer_count == 1  # AMD genuinely excluded, not counted as a 0-revenue peer
    assert result.company_market_share == pytest.approx(1.0)


def test_the_narrative_generator_receives_the_real_deterministic_values() -> None:
    use_case, company_repo, statement_repo, narrative_gen = _build()
    company_repo.save(_company("NVDA"))
    company_repo.save(_company("AMD"))
    statement_repo.save_income_statement(_income("NVDA", 60.0))
    statement_repo.save_income_statement(_income("AMD", 40.0))

    result = use_case.execute("NVDA")

    assert len(narrative_gen.received_calls) == 1
    ticker, industry, category, hhi, share, peer_count, peer_tickers = narrative_gen.received_calls[0]
    assert ticker == "NVDA"
    assert category == result.category
    assert hhi == result.hhi
    assert share == result.company_market_share
    assert peer_count == result.peer_count
    assert peer_tickers == ("AMD",)  # the target ticker itself is excluded from its own peer list


def test_honestly_unclassifiable_when_this_company_is_the_only_ingested_peer_in_its_industry() -> None:
    use_case, company_repo, statement_repo, narrative_gen = _build()
    company_repo.save(_company("NVDA"))
    statement_repo.save_income_statement(_income("NVDA", 100.0))

    result = use_case.execute("NVDA")

    assert result.category == "Unclassifiable (insufficient ingested peer data)"
