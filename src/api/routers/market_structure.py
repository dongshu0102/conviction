"""Market structure classification: a company's real, ingested
industry peers within this app's universe, classified into one of
the four classic microeconomic market structures (Perfect
Competition, Monopolistic Competition, Oligopoly, Monopoly) using the
real Herfindahl-Hirschman Index -- the actual U.S. DOJ/FTC metric for
market concentration, not an invented scoring scheme. Every category
is computed by exact, deterministic arithmetic before the LLM is ever
called; the LLM only explains an already-fixed classification through
real economic theory. See get_market_structure_classification.py's
own docstring for the full grounding discipline.

Deliberately on-demand, not persisted -- computed fresh on every
request, one ticker at a time, matching the same scope decision
already made for Master Lens.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from src.api.routers.companies import get_company_repository, get_statement_repository
from src.api.schemas import MarketStructureClassificationSchema
from src.application.interfaces.market_structure_narrative_generator import (
    MarketStructureGenerationError,
)
from src.application.use_cases.get_company_financials import (
    CompanyNotFoundError,
    GetCompanyFinancialsUseCase,
)
from src.application.use_cases.get_market_structure_classification import (
    GetMarketStructureClassificationUseCase,
)
from src.infrastructure.config import get_settings
from src.infrastructure.llm_providers.anthropic_market_structure_narrative_generator import (
    AnthropicMarketStructureNarrativeGenerator,
)
from src.infrastructure.persistence.company_repository_impl import SqlAlchemyCompanyRepository
from src.infrastructure.persistence.financial_statement_repository_impl import (
    SqlAlchemyFinancialStatementRepository,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/market-structure", tags=["market-structure"])


def get_market_structure_narrative_generator() -> AnthropicMarketStructureNarrativeGenerator:
    return AnthropicMarketStructureNarrativeGenerator(settings=get_settings())


def get_market_structure_use_case(
    company_repo: SqlAlchemyCompanyRepository = Depends(get_company_repository),
    statement_repo: SqlAlchemyFinancialStatementRepository = Depends(get_statement_repository),
    narrative_generator: AnthropicMarketStructureNarrativeGenerator = Depends(
        get_market_structure_narrative_generator
    ),
) -> GetMarketStructureClassificationUseCase:
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    return GetMarketStructureClassificationUseCase(company_repo, get_financials, narrative_generator)


@router.get("/{ticker}", response_model=MarketStructureClassificationSchema)
def get_market_structure_classification(
    ticker: str,
    use_case: GetMarketStructureClassificationUseCase = Depends(get_market_structure_use_case),
) -> MarketStructureClassificationSchema:
    try:
        result = use_case.execute(ticker)
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MarketStructureGenerationError as exc:
        logger.warning("Market structure narrative generation failed for %s: %s", ticker, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return MarketStructureClassificationSchema(
        ticker=result.ticker, industry=result.industry, category=result.category,
        hhi=result.hhi, company_market_share=result.company_market_share,
        peer_count=result.peer_count, narrative=result.narrative, model_used=result.model_used,
    )
