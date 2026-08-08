"""Tests for GetMacroSnapshotUseCase — every piece fetched
independently and allowed to fail on its own without blocking the rest
of the snapshot."""
from __future__ import annotations

from datetime import date

from src.application.use_cases.get_macro_snapshot import GetMacroSnapshotUseCase
from src.domain.entities.economic_indicator import EconomicIndicatorReading
from src.domain.entities.general_news import GeneralNewsHeadline
from src.domain.entities.market_risk_premium import MarketRiskPremium


class _FakeProvider:
    def __init__(
        self,
        indicators: dict[str, list[EconomicIndicatorReading]] | None = None,
        risk_premium: MarketRiskPremium | None = None,
        news: list[GeneralNewsHeadline] | None = None,
        indicator_raises: bool = False,
        risk_premium_raises: bool = False,
        news_raises: bool = False,
    ):
        self._indicators = indicators or {}
        self._risk_premium = risk_premium
        self._news = news or []
        self._indicator_raises = indicator_raises
        self._risk_premium_raises = risk_premium_raises
        self._news_raises = news_raises

    def get_economic_indicator(self, name: str) -> list[EconomicIndicatorReading]:
        if self._indicator_raises:
            raise NotImplementedError("not supported")
        return self._indicators.get(name, [])

    def get_market_risk_premium(self, country: str = "United States") -> MarketRiskPremium | None:
        if self._risk_premium_raises:
            raise NotImplementedError("not supported")
        return self._risk_premium

    def get_general_news(self, limit: int = 20) -> list[GeneralNewsHeadline]:
        if self._news_raises:
            raise NotImplementedError("not supported")
        return self._news[:limit]


def _reading(name: str, value: float, year: int = 2025, month: int = 11) -> EconomicIndicatorReading:
    return EconomicIndicatorReading(name=name, as_of=date(year, month, 1), value=value)


def test_execute_returns_all_pieces_when_everything_is_available() -> None:
    provider = _FakeProvider(
        indicators={
            "GDP": [_reading("GDP", 31422.526)],
            "CPI": [_reading("CPI", 325.063), _reading("CPI", 324.245, month=9)],
            "inflationRate": [_reading("inflationRate", 2.28)],
            "unemploymentRate": [_reading("unemploymentRate", 4.5)],
        },
        risk_premium=MarketRiskPremium("United States", 0.0023, 0.0446),
        news=[GeneralNewsHeadline(title="Fed holds rates steady", published_at=None, publisher="Reuters", url=None, snippet=None)],
    )
    use_case = GetMacroSnapshotUseCase(provider)
    snapshot = use_case.execute()

    assert snapshot.gdp.value == 31422.526
    assert snapshot.cpi.value == 325.063  # most recent, not the second row
    assert snapshot.inflation_rate.value == 2.28
    assert snapshot.unemployment_rate.value == 4.5
    assert snapshot.risk_premium.total_equity_risk_premium == 0.0446
    assert len(snapshot.recent_news) == 1


def test_execute_uses_the_most_recent_reading_when_multiple_are_returned() -> None:
    provider = _FakeProvider(
        indicators={"CPI": [_reading("CPI", 325.063, month=11), _reading("CPI", 324.245, month=9)]},
    )
    use_case = GetMacroSnapshotUseCase(provider)
    snapshot = use_case.execute()
    assert snapshot.cpi.as_of.month == 11


def test_execute_returns_none_for_an_indicator_that_is_genuinely_missing() -> None:
    provider = _FakeProvider(indicators={"GDP": []})
    use_case = GetMacroSnapshotUseCase(provider)
    snapshot = use_case.execute()
    assert snapshot.gdp is None


def test_execute_degrades_gracefully_when_indicators_are_unsupported() -> None:
    """The core property this use case exists for: one missing piece
    shouldn't crash the whole snapshot."""
    provider = _FakeProvider(indicator_raises=True, risk_premium_raises=True, news_raises=True)
    use_case = GetMacroSnapshotUseCase(provider)
    snapshot = use_case.execute()

    assert snapshot.gdp is None
    assert snapshot.cpi is None
    assert snapshot.inflation_rate is None
    assert snapshot.unemployment_rate is None
    assert snapshot.risk_premium is None
    assert snapshot.recent_news == []
    # The snapshot itself is still a real, usable object — not an exception.
    assert snapshot.as_of is not None


def test_execute_respects_the_news_limit() -> None:
    provider = _FakeProvider(
        news=[GeneralNewsHeadline(title=f"Headline {i}", published_at=None, publisher=None, url=None, snippet=None)
              for i in range(10)],
    )
    use_case = GetMacroSnapshotUseCase(provider)
    snapshot = use_case.execute(news_limit=3)
    assert len(snapshot.recent_news) == 3
