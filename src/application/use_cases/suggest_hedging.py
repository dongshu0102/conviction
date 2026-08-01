"""Use case: suggest mechanical delta hedges, per underlying.

Combines TWO sources of directional exposure: stock holdings (each
share has delta exactly 1.0, always — no live quote needed) and option
holdings' live delta. This is the actual "net exposure" a real hedge
needs to know — hedging only the options side while ignoring an
offsetting or compounding stock position on the same ticker would be a
real correctness bug, not just an incomplete feature.

Deterministic: the suggested share count is exact arithmetic (the
amount that brings net delta to precisely zero), never an LLM estimate.
Positions below `delta_threshold` are skipped — not every small
exposure is worth a suggested trade.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.application.interfaces.options_data_provider import OptionsDataProvider
from src.application.use_cases.manage_portfolio import PortfolioNotFoundError
from src.domain.entities.option import HedgeSuggestion, HedgingPlan
from src.domain.repositories.portfolio_repository import PortfolioRepository

CONTRACT_MULTIPLIER = 100  # standard: 1 option contract = 100 shares of the underlying
DEFAULT_DELTA_THRESHOLD = 10.0  # net exposure below this (in share-equivalents) isn't worth hedging


class SuggestHedgingUseCase:
    def __init__(
        self,
        portfolio_repo: PortfolioRepository,
        options_provider: OptionsDataProvider,
        delta_threshold: float = DEFAULT_DELTA_THRESHOLD,
    ) -> None:
        self._portfolio_repo = portfolio_repo
        self._options_provider = options_provider
        self._delta_threshold = delta_threshold

    def execute(self, portfolio_id: str) -> HedgingPlan:
        portfolio = self._portfolio_repo.get_by_id(portfolio_id)
        if portfolio is None:
            raise PortfolioNotFoundError(portfolio_id)

        # Stock delta is exact and needs no live quote — 1 share = 1.0 delta, always.
        stock_delta_by_ticker: dict[str, float] = {
            h.ticker: h.shares for h in portfolio.holdings
        }

        option_delta_by_ticker: dict[str, float] = {}
        excluded: list[str] = []
        for holding in portfolio.option_holdings:
            quote = self._options_provider.get_option_quote(holding.contract)
            if quote is None or quote.delta is None:
                excluded.append(holding.contract.occ_symbol_fragment)
                continue
            ticker = holding.contract.underlying_ticker
            contribution = quote.delta * holding.contracts_held * CONTRACT_MULTIPLIER
            option_delta_by_ticker[ticker] = option_delta_by_ticker.get(ticker, 0.0) + contribution

        all_tickers = set(stock_delta_by_ticker) | set(option_delta_by_ticker)
        suggestions: list[HedgeSuggestion] = []
        for ticker in all_tickers:
            net_delta = stock_delta_by_ticker.get(ticker, 0.0) + option_delta_by_ticker.get(
                ticker, 0.0
            )
            if abs(net_delta) < self._delta_threshold:
                continue  # exposure too small to bother hedging

            shares_to_trade = -net_delta  # exact amount that zeroes out net delta
            suggestions.append(
                HedgeSuggestion(
                    underlying_ticker=ticker,
                    net_delta=net_delta,
                    shares_to_trade=shares_to_trade,
                    resulting_delta=net_delta + shares_to_trade,
                )
            )

        # Largest exposure first — the most impactful hedge is the most
        # relevant thing to lead with, same convention as suggest_rebalancing.
        suggestions.sort(key=lambda s: abs(s.net_delta), reverse=True)

        return HedgingPlan(
            portfolio_id=portfolio_id,
            as_of=datetime.now(timezone.utc),
            suggestions=suggestions,
            positions_excluded=excluded,
        )
