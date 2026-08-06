"""Tests for speculative-growth candidate tracking: adding/removing
candidates, and the core check-and-alert use case. Real logic verified
with fakes, no mocks needed — same discipline as
test_assess_speculative_growth.py, which this file builds on directly.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from src.application.use_cases.assess_speculative_growth import AssessSpeculativeGrowthUseCase
from src.application.use_cases.check_speculative_growth_candidates import (
    CheckSpeculativeGrowthCandidatesUseCase,
)
from src.application.use_cases.compute_valuation import ComputeValuationUseCase
from src.application.use_cases.get_company_financials import GetCompanyFinancialsUseCase
from src.application.use_cases.manage_speculative_growth_candidates import (
    AddSpeculativeGrowthCandidateUseCase,
    ListSpeculativeGrowthCandidatesUseCase,
    RemoveSpeculativeGrowthCandidateUseCase,
)
from src.domain.entities.company import Company, Sector
from src.domain.entities.financial_statement import (
    BalanceSheet, CashFlowStatement, FiscalPeriodKey, IncomeStatement, Period,
)
from src.domain.entities.market_quote import MarketQuote
from src.application.use_cases.get_company_financials import CompanyNotFoundError
from tests.unit.fakes import (
    FakeAlertRepository,
    FakeCompanyRepository,
    FakeDataProvider,
    FakeFinancialStatementRepository,
    FakeSpeculativeGrowthCandidateRepository,
)

TICKER = "ROCKET"
USER = "alice"


def _key(year: int) -> FiscalPeriodKey:
    return FiscalPeriodKey(ticker=TICKER, fiscal_year=year, period=Period.ANNUAL)


def _income(year: int, revenue: float, net_income: float | None = -5_000_000) -> IncomeStatement:
    return IncomeStatement(
        key=_key(year), fiscal_date_ending=date(year, 12, 31), reported_currency="USD",
        revenue=revenue, net_income=net_income,
    )


def _setup(income_statements, market_cap=1_000_000_000):
    """Returns (statement_repo, provider, assess). statement_repo is
    the actual source of financial statements — mutate it via
    save_income_statement to simulate a new fiscal year's data
    arriving between checks. provider is separate and only backs the
    market-cap/quote lookup; mutate its _quote to simulate cap changes."""
    company = Company(
        ticker=TICKER, name="Rocket Inc", sector=Sector.TECHNOLOGY,
        industry="Software", exchange="NASDAQ", country="US",
    )
    company_repo = FakeCompanyRepository()
    company_repo.save(company)

    statement_repo = FakeFinancialStatementRepository()
    for s in income_statements:
        statement_repo.save_income_statement(s)

    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    provider = FakeDataProvider(
        company=company, income_statements=income_statements,
        balance_sheets=[], cash_flow_statements=[],
        quote=MarketQuote(ticker=TICKER, price=10.0, market_cap=market_cap, as_of=datetime.now(timezone.utc)),
    )
    compute_valuation = ComputeValuationUseCase(get_financials, provider)
    assess = AssessSpeculativeGrowthUseCase(get_financials, compute_valuation)
    return statement_repo, provider, assess


# --- Add / Remove / List -----------------------------------------------

def test_add_establishes_an_initial_baseline_from_a_real_assessment() -> None:
    _, _, assess = _setup([_income(2023, 10_000_000), _income(2024, 15_000_000), _income(2025, 30_000_000)])
    candidate_repo = FakeSpeculativeGrowthCandidateRepository()
    use_case = AddSpeculativeGrowthCandidateUseCase(candidate_repo, assess)

    candidate = use_case.execute(USER, "rocket")

    assert candidate.ticker == "ROCKET"
    assert candidate.last_growth_trend == "accelerating"
    assert candidate.last_checked_at is not None


def test_add_does_not_gate_on_whether_the_assessment_looks_favorable() -> None:
    # Decelerating growth — a "bad" assessment by the framework's own
    # logic — should still be addable. The use case never judges.
    _, _, assess = _setup([_income(2023, 10_000_000), _income(2024, 20_000_000), _income(2025, 24_000_000)])
    candidate_repo = FakeSpeculativeGrowthCandidateRepository()
    use_case = AddSpeculativeGrowthCandidateUseCase(candidate_repo, assess)

    candidate = use_case.execute(USER, "ROCKET")
    assert candidate.last_growth_trend == "decelerating"


def test_add_propagates_company_not_found_for_a_non_ingested_ticker() -> None:
    _, _, assess = _setup([])
    candidate_repo = FakeSpeculativeGrowthCandidateRepository()
    use_case = AddSpeculativeGrowthCandidateUseCase(candidate_repo, assess)

    try:
        use_case.execute(USER, "NOTREAL")
        raise AssertionError("expected CompanyNotFoundError")
    except CompanyNotFoundError:
        pass


def test_add_is_idempotent_and_does_not_reset_existing_state() -> None:
    _, _, assess = _setup([_income(2023, 10_000_000), _income(2024, 15_000_000), _income(2025, 30_000_000)])
    candidate_repo = FakeSpeculativeGrowthCandidateRepository()
    use_case = AddSpeculativeGrowthCandidateUseCase(candidate_repo, assess)

    first = use_case.execute(USER, "ROCKET")
    second = use_case.execute(USER, "ROCKET")

    assert first.added_at == second.added_at


def test_remove_returns_true_when_a_candidate_existed() -> None:
    _, _, assess = _setup([_income(2023, 10_000_000), _income(2024, 15_000_000), _income(2025, 30_000_000)])
    candidate_repo = FakeSpeculativeGrowthCandidateRepository()
    AddSpeculativeGrowthCandidateUseCase(candidate_repo, assess).execute(USER, "ROCKET")

    removed = RemoveSpeculativeGrowthCandidateUseCase(candidate_repo).execute(USER, "rocket")
    assert removed is True
    assert ListSpeculativeGrowthCandidatesUseCase(candidate_repo).execute(USER) == []


def test_remove_returns_false_for_a_ticker_that_was_never_added() -> None:
    candidate_repo = FakeSpeculativeGrowthCandidateRepository()
    removed = RemoveSpeculativeGrowthCandidateUseCase(candidate_repo).execute(USER, "GHOST")
    assert removed is False


# --- Check / alerting ----------------------------------------------------

def test_first_check_after_adding_establishes_baseline_and_fires_no_alert() -> None:
    _, _, assess = _setup([_income(2023, 10_000_000), _income(2024, 15_000_000), _income(2025, 30_000_000)])
    candidate_repo = FakeSpeculativeGrowthCandidateRepository()
    alert_repo = FakeAlertRepository()
    AddSpeculativeGrowthCandidateUseCase(candidate_repo, assess).execute(USER, "ROCKET")

    fired = CheckSpeculativeGrowthCandidatesUseCase(candidate_repo, alert_repo, assess).execute(USER)

    assert fired == []


def test_growth_trend_flip_fires_an_alert() -> None:
    statement_repo, _, assess = _setup([_income(2023, 10_000_000), _income(2024, 15_000_000), _income(2025, 30_000_000)])
    candidate_repo = FakeSpeculativeGrowthCandidateRepository()
    alert_repo = FakeAlertRepository()
    AddSpeculativeGrowthCandidateUseCase(candidate_repo, assess).execute(USER, "ROCKET")

    # Simulate time passing: a new fiscal year's data shows deceleration
    # relative to what was accelerating at add-time.
    statement_repo.save_income_statement(_income(2026, 33_000_000))  # 2025->2026: only 10% growth

    fired = CheckSpeculativeGrowthCandidatesUseCase(candidate_repo, alert_repo, assess).execute(USER)

    assert len(fired) == 1
    assert "flipped from accelerating to decelerating" in fired[0].message


def test_steady_state_between_checks_fires_no_alert() -> None:
    _, _, assess = _setup([_income(2023, 10_000_000), _income(2024, 15_000_000), _income(2025, 30_000_000)])
    candidate_repo = FakeSpeculativeGrowthCandidateRepository()
    alert_repo = FakeAlertRepository()
    AddSpeculativeGrowthCandidateUseCase(candidate_repo, assess).execute(USER, "ROCKET")

    fired = CheckSpeculativeGrowthCandidatesUseCase(candidate_repo, alert_repo, assess).execute(USER)
    assert fired == []


def test_market_cap_crossing_out_of_small_cap_fires_an_alert() -> None:
    _, provider, assess = _setup(
        [_income(2023, 10_000_000), _income(2024, 15_000_000), _income(2025, 30_000_000)],
        market_cap=500_000_000,  # starts as small-cap
    )
    candidate_repo = FakeSpeculativeGrowthCandidateRepository()
    alert_repo = FakeAlertRepository()
    AddSpeculativeGrowthCandidateUseCase(candidate_repo, assess).execute(USER, "ROCKET")

    provider._quote = MarketQuote(
        ticker=TICKER, price=200.0, market_cap=3_000_000_000, as_of=datetime.now(timezone.utc)
    )

    fired = CheckSpeculativeGrowthCandidatesUseCase(candidate_repo, alert_repo, assess).execute(USER)

    assert len(fired) == 1
    assert "small-cap threshold" in fired[0].message
