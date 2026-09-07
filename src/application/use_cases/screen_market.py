"""Use case: screen the real, whole market by structural criteria
(market cap, sector, industry, price, beta, dividend, volume,
exchange) -- the "which stocks?" entry point ScreenStocksUseCase
(the value/quality screen on a caller-supplied set) is meant to
run on afterward.

A simple, direct pass-through to the provider -- FMP's own server-side
screener does the real filtering across the whole market in a single
call, so there's no client-side business logic to add here beyond the
Dependency Inversion boundary itself.
"""
from __future__ import annotations

from src.application.interfaces.data_provider import FinancialDataProvider
from src.domain.entities.market_screen import MarketScreenCandidate


class ScreenMarketUseCase:
    def __init__(self, provider: FinancialDataProvider) -> None:
        self._provider = provider

    def execute(
        self,
        sector: str | None = None,
        industry: str | None = None,
        exchange: str | None = None,
        country: str | None = None,
        market_cap_more_than: float | None = None,
        market_cap_lower_than: float | None = None,
        price_more_than: float | None = None,
        price_lower_than: float | None = None,
        beta_more_than: float | None = None,
        beta_lower_than: float | None = None,
        dividend_more_than: float | None = None,
        dividend_lower_than: float | None = None,
        volume_more_than: float | None = None,
        volume_lower_than: float | None = None,
        limit: int = 50,
    ) -> list[MarketScreenCandidate]:
        return self._provider.screen_market(
            sector=sector, industry=industry, exchange=exchange, country=country,
            market_cap_more_than=market_cap_more_than, market_cap_lower_than=market_cap_lower_than,
            price_more_than=price_more_than, price_lower_than=price_lower_than,
            beta_more_than=beta_more_than, beta_lower_than=beta_lower_than,
            dividend_more_than=dividend_more_than, dividend_lower_than=dividend_lower_than,
            volume_more_than=volume_more_than, volume_lower_than=volume_lower_than,
            limit=limit,
        )
