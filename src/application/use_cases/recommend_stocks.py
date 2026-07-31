"""Use case: recommend stocks to fill real gaps in a portfolio.

Two-stage composition, no new business logic beyond the gap-finding
itself:
  1. Find sectors the portfolio is under-exposed to (real computation,
     using ComputePortfolioRiskUseCase's already-computed sector
     exposures — not a guess).
  2. Source real candidates for those sectors from the ingested company
     universe, then rank them via ScreenStocksUseCase (the exact same
     deterministic value/quality scoring already built and tested).

Bounded the same way ScreenStocksUseCase is — a handful of candidates
per gap sector, not the whole universe, for the same reason (each
candidate needs a live valuation lookup).
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.application.use_cases.compute_portfolio_risk import ComputePortfolioRiskUseCase
from src.application.use_cases.screen_stocks import ScreenStocksUseCase
from src.domain.entities.company import Sector
from src.domain.entities.recommendation import RecommendationResult, SectorGapPick
from src.domain.repositories.company_repository import CompanyRepository

DEFAULT_LOW_EXPOSURE_THRESHOLD = 0.05  # under 5% of the portfolio counts as a "gap"
CANDIDATES_PER_SECTOR = 5  # kept small — each candidate needs a live valuation lookup
MAX_GAP_SECTORS_CONSIDERED = 3  # cap total candidates screened per call


class RecommendStocksUseCase:
    def __init__(
        self,
        compute_risk: ComputePortfolioRiskUseCase,
        company_repo: CompanyRepository,
        screen_stocks: ScreenStocksUseCase,
    ) -> None:
        self._compute_risk = compute_risk
        self._company_repo = company_repo
        self._screen_stocks = screen_stocks

    def execute(
        self, portfolio_id: str, max_recommendations: int = 5
    ) -> RecommendationResult:
        risk = self._compute_risk.execute(portfolio_id)
        exposed: dict[str, float] = {e.sector: e.weight for e in risk.sector_exposures}

        all_sectors = [s.value for s in Sector if s != Sector.UNKNOWN]
        gap_sectors = [
            s for s in all_sectors if exposed.get(s, 0.0) < DEFAULT_LOW_EXPOSURE_THRESHOLD
        ][:MAX_GAP_SECTORS_CONSIDERED]

        if not gap_sectors:
            return RecommendationResult(
                portfolio_id=portfolio_id,
                as_of=datetime.now(timezone.utc),
                gap_sectors=[],
                picks=[],
            )

        companies = self._company_repo.list_all()
        candidates_by_sector: dict[str, list[str]] = {}
        for sector in gap_sectors:
            tickers = [c.ticker for c in companies if c.sector.value == sector][
                :CANDIDATES_PER_SECTOR
            ]
            if tickers:
                candidates_by_sector[sector] = tickers

        all_candidates = [t for tickers in candidates_by_sector.values() for t in tickers]
        if not all_candidates:
            return RecommendationResult(
                portfolio_id=portfolio_id,
                as_of=datetime.now(timezone.utc),
                gap_sectors=gap_sectors,
                picks=[],
            )

        screen_result = self._screen_stocks.execute(all_candidates)

        # Map each screened result back to whichever gap sector it came from
        ticker_to_sector = {t: s for s, tickers in candidates_by_sector.items() for t in tickers}

        picks = [
            SectorGapPick(
                stock=stock,
                gap_sector=ticker_to_sector.get(stock.ticker, "Unknown"),
                current_sector_weight=exposed.get(ticker_to_sector.get(stock.ticker, ""), 0.0),
            )
            for stock in screen_result.results[:max_recommendations]
        ]

        return RecommendationResult(
            portfolio_id=portfolio_id,
            as_of=datetime.now(timezone.utc),
            gap_sectors=gap_sectors,
            picks=picks,
        )
