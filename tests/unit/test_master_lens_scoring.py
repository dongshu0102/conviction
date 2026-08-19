from datetime import datetime, timezone

from src.domain.entities.financial_analysis import CompanyFinancialAnalysis, YearlyRatios
from src.domain.entities.valuation_snapshot import ValuationSnapshot
from src.domain.services.master_lens_scoring import (
    score_buffett, score_dalio, score_fisher, score_graham, score_klarman,
    score_lynch, score_marks, score_munger, score_soros, score_templeton,
)


def _ratios(**overrides) -> YearlyRatios:
    defaults = dict(
        fiscal_year=2024, revenue_growth_yoy=0.10, gross_margin=0.5, operating_margin=0.2,
        net_margin=0.15, free_cash_flow_margin=0.12, return_on_equity=0.2, return_on_assets=0.1,
        debt_to_equity=0.5, current_ratio=1.5,
    )
    defaults.update(overrides)
    return YearlyRatios(**defaults)


def _valuation(**overrides) -> ValuationSnapshot:
    defaults = dict(
        ticker="TEST", as_of=datetime.now(timezone.utc), price=100, market_cap=1e9,
        enterprise_value=1.1e9, fundamentals_fiscal_year=2024,
        price_to_earnings=15, price_to_sales=3, price_to_book=3,
        price_to_free_cash_flow=15, ev_to_ebitda=10,
    )
    defaults.update(overrides)
    return ValuationSnapshot(**defaults)


def test_buffett_scores_high_for_a_wide_stable_moat() -> None:
    analysis = CompanyFinancialAnalysis(ticker="T", yearly_ratios=[
        _ratios(fiscal_year=2022, gross_margin=0.60, free_cash_flow_margin=0.18),
        _ratios(fiscal_year=2023, gross_margin=0.61, free_cash_flow_margin=0.19),
    ])
    score, basis = score_buffett(analysis)
    assert score is not None
    assert score > 6.0
    assert "gross margin" in basis and "FCF margin" in basis


def test_buffett_returns_none_with_zero_data() -> None:
    analysis = CompanyFinancialAnalysis(ticker="T", yearly_ratios=[])
    score, basis = score_buffett(analysis)
    assert score is None
    assert "Insufficient" in basis


def test_munger_penalizes_real_high_leverage() -> None:
    analysis = CompanyFinancialAnalysis(ticker="T", yearly_ratios=[_ratios(debt_to_equity=3.0, current_ratio=0.5)])
    score, _ = score_munger(analysis)
    assert score is not None
    assert score < 3.0


def test_graham_scores_low_for_an_expensive_stock() -> None:
    valuation = _valuation(price_to_earnings=40, price_to_book=10)
    score, _ = score_graham(valuation)
    assert score is not None
    assert score < 2.0


def test_graham_scores_high_for_a_cheap_stock() -> None:
    valuation = _valuation(price_to_earnings=8, price_to_book=1)
    score, _ = score_graham(valuation)
    assert score is not None
    assert score > 7.0


def test_lynch_penalizes_genuinely_erratic_growth() -> None:
    analysis = CompanyFinancialAnalysis(ticker="T", yearly_ratios=[
        _ratios(fiscal_year=2022, revenue_growth_yoy=0.40),
        _ratios(fiscal_year=2023, revenue_growth_yoy=-0.20),
        _ratios(fiscal_year=2024, revenue_growth_yoy=0.35),
    ])
    score, _ = score_lynch(analysis)
    assert score is not None
    assert score < 6.0


def test_dalio_degrades_honestly_without_multi_year_roa_history() -> None:
    analysis = CompanyFinancialAnalysis(ticker="T", yearly_ratios=[_ratios(debt_to_equity=0.5)])
    score, basis = score_dalio(analysis)
    assert score is not None
    assert "insufficient history" in basis


def test_marks_scores_low_for_a_high_ev_ebitda_multiple() -> None:
    valuation = _valuation(ev_to_ebitda=35)
    score, _ = score_marks(valuation)
    assert score is not None
    assert score < 1.0


def test_klarman_rewards_real_liquidity_and_low_leverage() -> None:
    analysis = CompanyFinancialAnalysis(ticker="T", yearly_ratios=[_ratios(current_ratio=3.0, debt_to_equity=0.1)])
    score, _ = score_klarman(analysis)
    assert score is not None
    assert score > 8.0


def test_fisher_returns_none_with_no_growth_history() -> None:
    analysis = CompanyFinancialAnalysis(ticker="T", yearly_ratios=[_ratios(revenue_growth_yoy=None)])
    score, basis = score_fisher(analysis)
    assert score is None
    assert "Insufficient" in basis


def test_templeton_scores_high_for_a_genuinely_unloved_stock() -> None:
    valuation = _valuation(price_to_sales=0.5)
    score, _ = score_templeton(valuation)
    assert score is not None
    assert score > 8.0


def test_soros_scores_above_neutral_for_genuinely_accelerating_growth() -> None:
    analysis = CompanyFinancialAnalysis(ticker="T", yearly_ratios=[
        _ratios(fiscal_year=2023, revenue_growth_yoy=0.05),
        _ratios(fiscal_year=2024, revenue_growth_yoy=0.20),
    ])
    score, basis = score_soros(analysis)
    assert score is not None
    assert score > 5.0
    assert "5.0%" in basis and "20.0%" in basis


def test_soros_scores_below_neutral_for_genuinely_decelerating_growth() -> None:
    analysis = CompanyFinancialAnalysis(ticker="T", yearly_ratios=[
        _ratios(fiscal_year=2023, revenue_growth_yoy=0.20),
        _ratios(fiscal_year=2024, revenue_growth_yoy=0.05),
    ])
    score, _ = score_soros(analysis)
    assert score is not None
    assert score < 5.0


def test_soros_returns_none_with_only_one_year_of_growth_data() -> None:
    analysis = CompanyFinancialAnalysis(ticker="T", yearly_ratios=[_ratios(revenue_growth_yoy=0.10)])
    score, basis = score_soros(analysis)
    assert score is None
    assert "Insufficient" in basis


def test_every_score_is_clamped_to_the_real_0_to_10_range() -> None:
    """A genuinely extreme, real-world-implausible input (e.g. massive
    negative leverage from a data anomaly) must never produce a score
    outside the documented 0-10 scale."""
    analysis = CompanyFinancialAnalysis(ticker="T", yearly_ratios=[
        _ratios(debt_to_equity=-50.0, current_ratio=100.0, gross_margin=5.0, free_cash_flow_margin=5.0),
    ])
    for score_fn in (score_buffett, score_munger, score_klarman, score_dalio):
        score, _ = score_fn(analysis)
        assert score is not None
        assert 0.0 <= score <= 10.0
