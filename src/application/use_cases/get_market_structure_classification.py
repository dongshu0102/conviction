"""Use case: classify a company's real market structure using its own
real, ingested industry peers within this app's universe.

Structurally enforces the same grounding discipline as Master Lens:
real peer companies and their real, latest revenue are fetched FIRST,
HHI and the classification itself are computed by exact, deterministic
arithmetic (never by the LLM), and only THEN is the LLM called -- to
explain that already-fixed classification through real economic
theory, never to invent or override it.
"""
from __future__ import annotations

from src.application.interfaces.market_structure_narrative_generator import (
    MarketStructureGenerationError,
    MarketStructureNarrativeGenerator,
)
from src.application.use_cases.get_company_financials import (
    CompanyNotFoundError,
    GetCompanyFinancialsUseCase,
)
from src.domain.entities.market_structure import MarketStructureClassification
from src.domain.repositories.company_repository import CompanyRepository
from src.domain.services.market_structure_scoring import (
    classify_market_structure,
    compute_hhi,
    compute_market_shares,
)


def _latest_revenue(get_financials: GetCompanyFinancialsUseCase, ticker: str) -> float | None:
    try:
        financials = get_financials.execute(ticker, years=1)
    except CompanyNotFoundError:
        return None
    if not financials.income_statements:
        return None
    return financials.income_statements[-1].revenue


class GetMarketStructureClassificationUseCase:
    def __init__(
        self,
        company_repository: CompanyRepository,
        get_financials: GetCompanyFinancialsUseCase,
        narrative_generator: MarketStructureNarrativeGenerator,
    ) -> None:
        self._company_repository = company_repository
        self._get_financials = get_financials
        self._narrative_generator = narrative_generator

    def execute(self, ticker: str) -> MarketStructureClassification:
        ticker = ticker.strip().upper()

        company = self._company_repository.get_by_ticker(ticker)
        if company is None:
            raise CompanyNotFoundError(ticker)

        # Every real, ingested company sharing this exact industry
        # string -- including the target company itself, since its own
        # revenue is part of the real, total group revenue the shares
        # are computed against.
        peers = [c for c in self._company_repository.list_all() if c.industry == company.industry]

        revenues: dict[str, float] = {}
        for peer in peers:
            revenue = _latest_revenue(self._get_financials, peer.ticker)
            if revenue is not None:
                revenues[peer.ticker] = revenue

        market_shares = compute_market_shares(revenues)
        hhi = compute_hhi(market_shares) if market_shares else None
        company_share = market_shares.get(ticker)
        peer_count = len(market_shares)

        category = classify_market_structure(hhi, company_share, peer_count)

        peer_tickers = sorted(t for t in market_shares if t != ticker)

        try:
            narrative_result = self._narrative_generator.generate(
                ticker, company.industry, category, hhi, company_share, peer_count, peer_tickers,
            )
        except MarketStructureGenerationError:
            raise

        return MarketStructureClassification(
            ticker=ticker, industry=company.industry, category=category,
            hhi=hhi, company_market_share=company_share, peer_count=peer_count,
            narrative=narrative_result.narrative, model_used=narrative_result.model_used,
        )
