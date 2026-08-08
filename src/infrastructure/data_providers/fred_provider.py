"""FRED (St. Louis Fed) adapter for deep macro-history data.

Wire format verified directly against FRED's own actual API
documentation and multiple independent, working client-library
implementations (fetched, not guessed). The actual parsing logic
lives in fred_parsing.py, deliberately separated so it has no httpx
dependency and can be tested in isolation.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import httpx

from src.application.interfaces.macro_history_provider import (
    MacroHistoryProvider,
    MacroHistoryProviderError,
)
from src.domain.entities.economic_indicator import EconomicIndicatorReading
from src.infrastructure.config import Settings
from src.infrastructure.data_providers.fred_parsing import parse_series_observations

logger = logging.getLogger(__name__)


class FredProvider(MacroHistoryProvider):
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.Client(
            base_url=settings.fred_base_url,
            timeout=settings.fred_request_timeout_seconds,
        )

    def get_series_history(self, series_id: str, limit: int = 24) -> list[EconomicIndicatorReading]:
        # Deliberately using observation_start, not sort_order, to get
        # recent data: for a decades-deep series like UNRATE (data
        # back to 1948), a plain limit param with no sort_order applied
        # would return FRED's own default ascending order's FIRST N
        # rows — the OLDEST 24 observations from 1948, not the most
        # recent ones. observation_start sidesteps that risk entirely
        # by asking FRED to only consider recent history in the first
        # place, rather than depending on an unverified assumption
        # about how sort_order interacts with limit server-side.
        months_of_headroom = max(limit, 24) + 12
        start = date.today() - timedelta(days=31 * months_of_headroom)

        try:
            response = self._client.get(
                "/series/observations",
                params={
                    "series_id": series_id,
                    "api_key": self._settings.fred_api_key,
                    "file_type": "json",
                    "observation_start": start.isoformat(),
                },
            )
        except httpx.HTTPError as exc:
            raise MacroHistoryProviderError(f"FRED request failed for {series_id}: {exc}") from exc

        if response.status_code != 200:
            raise MacroHistoryProviderError(
                f"FRED returned {response.status_code} for {series_id}: {response.text}"
            )

        # parse_series_observations reverses FRED's own default
        # (ascending, oldest-first) order to this codebase's
        # most-recent-first convention — that exact path is the one
        # already tested, so no sort_order dependency needed anywhere
        # in this call.
        readings = parse_series_observations(response.json(), series_id)
        return readings[:limit]
