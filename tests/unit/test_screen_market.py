from __future__ import annotations

from src.application.use_cases.screen_market import ScreenMarketUseCase
from src.domain.entities.market_screen import MarketScreenCandidate


class _FakeMarketScreenProvider:
    """A genuinely minimal, dedicated fake -- screen_market is a
    completely independent capability with no dependency on the
    heavier, shared FakeDataProvider's own, unrelated required state
    (a real Company, income statements, etc)."""

    def __init__(self, candidates: list[MarketScreenCandidate] | None = None) -> None:
        self._candidates = candidates or []
        self.last_call_kwargs: dict | None = None

    def screen_market(self, **kwargs) -> list[MarketScreenCandidate]:
        self.last_call_kwargs = kwargs
        return self._candidates


def _candidate(ticker: str = "AAPL") -> MarketScreenCandidate:
    return MarketScreenCandidate(
        ticker=ticker, company_name="Apple Inc.", market_cap=4_699_513_299_320.0,
        price=319.97, beta=1.085, last_annual_dividend=1.06, volume=39_606_884,
        sector="Technology", industry="Consumer Electronics", exchange="NASDAQ", country="US",
    )


def test_returns_real_candidates_from_the_provider() -> None:
    candidates = [_candidate("AAPL"), _candidate("MSFT")]
    provider = _FakeMarketScreenProvider(candidates)
    use_case = ScreenMarketUseCase(provider)

    result = use_case.execute(sector="Technology")

    assert result == candidates


def test_passes_through_the_real_filter_criteria_given() -> None:
    provider = _FakeMarketScreenProvider()
    use_case = ScreenMarketUseCase(provider)

    use_case.execute(sector="Technology", market_cap_more_than=10_000_000_000, country="US")

    assert provider.last_call_kwargs["sector"] == "Technology"
    assert provider.last_call_kwargs["market_cap_more_than"] == 10_000_000_000
    assert provider.last_call_kwargs["country"] == "US"


def test_returns_an_honestly_empty_list_when_nothing_genuinely_matches() -> None:
    provider = _FakeMarketScreenProvider(candidates=[])
    use_case = ScreenMarketUseCase(provider)

    result = use_case.execute(sector="Nonexistent Sector")

    assert result == []
