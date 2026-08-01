"""Use case: propose a from-scratch allocation across a list of
tickers using naive (inverse-volatility) risk parity.

This is the "Portfolio Construction" step of the professional workflow
— genuinely proposing an allocation, not just flagging an existing
portfolio's concentration (suggest_rebalancing already does that, and
remains separate and narrower). No expected-return assumption is
involved anywhere in this file — see portfolio_construction.py's
METHODOLOGY_NOTE for why.
"""
from __future__ import annotations

import logging
import statistics
from datetime import datetime, timezone

from src.application.interfaces.data_provider import (
    DataProviderError,
    FinancialDataProvider,
)
from src.domain.entities.portfolio_construction import (
    RiskParityAllocation,
    RiskParityConstructionResult,
)
from src.domain.services.portfolio_risk_math import (
    compute_simple_returns,
    inverse_volatility_weights,
)

logger = logging.getLogger(__name__)

LOOKBACK_TRADING_DAYS = 60
MIN_RETURN_OBSERVATIONS = 20


class NoTickersProvidedError(Exception):
    def __init__(self) -> None:
        super().__init__("No tickers were provided to allocate across.")


class InvalidInvestmentAmountError(Exception):
    def __init__(self, amount: float) -> None:
        super().__init__(f"total_investment must be positive, got {amount}.")


class NoAllocatableTickersError(Exception):
    def __init__(self) -> None:
        super().__init__(
            "None of the provided tickers had enough price history to "
            "compute a volatility-based allocation."
        )


class ConstructRiskParityPortfolioUseCase:
    def __init__(self, data_provider: FinancialDataProvider) -> None:
        self._data_provider = data_provider

    def execute(self, tickers: list[str], total_investment: float) -> RiskParityConstructionResult:
        if not tickers:
            raise NoTickersProvidedError()
        if total_investment <= 0:
            raise InvalidInvestmentAmountError(total_investment)

        tickers = [t.strip().upper() for t in tickers]
        volatility_by_ticker: dict[str, float] = {}
        price_by_ticker: dict[str, float] = {}
        excluded: list[str] = []

        for ticker in tickers:
            try:
                quote = self._data_provider.get_quote(ticker)
            except DataProviderError as exc:
                logger.warning("Risk parity: quote fetch failed for %s: %s", ticker, exc)
                excluded.append(ticker)
                continue

            if not hasattr(self._data_provider, "get_daily_closes"):
                excluded.append(ticker)
                continue
            try:
                bars = self._data_provider.get_daily_closes(ticker, limit=LOOKBACK_TRADING_DAYS + 1)
            except (NotImplementedError, DataProviderError) as exc:
                logger.warning("Risk parity: price history unavailable for %s: %s", ticker, exc)
                excluded.append(ticker)
                continue

            returns = compute_simple_returns([b.close for b in bars])
            if len(returns) < MIN_RETURN_OBSERVATIONS:
                excluded.append(ticker)
                continue

            variance = statistics.variance(returns)
            if variance <= 0:
                excluded.append(ticker)
                continue

            volatility_by_ticker[ticker] = variance ** 0.5
            price_by_ticker[ticker] = quote.price

        weights = inverse_volatility_weights(volatility_by_ticker)
        if not weights:
            raise NoAllocatableTickersError()

        allocations = []
        for ticker, weight in sorted(weights.items(), key=lambda kv: -kv[1]):
            target_dollars = total_investment * weight
            price = price_by_ticker[ticker]
            allocations.append(
                RiskParityAllocation(
                    ticker=ticker,
                    daily_volatility=volatility_by_ticker[ticker],
                    target_weight=weight,
                    target_dollar_amount=target_dollars,
                    current_price=price,
                    suggested_shares=target_dollars / price if price > 0 else 0.0,
                )
            )

        return RiskParityConstructionResult(
            as_of=datetime.now(timezone.utc),
            total_investment=total_investment,
            allocations=allocations,
            excluded=excluded,
        )
