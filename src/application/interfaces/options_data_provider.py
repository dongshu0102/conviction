"""Contract for an options data provider.

Same Dependency Inversion pattern as FinancialDataProvider — the
application layer depends on this interface, never on MarketData.app's
specific columnar wire format directly. If we ever swap providers,
only the infrastructure adapter changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from src.domain.entities.option import OptionContract, OptionQuote


class OptionsDataProvider(ABC):
    @abstractmethod
    def get_option_chain(
        self, underlying_ticker: str, expiration: date | None = None
    ) -> list[OptionQuote]:
        """Fetch live quotes for an underlying's option chain. If
        expiration is given, restricts to that expiration only."""

    @abstractmethod
    def get_option_quote(self, contract: OptionContract) -> OptionQuote | None:
        """Fetch a live quote for one specific contract. Returns None
        if the contract doesn't exist or has no current quote."""


class OptionsDataProviderError(Exception):
    pass
