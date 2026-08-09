from __future__ import annotations

from datetime import date

from src.application.use_cases.run_capital_flow_scan import RunCapitalFlowScanUseCase
from src.domain.entities.capital_flow import CapitalFlowSource, InsiderTrade, PoliticianTrade
from src.domain.entities.company import Company, Sector
from tests.unit.fakes import FakeDataProvider


def _company() -> Company:
    return Company(ticker="X", name="X", sector=Sector.TECHNOLOGY, industry="X", exchange="X", country="US")


def _insider(symbol="NVDA", securities_transacted=10_000.0, price=180.0, transaction_type="P-Purchase", acquisition_or_disposition="A") -> InsiderTrade:
    return InsiderTrade(
        symbol=symbol, filing_date=date(2026, 8, 7), transaction_date=date(2026, 8, 6),
        reporting_name="TEST PERSON", type_of_owner="officer: CEO",
        transaction_type=transaction_type, acquisition_or_disposition=acquisition_or_disposition,
        securities_transacted=securities_transacted, price=price, security_name="Common Stock",
        url="https://test.gov",
    )


def _politician(chamber=CapitalFlowSource.SENATE, symbol="AAPL", amount_range="$1,000,001 - $5,000,000") -> PoliticianTrade:
    return PoliticianTrade(
        chamber=chamber, symbol=symbol, disclosure_date=date(2026, 8, 7),
        transaction_date=date(2026, 7, 23), person_name="Test Person", office="Test Person",
        owner="Self", asset_description="Test Corp", asset_type="Stock",
        transaction_type="Purchase", amount_range=amount_range, link="https://test",
    )


class _FakeCapitalFlowRepository:
    def __init__(self) -> None:
        self.seen_dedup_keys: set[str] = set()
        self.saved: list = []

    def save_new_events(self, events):
        new_events = [e for e in events if e.dedup_key not in self.seen_dedup_keys]
        for e in new_events:
            self.seen_dedup_keys.add(e.dedup_key)
        self.saved.extend(new_events)
        return new_events

    def list_recent(self, source=None, limit=50):
        results = self.saved if source is None else [e for e in self.saved if e.source == source]
        return list(reversed(results))[:limit]


class _CapitalFlowProvider(FakeDataProvider):
    def __init__(self, insider_trades=None, senate_trades=None, house_trades=None, raise_on="none", bars_by_ticker=None, fail_tickers=None):
        super().__init__(company=_company())
        self._insider_trades = insider_trades or []
        self._senate_trades = senate_trades or []
        self._house_trades = house_trades or []
        self._raise_on = raise_on
        self._bars_by_ticker = bars_by_ticker or {}
        self._fail_tickers = fail_tickers or set()

    def get_latest_insider_trades(self, limit: int = 100):
        if self._raise_on == "insider":
            raise NotImplementedError("not supported")
        return self._insider_trades

    def get_latest_senate_trades(self, limit: int = 100):
        if self._raise_on == "senate":
            raise NotImplementedError("not supported")
        return self._senate_trades

    def get_latest_house_trades(self, limit: int = 100):
        if self._raise_on == "house":
            raise NotImplementedError("not supported")
        return self._house_trades

    def get_daily_bars_full(self, ticker: str, limit: int = 30):
        if self._raise_on == "volume" or ticker in self._fail_tickers:
            raise NotImplementedError("not supported")
        return self._bars_by_ticker.get(ticker, [])


def test_execute_returns_only_genuinely_unusual_events() -> None:
    """Small trades and noise (gifts) should never reach the repository."""
    provider = _CapitalFlowProvider(
        insider_trades=[
            _insider(securities_transacted=100.0, price=10.0),  # $1,000 - too small
            _insider(transaction_type="G-Gift", securities_transacted=1_000_000, price=100.0),  # gift, filtered regardless of size
            _insider(symbol="NVDA", securities_transacted=10_000, price=180.0),  # $1.8M - real event
        ],
    )
    repo = _FakeCapitalFlowRepository()
    use_case = RunCapitalFlowScanUseCase(provider, repo)

    result = use_case.execute()

    assert len(result) == 1
    assert result[0].symbol == "NVDA"


def test_execute_scans_all_three_sources() -> None:
    provider = _CapitalFlowProvider(
        insider_trades=[_insider(symbol="NVDA", securities_transacted=10_000, price=180.0)],
        senate_trades=[_politician(chamber=CapitalFlowSource.SENATE, symbol="AAPL")],
        house_trades=[_politician(chamber=CapitalFlowSource.HOUSE, symbol="GOOGL")],
    )
    repo = _FakeCapitalFlowRepository()
    use_case = RunCapitalFlowScanUseCase(provider, repo)

    result = use_case.execute()

    assert len(result) == 3
    sources = {e.source for e in result}
    assert sources == {CapitalFlowSource.INSIDER, CapitalFlowSource.SENATE, CapitalFlowSource.HOUSE}


def test_execute_does_not_re_report_the_same_event_on_a_second_run() -> None:
    """The core property this use case exists for: real dedup across
    separate scan runs, not just within a single run's own list."""
    provider = _CapitalFlowProvider(
        insider_trades=[_insider(symbol="NVDA", securities_transacted=10_000, price=180.0)],
    )
    repo = _FakeCapitalFlowRepository()
    use_case = RunCapitalFlowScanUseCase(provider, repo)

    first_run = use_case.execute()
    second_run = use_case.execute()  # identical data, run again

    assert len(first_run) == 1
    assert len(second_run) == 0  # already seen, correctly not re-reported


def test_execute_degrades_gracefully_when_one_source_is_unavailable() -> None:
    """One source failing (e.g. FMP briefly down for Senate data)
    shouldn't block the other two from being scanned."""
    provider = _CapitalFlowProvider(
        insider_trades=[_insider(symbol="NVDA", securities_transacted=10_000, price=180.0)],
        house_trades=[_politician(chamber=CapitalFlowSource.HOUSE, symbol="GOOGL")],
        raise_on="senate",
    )
    repo = _FakeCapitalFlowRepository()
    use_case = RunCapitalFlowScanUseCase(provider, repo)

    result = use_case.execute()

    assert len(result) == 2
    sources = {e.source for e in result}
    assert sources == {CapitalFlowSource.INSIDER, CapitalFlowSource.HOUSE}


def test_execute_respects_custom_thresholds() -> None:
    provider = _CapitalFlowProvider(
        insider_trades=[_insider(symbol="NVDA", securities_transacted=100.0, price=100.0)],  # $10,000
    )
    repo = _FakeCapitalFlowRepository()
    use_case = RunCapitalFlowScanUseCase(provider, repo, insider_min_value_usd=5_000.0)

    result = use_case.execute()

    assert len(result) == 1  # would be filtered by the $1M default, but not the custom $5,000 bar


def test_execute_returns_empty_list_when_nothing_is_unusual() -> None:
    provider = _CapitalFlowProvider(insider_trades=[], senate_trades=[], house_trades=[])
    repo = _FakeCapitalFlowRepository()
    use_case = RunCapitalFlowScanUseCase(provider, repo)

    assert use_case.execute() == []


def _bar(bar_date, volume):
    from src.domain.entities.market_quote import PriceBar
    return PriceBar(bar_date=bar_date, close=100.0, volume=volume)


def test_execute_skips_volume_scan_entirely_when_no_ticker_universe_given() -> None:
    """The core, deliberate default: volume scanning never silently
    runs — a caller must explicitly opt in with a real ticker list."""
    provider = _CapitalFlowProvider(
        bars_by_ticker={"NVDA": [_bar(date(2026, 8, 7), 90_000_000)] + [_bar(date(2026, 8, 6), 30_000_000)] * 15},
    )
    repo = _FakeCapitalFlowRepository()
    use_case = RunCapitalFlowScanUseCase(provider, repo)  # no ticker_universe passed

    result = use_case.execute()

    assert result == []  # never scanned, even though NVDA data would clear the spike threshold


def test_execute_detects_a_real_volume_spike_when_universe_is_given() -> None:
    provider = _CapitalFlowProvider(
        bars_by_ticker={
            "NVDA": [_bar(date(2026, 8, 7), 90_000_000)] + [_bar(date(2026, 8, 6), 30_000_000)] * 15,
        },
    )
    repo = _FakeCapitalFlowRepository()
    use_case = RunCapitalFlowScanUseCase(provider, repo, ticker_universe=["NVDA"])

    result = use_case.execute()

    assert len(result) == 1
    assert result[0].symbol == "NVDA"
    assert "3.0x" in result[0].headline


def test_execute_skips_tickers_with_normal_volume() -> None:
    provider = _CapitalFlowProvider(
        bars_by_ticker={
            "AAPL": [_bar(date(2026, 8, 7), 31_000_000)] + [_bar(date(2026, 8, 6), 30_000_000)] * 15,
        },
    )
    repo = _FakeCapitalFlowRepository()
    use_case = RunCapitalFlowScanUseCase(provider, repo, ticker_universe=["AAPL"])

    assert use_case.execute() == []


def test_execute_degrades_gracefully_when_one_tickers_volume_data_fails() -> None:
    """One ticker failing (delisted, thin data) shouldn't block the
    rest of the universe from being scanned — a real, isolated
    per-ticker failure, not a global one."""
    provider = _CapitalFlowProvider(
        bars_by_ticker={
            "NVDA": [_bar(date(2026, 8, 7), 90_000_000)] + [_bar(date(2026, 8, 6), 30_000_000)] * 15,
        },
        fail_tickers={"BROKEN"},
    )
    repo = _FakeCapitalFlowRepository()
    use_case = RunCapitalFlowScanUseCase(provider, repo, ticker_universe=["BROKEN", "NVDA"])

    result = use_case.execute()

    assert len(result) == 1
    assert result[0].symbol == "NVDA"


class _FakeMacroHistoryProvider:
    def __init__(self, readings_by_series=None, raise_on_series=None):
        self._readings_by_series = readings_by_series or {}
        self._raise_on_series = raise_on_series or set()

    def get_series_history(self, series_id: str, limit: int = 24):
        if series_id in self._raise_on_series:
            raise NotImplementedError("not supported")
        return self._readings_by_series.get(series_id, [])[:limit]


def _macro_reading(value, as_of):
    from src.domain.entities.economic_indicator import EconomicIndicatorReading
    return EconomicIndicatorReading(name="TEST", as_of=as_of, value=value)


def test_execute_skips_macro_scan_entirely_when_no_series_given() -> None:
    """Same deliberate default as ticker_universe: never silently runs."""
    provider = _CapitalFlowProvider()
    fred = _FakeMacroHistoryProvider(
        readings_by_series={"TEST": [_macro_reading(150_000, date(2026, 4, 1)), _macro_reading(80_000, date(2026, 1, 1))]},
    )
    repo = _FakeCapitalFlowRepository()
    use_case = RunCapitalFlowScanUseCase(provider, repo, macro_history_provider=fred)  # no macro_series passed

    assert use_case.execute() == []


def test_execute_detects_a_real_macro_flow_change_when_series_given() -> None:
    provider = _CapitalFlowProvider()
    fred = _FakeMacroHistoryProvider(
        readings_by_series={"TEST": [_macro_reading(150_000, date(2026, 4, 1)), _macro_reading(80_000, date(2026, 1, 1))]},
    )
    repo = _FakeCapitalFlowRepository()
    use_case = RunCapitalFlowScanUseCase(
        provider, repo, macro_history_provider=fred, macro_series={"TEST": "Test Series"},
    )

    result = use_case.execute()

    assert len(result) == 1
    assert result[0].source == CapitalFlowSource.MACRO
    assert "+87.5%" in result[0].headline


def test_execute_skips_macro_series_with_small_changes() -> None:
    provider = _CapitalFlowProvider()
    fred = _FakeMacroHistoryProvider(
        readings_by_series={"TEST": [_macro_reading(100.0, date(2026, 4, 1)), _macro_reading(98.0, date(2026, 1, 1))]},
    )
    repo = _FakeCapitalFlowRepository()
    use_case = RunCapitalFlowScanUseCase(
        provider, repo, macro_history_provider=fred, macro_series={"TEST": "Test Series"},
    )

    assert use_case.execute() == []


def test_execute_reports_macro_unavailable_when_no_fred_provider_configured() -> None:
    """macro_series given but no macro_history_provider at all —
    should degrade gracefully, not crash."""
    provider = _CapitalFlowProvider()
    repo = _FakeCapitalFlowRepository()
    use_case = RunCapitalFlowScanUseCase(provider, repo, macro_series={"TEST": "Test Series"})

    assert use_case.execute() == []


def test_execute_skips_one_failing_series_without_blocking_others() -> None:
    provider = _CapitalFlowProvider()
    fred = _FakeMacroHistoryProvider(
        readings_by_series={
            "GOOD": [_macro_reading(150_000, date(2026, 4, 1)), _macro_reading(80_000, date(2026, 1, 1))],
        },
        raise_on_series={"BROKEN"},
    )
    repo = _FakeCapitalFlowRepository()
    use_case = RunCapitalFlowScanUseCase(
        provider, repo, macro_history_provider=fred,
        macro_series={"BROKEN": "Broken Series", "GOOD": "Good Series"},
    )

    result = use_case.execute()

    assert len(result) == 1
    assert "Good Series" in result[0].headline
