from __future__ import annotations

from datetime import date, datetime, timezone

from src.application.use_cases.get_stock_candles import GetStockCandlesUseCase
from src.domain.entities.stock_candle import StockCandle
from tests.unit.fakes import FakeStockDataProvider


def test_returns_real_candles_from_the_provider() -> None:
    candles = [
        StockCandle(ticker="AAPL", timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    open=100.0, high=105.0, low=99.0, close=103.0, volume=1_000_000),
    ]
    provider = FakeStockDataProvider(candles={"AAPL": candles})
    use_case = GetStockCandlesUseCase(provider)

    result = use_case.execute("AAPL", "D", date(2026, 1, 1), date(2026, 1, 2))

    assert result == candles


def test_normalizes_ticker_case_and_whitespace() -> None:
    candles = [
        StockCandle(ticker="AAPL", timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    open=100.0, high=105.0, low=99.0, close=103.0, volume=1_000_000),
    ]
    provider = FakeStockDataProvider(candles={"AAPL": candles})
    use_case = GetStockCandlesUseCase(provider)

    result = use_case.execute(" aapl ", "D", date(2026, 1, 1), date(2026, 1, 2))

    assert result == candles


def test_returns_an_honestly_empty_list_for_a_genuinely_unknown_ticker() -> None:
    provider = FakeStockDataProvider(candles={})
    use_case = GetStockCandlesUseCase(provider)

    result = use_case.execute("XXXX", "D", date(2026, 1, 1), date(2026, 1, 2))

    assert result == []
