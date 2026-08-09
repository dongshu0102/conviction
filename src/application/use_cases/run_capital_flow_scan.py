"""Use case: run a capital-flow scan.

Fetches the latest insider-trading and political-disclosure feeds,
filters each down to genuinely unusual events (capital_flow_math.py),
and persists only the ones not already seen. A broad, market-wide
scan — no watchlist, no per-user scoping — matching the explicit
"scan broadly, any ticker" design decision made when this feature was
scoped, not the per-user pattern RunMonitoringCheckUseCase uses.

Volume scanning is genuinely different in cost from the other two
sources: insider/political trading are each ONE API call covering the
whole market, while volume data is fetched per-ticker — scanning even
the S&P 500 means 500 real calls. ticker_universe therefore defaults
to None, meaning volume scanning is skipped entirely unless a caller
explicitly opts in with a real list of tickers — never silently
defaulted to "all 500," which would be a real, meaningful rate-limit
and cost decision made on the caller's behalf without their consent.

Macro flow scanning needs a real, separate MacroHistoryProvider (FRED)
dependency — same optional-provider pattern GetRateSignalsUseCase
already uses for the Sahm Rule — and an explicit macro_series mapping
of {series_id: human label}, since there's no sensible universal
default list of "the" macro-flow series to watch.

Each source is fetched and processed independently and allowed to
fail on its own: FMP being briefly unavailable for Senate data
shouldn't block insider trades from being scanned. A source that
fails is logged and skipped for that run, not fatal to the whole scan.
"""
from __future__ import annotations

import logging

from src.application.interfaces.data_provider import DataProviderError, FinancialDataProvider
from src.application.interfaces.macro_history_provider import (
    MacroHistoryProvider,
    MacroHistoryProviderError,
)
from src.domain.entities.capital_flow import CapitalFlowEvent
from src.domain.repositories.capital_flow_repository import CapitalFlowRepository
from src.domain.services.capital_flow_math import (
    build_insider_event,
    build_macro_flow_event,
    build_politician_event,
    build_volume_event,
)

logger = logging.getLogger(__name__)

# How many of the most recent rows to pull per source, per run. Not the
# same thing as how many clear the "unusual" threshold — most rows in
# each raw feed are filtered out by capital_flow_math.py long before
# persistence.
DEFAULT_FETCH_LIMIT = 100

# How many trading days of bars to fetch per ticker for volume
# scanning — needs to comfortably exceed capital_flow_math.py's own
# MIN_PRIOR_DAYS_REQUIRED + 1 (today), with some headroom.
DEFAULT_VOLUME_BARS_LIMIT = 30


class RunCapitalFlowScanUseCase:
    def __init__(
        self,
        data_provider: FinancialDataProvider,
        capital_flow_repo: CapitalFlowRepository,
        fetch_limit: int = DEFAULT_FETCH_LIMIT,
        insider_min_value_usd: float | None = None,
        politician_min_value_usd: float | None = None,
        ticker_universe: list[str] | None = None,
        volume_spike_multiple: float | None = None,
        macro_history_provider: MacroHistoryProvider | None = None,
        macro_series: dict[str, str] | None = None,
        macro_change_threshold: float | None = None,
    ) -> None:
        self._data_provider = data_provider
        self._capital_flow_repo = capital_flow_repo
        self._fetch_limit = fetch_limit
        self._insider_min_value_usd = insider_min_value_usd
        self._politician_min_value_usd = politician_min_value_usd
        self._ticker_universe = ticker_universe
        self._volume_spike_multiple = volume_spike_multiple
        self._macro_history_provider = macro_history_provider
        self._macro_series = macro_series
        self._macro_change_threshold = macro_change_threshold

    def execute(self) -> list[CapitalFlowEvent]:
        candidate_events: list[CapitalFlowEvent] = []
        candidate_events.extend(self._scan_insider())
        candidate_events.extend(self._scan_senate())
        candidate_events.extend(self._scan_house())
        if self._ticker_universe:
            candidate_events.extend(self._scan_volume())
        if self._macro_series:
            candidate_events.extend(self._scan_macro())

        # save_new_events is the single dedup+persist operation — see
        # CapitalFlowRepository's own docstring for why this isn't
        # split into a separate check-then-save.
        return self._capital_flow_repo.save_new_events(candidate_events)

    def _scan_insider(self) -> list[CapitalFlowEvent]:
        try:
            trades = self._data_provider.get_latest_insider_trades(limit=self._fetch_limit)
        except (DataProviderError, NotImplementedError) as exc:
            logger.warning("Capital flow scan: insider trades unavailable: %s", exc)
            return []

        kwargs = {} if self._insider_min_value_usd is None else {"min_value_usd": self._insider_min_value_usd}
        events = [build_insider_event(t, **kwargs) for t in trades]
        return [e for e in events if e is not None]

    def _scan_senate(self) -> list[CapitalFlowEvent]:
        try:
            trades = self._data_provider.get_latest_senate_trades(limit=self._fetch_limit)
        except (DataProviderError, NotImplementedError) as exc:
            logger.warning("Capital flow scan: Senate trades unavailable: %s", exc)
            return []

        kwargs = {} if self._politician_min_value_usd is None else {"min_value_usd": self._politician_min_value_usd}
        events = [build_politician_event(t, **kwargs) for t in trades]
        return [e for e in events if e is not None]

    def _scan_house(self) -> list[CapitalFlowEvent]:
        try:
            trades = self._data_provider.get_latest_house_trades(limit=self._fetch_limit)
        except (DataProviderError, NotImplementedError) as exc:
            logger.warning("Capital flow scan: House trades unavailable: %s", exc)
            return []

        kwargs = {} if self._politician_min_value_usd is None else {"min_value_usd": self._politician_min_value_usd}
        events = [build_politician_event(t, **kwargs) for t in trades]
        return [e for e in events if e is not None]

    def _scan_volume(self) -> list[CapitalFlowEvent]:
        events: list[CapitalFlowEvent] = []
        volume_kwargs = {} if self._volume_spike_multiple is None else {"spike_multiple": self._volume_spike_multiple}

        for ticker in self._ticker_universe:
            try:
                bars = self._data_provider.get_daily_bars_full(ticker, limit=DEFAULT_VOLUME_BARS_LIMIT)
            except (DataProviderError, NotImplementedError) as exc:
                # One ticker's volume data being unavailable is routine
                # (delisted, thinly-traded, a real transient vendor
                # gap) — logged and skipped, never fatal to the rest
                # of the universe being scanned.
                logger.warning("Capital flow scan: volume data unavailable for %s: %s", ticker, exc)
                continue

            if not bars or bars[0].volume is None:
                continue

            volumes = [b.volume for b in bars if b.volume is not None]
            event = build_volume_event(ticker, bars[0].bar_date, volumes, **volume_kwargs)
            if event is not None:
                events.append(event)

        return events

    def _scan_macro(self) -> list[CapitalFlowEvent]:
        if self._macro_history_provider is None:
            logger.warning("Capital flow scan: macro_series given but no FRED provider configured")
            return []

        macro_kwargs = {} if self._macro_change_threshold is None else {"change_threshold": self._macro_change_threshold}
        events: list[CapitalFlowEvent] = []

        for series_id, label in self._macro_series.items():
            try:
                readings = self._macro_history_provider.get_series_history(series_id, limit=2)
            except (MacroHistoryProviderError, NotImplementedError) as exc:
                logger.warning("Capital flow scan: FRED series %s unavailable: %s", series_id, exc)
                continue

            if len(readings) < 2:
                # Not enough history to compute a real change for this
                # series yet — logged and skipped, never a fabricated
                # single-reading "change."
                continue

            event = build_macro_flow_event(series_id, label, readings[0], readings[1], **macro_kwargs)
            if event is not None:
                events.append(event)

        return events
