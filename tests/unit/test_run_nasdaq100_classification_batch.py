from datetime import date

import pytest

from src.application.interfaces.nasdaq100_classifier import (
    Nasdaq100ClassificationError,
    Nasdaq100ClassificationResult,
)
from src.application.use_cases.run_nasdaq100_classification_batch import (
    RunNasdaq100ClassificationBatchUseCase,
)
from src.application.use_cases.get_company_financials import GetCompanyFinancialsUseCase
from src.domain.entities.company import Company, Sector
from src.domain.entities.financial_statement import FiscalPeriodKey, IncomeStatement, Period
from tests.unit.fakes import FakeCompanyRepository, FakeFinancialStatementRepository, FakePortfolioRepository


class FakeIndexMembershipRepository:
    def __init__(self, memberships: dict[str, list[str]] | None = None):
        self._memberships = memberships or {}

    def save_memberships(self, ticker, index_names):
        self._memberships[ticker] = index_names

    def get_memberships_for_tickers(self, tickers):
        return {t: self._memberships[t] for t in tickers if t in self._memberships}


class FakeNasdaq100ClassificationRepository:
    def __init__(self):
        self.saved_batches = []

    def save_batch(self, results):
        self.saved_batches.append(results)

    def get_all(self, **kwargs):
        return self.saved_batches[-1] if self.saved_batches else []


class FakeComputeFinancialAnalysis:
    def __init__(self, revenue_growth_by_ticker: dict[str, float] | None = None, raise_for: set | None = None):
        self._growth = revenue_growth_by_ticker or {}
        self._raise_for = raise_for or set()

    def execute(self, ticker, years=5):
        if ticker in self._raise_for:
            raise RuntimeError(f"no financial data for {ticker}")
        from src.domain.entities.financial_analysis import CompanyFinancialAnalysis, YearlyRatios
        growth = self._growth.get(ticker)
        ratios = [YearlyRatios(
            fiscal_year=2024, revenue_growth_yoy=growth,
            gross_margin=None, operating_margin=None, net_margin=None, free_cash_flow_margin=None,
            return_on_equity=None, return_on_assets=None, debt_to_equity=None, current_ratio=None,
        )] if growth is not None else []
        return CompanyFinancialAnalysis(ticker=ticker, yearly_ratios=ratios)


class FakeComputeValuation:
    def __init__(self, market_cap_by_ticker: dict[str, float] | None = None, raise_for: set | None = None):
        self._market_cap = market_cap_by_ticker or {}
        self._raise_for = raise_for or set()

    def execute(self, ticker):
        if ticker in self._raise_for:
            raise RuntimeError(f"no valuation data for {ticker}")
        from datetime import datetime, timezone
        from src.domain.entities.valuation_snapshot import ValuationSnapshot
        return ValuationSnapshot(
            ticker=ticker, as_of=datetime.now(timezone.utc), price=100.0,
            market_cap=self._market_cap.get(ticker, 0.0), enterprise_value=None,
            fundamentals_fiscal_year=2024, price_to_earnings=None, price_to_sales=None,
            price_to_book=None, price_to_free_cash_flow=None, ev_to_ebitda=None,
        )


class FakeNasdaq100Classifier:
    def __init__(self, results_by_ticker: dict | None = None, raise_for: set | None = None):
        self._results = results_by_ticker or {}
        self._raise_for = raise_for or set()
        self.classify_calls = []

    def classify(self, ticker, name, industry, description):
        self.classify_calls.append(ticker)
        if ticker in self._raise_for:
            raise Nasdaq100ClassificationError(f"LLM failed for {ticker}")
        return self._results.get(ticker, Nasdaq100ClassificationResult(
            value_chain_position="Midstream — Design/Development",
            business_model="Subscription/SaaS", model_used="fake-model",
        ))


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


def _build(
    nasdaq100_tickers, statement_repo=None, market_cap_by_ticker=None,
    revenue_growth_by_ticker=None, classifier_results=None, classifier_raise_for=None,
):
    company_repo = FakeCompanyRepository()
    for t in nasdaq100_tickers:
        company_repo.save(_company(t))
    statement_repo = statement_repo or FakeFinancialStatementRepository()
    index_repo = FakeIndexMembershipRepository({t: ["Nasdaq-100"] for t in nasdaq100_tickers})
    classification_repo = FakeNasdaq100ClassificationRepository()
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    compute_analysis = FakeComputeFinancialAnalysis(revenue_growth_by_ticker)
    compute_valuation = FakeComputeValuation(market_cap_by_ticker)
    classifier = FakeNasdaq100Classifier(classifier_results, classifier_raise_for)
    use_case = RunNasdaq100ClassificationBatchUseCase(
        company_repo, index_repo, classification_repo,
        get_financials, compute_analysis, compute_valuation, classifier,
    )
    return use_case, classification_repo, classifier


def test_only_genuine_nasdaq100_members_are_included() -> None:
    company_repo_tickers = ["NVDA", "AMD", "NOTINDEX"]
    use_case, classification_repo, _ = _build(nasdaq100_tickers=["NVDA", "AMD"])
    # NOTINDEX exists as a company but isn't a Nasdaq-100 member
    use_case._company_repository.save(_company("NOTINDEX"))

    succeeded, failed = use_case.execute()

    saved = classification_repo.saved_batches[-1]
    saved_tickers = {r.ticker for r in saved}
    assert saved_tickers == {"NVDA", "AMD"}
    assert "NOTINDEX" not in saved_tickers


def test_computes_real_deterministic_market_cap_tier_and_maturity_stage() -> None:
    use_case, classification_repo, _ = _build(
        nasdaq100_tickers=["NVDA"],
        market_cap_by_ticker={"NVDA": 600_000_000_000.0},
        revenue_growth_by_ticker={"NVDA": 0.30},
    )

    use_case.execute()

    row = classification_repo.saved_batches[-1][0]
    assert row.market_cap_tier == "Mega-Cap"
    assert row.maturity_stage == "Hyper-Growth"


def test_llm_classifier_result_is_stored_directly() -> None:
    use_case, classification_repo, classifier = _build(nasdaq100_tickers=["NVDA"])

    use_case.execute()

    row = classification_repo.saved_batches[-1][0]
    assert row.value_chain_position == "Midstream — Design/Development"
    assert row.business_model == "Subscription/SaaS"
    assert classifier.classify_calls == ["NVDA"]


def test_a_failed_llm_classification_does_not_abort_the_batch() -> None:
    use_case, classification_repo, _ = _build(
        nasdaq100_tickers=["NVDA", "AMD"], classifier_raise_for={"NVDA"},
    )

    succeeded, failed = use_case.execute()

    saved = {r.ticker: r for r in classification_repo.saved_batches[-1]}
    assert saved["NVDA"].value_chain_position is None  # honestly None, not fabricated
    assert saved["AMD"].value_chain_position == "Midstream — Design/Development"  # AMD still, genuinely processed
    assert succeeded == 2  # both tickers still produced a real row


def test_market_structure_category_is_computed_from_real_ingested_peers() -> None:
    statement_repo = FakeFinancialStatementRepository()
    statement_repo.save_income_statement(_income("NVDA", 90.0))
    statement_repo.save_income_statement(_income("AMD", 5.0))
    statement_repo.save_income_statement(_income("INTC", 5.0))
    use_case, classification_repo, _ = _build(
        nasdaq100_tickers=["NVDA", "AMD", "INTC"], statement_repo=statement_repo,
    )

    use_case.execute()

    row = next(r for r in classification_repo.saved_batches[-1] if r.ticker == "NVDA")
    assert row.market_structure_category == "Monopoly"
    assert row.hhi is not None
