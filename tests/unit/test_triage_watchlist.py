"""Tests for TriageWatchlistUseCase.

Score arithmetic is hand-verified in comments — same discipline as the
Greeks and option P&L tests. Weights: day move x1.0, since-added x0.5,
P/E drift x0.5 (all in percentage points), +10.0 flat if target crossed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from src.application.interfaces.data_provider import DataProviderError
from src.application.use_cases.triage_watchlist import TriageWatchlistUseCase
from src.domain.entities.market_quote import MarketQuote
from src.domain.entities.monitoring import PriceSnapshot
from src.domain.entities.watchlist import WatchlistItem
from tests.unit.fakes import FakePriceSnapshotRepository, FakeWatchlistRepository

NOW = datetime.now(timezone.utc)


class _QuoteOnlyProvider:
    """Duck-typed provider: triage only calls get_quote."""

    def __init__(self, prices: dict[str, float], failing: set[str] | None = None) -> None:
        self._prices = prices
        self._failing = failing or set()

    def get_quote(self, ticker: str) -> MarketQuote:
        if ticker in self._failing:
            raise DataProviderError(f"no quote for {ticker}")
        return MarketQuote(ticker=ticker, price=self._prices[ticker], market_cap=1e12, as_of=NOW)


class _PerTickerValuation:
    def __init__(self, pe_by_ticker: dict[str, float]) -> None:
        self._pe = pe_by_ticker

    def execute(self, ticker: str):
        if ticker not in self._pe:
            raise RuntimeError(f"no financials for {ticker}")
        return SimpleNamespace(price_to_earnings=self._pe[ticker])


def _item(ticker: str, **kwargs) -> WatchlistItem:
    return WatchlistItem(user_id="alice", ticker=ticker, added_at=NOW, **kwargs)


def test_scores_hand_verified_and_sorted_desc() -> None:
    watchlist = FakeWatchlistRepository()
    # AAPL: snapshot 100 -> current 105 (day +5%), added at 100 (+5% since),
    #       P/E 20 -> 22 (+10% drift), target 90 not crossed (105 > 90)
    #       score = 5.0*1.0 + 5.0*0.5 + 10.0*0.5 = 5.0 + 2.5 + 5.0 = 12.5
    watchlist.add(_item("AAPL", added_price=100.0, added_pe=20.0, target_price=90.0))
    # MSFT: snapshot 250 -> current 240 (day -4%), added at 200 (+20% since),
    #       no added_pe baseline (drift absent even though current P/E exists),
    #       target 250 CROSSED (240 <= 250)
    #       score = 4.0*1.0 + 20.0*0.5 + 0 + 10.0 = 4.0 + 10.0 + 10.0 = 24.0
    watchlist.add(_item("MSFT", added_price=200.0, target_price=250.0))

    snapshots = FakePriceSnapshotRepository()
    snapshots.save(PriceSnapshot(ticker="AAPL", price=100.0, captured_at=NOW))
    snapshots.save(PriceSnapshot(ticker="MSFT", price=250.0, captured_at=NOW))

    use_case = TriageWatchlistUseCase(
        watchlist,
        _QuoteOnlyProvider({"AAPL": 105.0, "MSFT": 240.0}),
        snapshots,
        valuation_use_case=_PerTickerValuation({"AAPL": 22.0, "MSFT": 30.0}),
    )
    result = use_case.execute("alice")

    assert [t.ticker for t in result.items] == ["MSFT", "AAPL"]  # highest attention first

    msft, aapl = result.items
    assert abs(msft.triage_score - 24.0) < 1e-9
    assert msft.signals.target_crossed is True
    assert msft.signals.pe_drift_pct is None  # no baseline -> honestly absent
    assert msft.signals.current_pe == 30.0  # current P/E still reported

    assert abs(aapl.triage_score - 12.5) < 1e-9
    assert aapl.signals.target_crossed is False
    assert abs(aapl.signals.day_move_pct - 0.05) < 1e-9
    assert abs(aapl.signals.pe_drift_pct - 0.10) < 1e-9


def test_missing_everything_scores_zero_with_all_signals_none() -> None:
    watchlist = FakeWatchlistRepository()
    watchlist.add(_item("AAPL"))  # no baselines, no target

    use_case = TriageWatchlistUseCase(
        watchlist,
        _QuoteOnlyProvider({"AAPL": 105.0}),
        FakePriceSnapshotRepository(),  # no prior snapshot -> no day move
        valuation_use_case=None,  # no valuation wired -> no P/E at all
    )
    result = use_case.execute("alice")

    assert len(result.items) == 1
    item = result.items[0]
    assert item.triage_score == 0.0
    assert item.signals.day_move_pct is None
    assert item.signals.move_since_added_pct is None
    assert item.signals.pe_drift_pct is None
    assert item.signals.current_pe is None
    assert item.signals.target_crossed is False
    assert item.signals.current_price == 105.0  # the one thing we DO know


def test_quote_failure_excludes_ticker_but_triages_the_rest() -> None:
    watchlist = FakeWatchlistRepository()
    watchlist.add(_item("AAPL", added_price=100.0))
    watchlist.add(_item("BROKEN", added_price=50.0))

    use_case = TriageWatchlistUseCase(
        watchlist,
        _QuoteOnlyProvider({"AAPL": 110.0}, failing={"BROKEN"}),
        FakePriceSnapshotRepository(),
    )
    result = use_case.execute("alice")

    assert result.tickers_excluded == ["BROKEN"]
    assert [t.ticker for t in result.items] == ["AAPL"]
    # since-added: (110-100)/100 = +10% -> 10.0 * 0.5 = 5.0
    assert abs(result.items[0].triage_score - 5.0) < 1e-9


def test_list_name_filter_scopes_the_triage() -> None:
    watchlist = FakeWatchlistRepository()
    watchlist.add(_item("AAPL", list_name="Tech Watch"))
    watchlist.add(_item("MSFT", list_name="Default"))

    use_case = TriageWatchlistUseCase(
        watchlist,
        _QuoteOnlyProvider({"AAPL": 105.0, "MSFT": 300.0}),
        FakePriceSnapshotRepository(),
    )
    result = use_case.execute("alice", list_name="Tech Watch")

    assert [t.ticker for t in result.items] == ["AAPL"]
