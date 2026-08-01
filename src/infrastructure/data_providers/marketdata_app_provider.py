"""MarketData.app adapter for options data.

Wire format verified directly against MarketData.app's actual API
documentation (fetched, not guessed). The actual parsing logic lives
in marketdata_parsing.py, deliberately separated so it has no httpx
dependency and can be tested in isolation.
"""
from __future__ import annotations

import logging
from datetime import date

import httpx

from src.application.interfaces.options_data_provider import (
    OptionsDataProvider,
    OptionsDataProviderError,
)
from src.domain.entities.option import OptionContract, OptionQuote
from src.infrastructure.config import Settings
from src.infrastructure.data_providers.marketdata_parsing import parse_option_chain_response

logger = logging.getLogger(__name__)

# MarketData.app returns 203 for cache-tier responses — identical body
# shape to 200, just a different status. Both must be treated as
# success; this was confirmed directly from their docs, not assumed.
_SUCCESS_STATUS_CODES = (200, 203)


class MarketDataAppProvider(OptionsDataProvider):
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.Client(
            base_url="https://api.marketdata.app/v1",
            headers={"Authorization": f"Bearer {settings.marketdata_api_key}"},
            timeout=30.0,
        )

    def get_option_chain(
        self, underlying_ticker: str, expiration: date | None = None
    ) -> list[OptionQuote]:
        params = {"feed": "cached"}  # Cached Mode — 1 credit per call regardless of chain size
        if expiration:
            params["from"] = expiration.isoformat()
            params["to"] = expiration.isoformat()

        try:
            response = self._client.get(
                f"/options/chain/{underlying_ticker}/", params=params
            )
        except httpx.HTTPError as exc:
            raise OptionsDataProviderError(
                f"MarketData.app request failed for {underlying_ticker}: {exc}"
            ) from exc

        if response.status_code not in _SUCCESS_STATUS_CODES:
            raise OptionsDataProviderError(
                f"MarketData.app returned {response.status_code} for {underlying_ticker}: {response.text}"
            )

        return parse_option_chain_response(response.json())

    def get_option_quote(self, contract: OptionContract) -> OptionQuote | None:
        chain = self.get_option_chain(contract.underlying_ticker, contract.expiration)
        for quote in chain:
            if (
                quote.contract.strike == contract.strike
                and quote.contract.option_type == contract.option_type
            ):
                return quote
        return None
