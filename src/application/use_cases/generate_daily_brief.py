"""Use case: generate a user's Daily Brief.

This is deliberately NOT a new data path — it composes four things that
already exist and are already tested independently:
  1. Watchlist price moves (reuses PriceSnapshotRepository from monitoring)
  2. Portfolio valuation (reuses ComputePortfolioValuationUseCase)
  3. Portfolio risk (reuses ComputePortfolioRiskUseCase)
  4. Unread alert count (reuses AlertRepository)

The LLM only ever sees the structured output of these four steps — it
never has an independent path to fetch data itself, same grounding
discipline as the Research Agent.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.application.interfaces.brief_generator import (
    BriefGenerationError,
    BriefGenerator,
)
from src.application.interfaces.data_provider import (
    DataProviderError,
    FinancialDataProvider,
)
from src.application.use_cases.compute_portfolio_risk import ComputePortfolioRiskUseCase
from src.application.use_cases.compute_portfolio_valuation import (
    ComputePortfolioValuationUseCase,
)
from src.domain.entities.daily_brief import (
    DailyBrief,
    PortfolioBriefSummary,
    WatchlistPriceMove,
)
from src.domain.repositories.monitoring_repository import (
    AlertRepository,
    PriceSnapshotRepository,
)
from src.domain.repositories.portfolio_repository import PortfolioRepository
from src.domain.repositories.watchlist_repository import WatchlistRepository

logger = logging.getLogger(__name__)


class GenerateDailyBriefUseCase:
    def __init__(
        self,
        watchlist_repo: WatchlistRepository,
        snapshot_repo: PriceSnapshotRepository,
        alert_repo: AlertRepository,
        portfolio_repo: PortfolioRepository,
        data_provider: FinancialDataProvider,
        compute_valuation: ComputePortfolioValuationUseCase,
        compute_risk: ComputePortfolioRiskUseCase,
        brief_generator: BriefGenerator,
    ) -> None:
        self._watchlist_repo = watchlist_repo
        self._snapshot_repo = snapshot_repo
        self._alert_repo = alert_repo
        self._portfolio_repo = portfolio_repo
        self._data_provider = data_provider
        self._compute_valuation = compute_valuation
        self._compute_risk = compute_risk
        self._brief_generator = brief_generator

    def execute(self, user_id: str) -> DailyBrief:
        watchlist_moves = self._build_watchlist_moves(user_id)
        portfolio_summaries = self._build_portfolio_summaries(user_id)
        unread_alert_count = len(self._alert_repo.list_for_user(user_id, unread_only=True))

        try:
            result = self._brief_generator.generate(
                watchlist_moves, portfolio_summaries, unread_alert_count
            )
        except BriefGenerationError:
            logger.exception("Brief generation failed for %s", user_id)
            raise

        return DailyBrief(
            user_id=user_id,
            generated_at=datetime.now(timezone.utc),
            narrative=result.narrative,
            model_used=result.model_used,
            unread_alert_count=unread_alert_count,
            watchlist_moves=watchlist_moves,
            portfolio_summaries=portfolio_summaries,
        )

    def _build_watchlist_moves(self, user_id: str) -> list[WatchlistPriceMove]:
        moves = []
        for item in self._watchlist_repo.list_for_user(user_id):
            try:
                quote = self._data_provider.get_quote(item.ticker)
            except DataProviderError:
                logger.warning("Brief: quote fetch failed for %s, skipping", item.ticker)
                continue

            prior = self._snapshot_repo.get_latest(item.ticker)
            change_pct = None
            prior_price = None
            if prior is not None and prior.price > 0:
                prior_price = prior.price
                change_pct = (quote.price - prior.price) / prior.price

            moves.append(
                WatchlistPriceMove(
                    ticker=item.ticker,
                    current_price=quote.price,
                    prior_price=prior_price,
                    change_pct=change_pct,
                )
            )
        return moves

    def _build_portfolio_summaries(self, user_id: str) -> list[PortfolioBriefSummary]:
        summaries = []
        for portfolio in self._portfolio_repo.list_for_user(user_id):
            full_portfolio = self._portfolio_repo.get_by_id(portfolio.portfolio_id)
            if full_portfolio is None or not full_portfolio.holdings:
                continue

            try:
                valuation = self._compute_valuation.execute(portfolio.portfolio_id)
                risk = self._compute_risk.execute(portfolio.portfolio_id)
            except DataProviderError:
                logger.warning(
                    "Brief: valuation/risk failed for portfolio %s, skipping",
                    portfolio.portfolio_id,
                )
                continue

            summaries.append(
                PortfolioBriefSummary(
                    portfolio_id=portfolio.portfolio_id,
                    name=portfolio.name,
                    total_market_value=valuation.total_market_value,
                    total_unrealized_gain_pct=valuation.total_unrealized_gain_pct,
                    largest_position_weight=risk.largest_position_weight,
                    herfindahl_index=risk.herfindahl_index,
                )
            )
        return summaries
