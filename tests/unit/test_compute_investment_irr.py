"""Tests for ComputeInvestmentIrrUseCase."""
from __future__ import annotations

from datetime import datetime, timezone

from src.application.use_cases.compute_investment_irr import (
    ComputeInvestmentIrrUseCase,
    InvalidIrrScenarioError,
)
from src.domain.entities.market_quote import MarketQuote
from tests.unit.fakes import FakeDataProvider

TICKER = "ROCKET"


def _provider(price: float) -> FakeDataProvider:
    return FakeDataProvider(
        company=None, income_statements=[], balance_sheets=[], cash_flow_statements=[],
        quote=MarketQuote(ticker=TICKER, price=price, market_cap=price * 1_000_000,
                           as_of=datetime.now(timezone.utc)),
    )


def test_irr_with_explicit_entry_price_no_dividends_matches_the_pure_math_case() -> None:
    use_case = ComputeInvestmentIrrUseCase(_provider(50.0))
    result = use_case.execute(entry_price=100, exit_price=110, years=1)

    assert result.scenario.cash_flows == [-100, 110]
    assert result.irr is not None
    assert abs(result.irr - 0.10) < 1e-6


def test_irr_fetches_entry_price_from_the_live_quote_when_not_supplied() -> None:
    use_case = ComputeInvestmentIrrUseCase(_provider(75.0))
    result = use_case.execute(ticker=TICKER, exit_price=100, years=2)

    assert result.scenario.entry_price == 75.0
    assert result.scenario.cash_flows[0] == -75.0


def test_irr_includes_annual_dividends_in_every_year_and_exit_proceeds_only_in_the_last() -> None:
    use_case = ComputeInvestmentIrrUseCase(_provider(50.0))
    result = use_case.execute(entry_price=100, exit_price=120, years=3, annual_dividend_per_share=2.0)

    assert result.scenario.cash_flows == [-100, 2.0, 2.0, 122.0]


def test_irr_raises_without_either_entry_price_or_ticker() -> None:
    use_case = ComputeInvestmentIrrUseCase(_provider(50.0))
    try:
        use_case.execute(exit_price=100, years=1)
        raise AssertionError("expected InvalidIrrScenarioError")
    except InvalidIrrScenarioError:
        pass


def test_irr_raises_for_zero_years() -> None:
    use_case = ComputeInvestmentIrrUseCase(_provider(50.0))
    try:
        use_case.execute(entry_price=100, exit_price=110, years=0)
        raise AssertionError("expected InvalidIrrScenarioError")
    except InvalidIrrScenarioError:
        pass
