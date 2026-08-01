"""Tests for ConstructRiskParityPortfolioUseCase — the risk-parity
allocator. Volatility inputs reuse the same independently-verified
price series as test_compute_portfolio_risk.py (_ALTERNATING_CLOSES,
sample variance = 0.002/19 exactly) plus a second series with exactly
double the return magnitude, so the resulting weight ratio is a clean,
hand-verifiable 2:1.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from src.application.use_cases.construct_risk_parity_portfolio import (
    ConstructRiskParityPortfolioUseCase,
    InvalidInvestmentAmountError,
    NoAllocatableTickersError,
    NoTickersProvidedError,
)
from src.domain.entities.market_quote import MarketQuote, PriceBar
from tests.unit.fakes import FakeDataProvider
from src.domain.entities.company import Company, Sector

# 21 prices (most-recent-first) yielding exactly 20 alternating +-1%
# returns. Sample variance EXACTLY 0.002/19 — verified independently.
_LOW_VOL_CLOSES = [
    99.90004498800211, 100.90913635151728, 99.91003599160126, 100.9192282743447,
    99.9200279944007, 100.92932120646535, 99.93002099650035, 100.93941514798014,
    99.94001499800014, 100.94951009899003, 99.95000999900003, 100.959606059596,
    99.9600059996, 100.969703029899, 99.97000299989999, 100.97980100999999,
    99.98000099999999, 100.98989999999999, 99.99, 101.0, 100.0,
]
# Same shape, +-2% returns instead of +-1% -> variance is EXACTLY 4x,
# stdev EXACTLY 2x — independently verified via statistics.variance.
_HIGH_VOL_CLOSES = [
    99.60071923253732, 101.63338697197685, 99.6405754627224, 101.6740565946147,
    99.68044764177911, 101.71474249161133, 99.72033577608954, 101.75544466947913,
    99.76023987203837, 101.79616313473304, 99.80015993601278, 101.8368978938906,
    99.84009597440254, 101.87764895347199, 99.88004799359999, 101.91841631999999,
    99.92001599999999, 101.9592, 99.96, 102.0, 100.0,
]


class _PricedProvider(FakeDataProvider):
    def __init__(self, *args, closes_by_ticker=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._closes_by_ticker = closes_by_ticker or {}

    def get_daily_closes(self, ticker: str, limit: int = 30):
        closes = self._closes_by_ticker.get(ticker, [])
        return [PriceBar(bar_date=date(2026, 1, 1), close=c) for c in closes][:limit]


def _quote(ticker: str, price: float) -> MarketQuote:
    return MarketQuote(ticker=ticker, price=price, market_cap=1e9,
                         as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))


def test_weight_ratio_is_exactly_two_to_one_for_double_volatility() -> None:
    provider = _PricedProvider(
        company=Company(ticker="LOW", name="LOW", sector=Sector.TECHNOLOGY,
                          industry="X", exchange="X", country="US"),
        quotes_by_ticker={"LOW": _quote("LOW", 100.0), "HIGH": _quote("HIGH", 100.0)},
        closes_by_ticker={"LOW": _LOW_VOL_CLOSES, "HIGH": _HIGH_VOL_CLOSES},
    )
    use_case = ConstructRiskParityPortfolioUseCase(provider)
    result = use_case.execute(["LOW", "HIGH"], total_investment=10_000.0)

    assert result.excluded == []
    by_ticker = {a.ticker: a for a in result.allocations}
    # HIGH's volatility is exactly 2x LOW's -> LOW's weight is exactly
    # 2x HIGH's (inverse relationship)
    ratio = by_ticker["LOW"].target_weight / by_ticker["HIGH"].target_weight
    assert abs(ratio - 2.0) < 1e-6
    assert abs(by_ticker["LOW"].target_weight + by_ticker["HIGH"].target_weight - 1.0) < 1e-9


def test_target_dollars_and_shares_computed_correctly() -> None:
    provider = _PricedProvider(
        company=Company(ticker="LOW", name="LOW", sector=Sector.TECHNOLOGY,
                          industry="X", exchange="X", country="US"),
        quotes_by_ticker={"LOW": _quote("LOW", 50.0)},
        closes_by_ticker={"LOW": _LOW_VOL_CLOSES},
    )
    use_case = ConstructRiskParityPortfolioUseCase(provider)
    result = use_case.execute(["LOW"], total_investment=5_000.0)

    # Single ticker -> gets 100% weight by construction
    alloc = result.allocations[0]
    assert abs(alloc.target_weight - 1.0) < 1e-9
    assert abs(alloc.target_dollar_amount - 5_000.0) < 1e-9
    assert abs(alloc.suggested_shares - (5_000.0 / 50.0)) < 1e-9  # 100 shares


def test_insufficient_history_excluded_remaining_still_allocated() -> None:
    provider = _PricedProvider(
        company=Company(ticker="LOW", name="LOW", sector=Sector.TECHNOLOGY,
                          industry="X", exchange="X", country="US"),
        quotes_by_ticker={"LOW": _quote("LOW", 100.0), "SHORT": _quote("SHORT", 100.0)},
        closes_by_ticker={"LOW": _LOW_VOL_CLOSES, "SHORT": [100.0, 99.0, 98.0]},
    )
    use_case = ConstructRiskParityPortfolioUseCase(provider)
    result = use_case.execute(["LOW", "SHORT"], total_investment=1000.0)

    assert result.excluded == ["SHORT"]
    assert len(result.allocations) == 1
    assert result.allocations[0].ticker == "LOW"
    assert abs(result.allocations[0].target_weight - 1.0) < 1e-9  # sole survivor gets 100%


def test_quote_fetch_failure_excludes_ticker_not_crash() -> None:
    from src.application.interfaces.data_provider import DataProviderError

    class _FailingQuoteProvider(_PricedProvider):
        def get_quote(self, ticker: str):
            if ticker == "DEAD":
                raise DataProviderError("no quote")
            return super().get_quote(ticker)

    provider = _FailingQuoteProvider(
        company=Company(ticker="LOW", name="LOW", sector=Sector.TECHNOLOGY,
                          industry="X", exchange="X", country="US"),
        quotes_by_ticker={"LOW": _quote("LOW", 100.0)},
        closes_by_ticker={"LOW": _LOW_VOL_CLOSES},
    )
    use_case = ConstructRiskParityPortfolioUseCase(provider)
    result = use_case.execute(["LOW", "DEAD"], total_investment=1000.0)

    assert result.excluded == ["DEAD"]
    assert len(result.allocations) == 1


def test_empty_ticker_list_raises() -> None:
    provider = _PricedProvider(company=None, quotes_by_ticker={})
    use_case = ConstructRiskParityPortfolioUseCase(provider)
    try:
        use_case.execute([], total_investment=1000.0)
        raise AssertionError("expected NoTickersProvidedError")
    except NoTickersProvidedError:
        pass


def test_non_positive_investment_raises() -> None:
    provider = _PricedProvider(company=None, quotes_by_ticker={})
    use_case = ConstructRiskParityPortfolioUseCase(provider)
    try:
        use_case.execute(["LOW"], total_investment=0.0)
        raise AssertionError("expected InvalidInvestmentAmountError")
    except InvalidInvestmentAmountError:
        pass


def test_all_tickers_unallocatable_raises() -> None:
    provider = _PricedProvider(
        company=Company(ticker="SHORT", name="SHORT", sector=Sector.TECHNOLOGY,
                          industry="X", exchange="X", country="US"),
        quotes_by_ticker={"SHORT": _quote("SHORT", 100.0)},
        closes_by_ticker={"SHORT": [100.0, 99.0]},  # only 1 return, too short
    )
    use_case = ConstructRiskParityPortfolioUseCase(provider)
    try:
        use_case.execute(["SHORT"], total_investment=1000.0)
        raise AssertionError("expected NoAllocatableTickersError")
    except NoAllocatableTickersError:
        pass
