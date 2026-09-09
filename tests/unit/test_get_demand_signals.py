from __future__ import annotations

from datetime import date

from src.application.use_cases.get_demand_signals import GetDemandSignalsUseCase
from src.domain.entities.analyst_ratings import AnalystGrade, AnalystRatings
from src.domain.entities.financial_analysis import CompanyFinancialAnalysis, YearlyRatios
from src.domain.services.economic_cycle_math import EconomicCycleState


class _FakeFinancialAnalysisUseCase:
    def __init__(self, analysis: CompanyFinancialAnalysis) -> None:
        self._analysis = analysis

    def execute(self, ticker: str, years: int = 5) -> CompanyFinancialAnalysis:
        return self._analysis


class _FakeAnalystRatingsUseCase:
    def __init__(self, ratings: AnalystRatings | None) -> None:
        self._ratings = ratings

    def execute(self, ticker: str) -> AnalystRatings | None:
        return self._ratings


class _FakeEconomicCycleUseCase:
    def __init__(self, state: EconomicCycleState) -> None:
        self._state = state

    def execute(self) -> EconomicCycleState:
        return self._state


def _ratio(fiscal_year: int, revenue_growth_yoy: float | None) -> YearlyRatios:
    return YearlyRatios(
        fiscal_year=fiscal_year, revenue_growth_yoy=revenue_growth_yoy,
        gross_margin=None, operating_margin=None, net_margin=None, free_cash_flow_margin=None,
        return_on_equity=None, return_on_assets=None, debt_to_equity=None, current_ratio=None,
    )


def _grade(action: str) -> AnalystGrade:
    return AnalystGrade(
        grading_company="Test Firm", date=date(2026, 1, 1),
        previous_grade="Hold", new_grade="Buy", action=action,
    )


def _cycle(state: str) -> EconomicCycleState:
    return EconomicCycleState(state=state, yield_curve_inverted=False, sahm_rule_triggered=False, reasoning=["test"])


def test_combines_all_three_real_signals_correctly() -> None:
    analysis = CompanyFinancialAnalysis(
        ticker="AAPL", yearly_ratios=[_ratio(2024, 0.08), _ratio(2025, 0.12)],
    )
    ratings = AnalystRatings(
        ticker="AAPL", recent_grades=[_grade("upgrade"), _grade("upgrade"), _grade("maintain")],
        last_month_avg_price_target=None, last_month_count=0,
        last_quarter_avg_price_target=331.69, last_quarter_count=17,
        last_year_avg_price_target=None, last_year_count=0,
    )
    use_case = GetDemandSignalsUseCase(
        _FakeFinancialAnalysisUseCase(analysis),
        _FakeAnalystRatingsUseCase(ratings),
        _FakeEconomicCycleUseCase(_cycle("Expansion")),
    )

    result = use_case.execute("aapl")

    assert result.ticker == "AAPL"
    assert result.latest_revenue_growth_yoy == 0.12
    assert result.prior_revenue_growth_yoy == 0.08
    assert result.revenue_growth_accelerating is True
    assert result.recent_upgrades == 2
    assert result.recent_downgrades == 0
    assert result.analyst_consensus_direction == "More bullish"
    assert result.last_quarter_avg_price_target == 331.69
    assert result.economic_cycle_state == "Expansion"


def test_honestly_handles_a_ticker_with_no_real_analyst_coverage_at_all() -> None:
    analysis = CompanyFinancialAnalysis(ticker="OBSCURE", yearly_ratios=[_ratio(2025, 0.05)])
    use_case = GetDemandSignalsUseCase(
        _FakeFinancialAnalysisUseCase(analysis),
        _FakeAnalystRatingsUseCase(ratings=None),
        _FakeEconomicCycleUseCase(_cycle("Expansion")),
    )

    result = use_case.execute("OBSCURE")

    assert result.recent_upgrades == 0
    assert result.recent_downgrades == 0
    assert result.analyst_consensus_direction == "No recent activity"
    assert result.last_quarter_avg_price_target is None


def test_honestly_handles_a_single_year_of_real_data_with_no_prior_year_to_compare() -> None:
    analysis = CompanyFinancialAnalysis(ticker="NEW", yearly_ratios=[_ratio(2025, 0.10)])
    use_case = GetDemandSignalsUseCase(
        _FakeFinancialAnalysisUseCase(analysis),
        _FakeAnalystRatingsUseCase(ratings=None),
        _FakeEconomicCycleUseCase(_cycle("Expansion")),
    )

    result = use_case.execute("NEW")

    assert result.latest_revenue_growth_yoy == 0.10
    assert result.prior_revenue_growth_yoy is None
    assert result.revenue_growth_accelerating is None
