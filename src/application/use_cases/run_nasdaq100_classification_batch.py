"""Use case: compute all six real screener dimensions for every real
Nasdaq-100 company and store them as a batch.

Deliberately not on-demand -- ~100 companies, each needing a real LLM
call (for value chain/business model) plus peer discovery for HHI,
would be genuinely too slow and expensive to run per screener request.
This runs as a background/batch job, matching the same reasoning as
the Conviction Screener's own full-universe scan.

Reuses GetMarketStructureClassificationUseCase's own real peer-revenue
lookup logic (_latest_revenue) directly rather than reimplementing it,
and the same market_structure_scoring functions it's built on -- but
never calls the market structure NARRATIVE generator here, since a
batch of ~100 companies has no use for 100 individual LLM-written
paragraphs; only the real, deterministic category and HHI number are
stored.

Continues past any single ticker's own failure rather than aborting
the whole batch -- one company's LLM classification failing, or having
too few real peers for HHI, should never prevent every other company
from getting its own, real, correct row for the OTHER five dimensions.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.application.interfaces.nasdaq100_classifier import (
    Nasdaq100ClassificationError,
    Nasdaq100Classifier,
)
from src.application.use_cases.compute_financial_analysis import ComputeFinancialAnalysisUseCase
from src.application.use_cases.compute_valuation import ComputeValuationUseCase
from src.application.use_cases.get_company_financials import GetCompanyFinancialsUseCase
from src.application.use_cases.get_market_structure_classification import _latest_revenue
from src.domain.entities.nasdaq100_classification import Nasdaq100Classification
from src.domain.repositories.company_repository import CompanyRepository
from src.domain.repositories.index_membership_repository import IndexMembershipRepository
from src.domain.repositories.nasdaq100_classification_repository import (
    Nasdaq100ClassificationRepository,
)
from src.domain.services.market_structure_scoring import (
    classify_market_structure,
    compute_hhi,
    compute_market_shares,
)
from src.domain.services.nasdaq100_tier_scoring import (
    classify_market_cap_tier,
    classify_maturity_stage,
)

logger = logging.getLogger(__name__)

_NASDAQ_100_INDEX_NAME = "Nasdaq-100"


class RunNasdaq100ClassificationBatchUseCase:
    def __init__(
        self,
        company_repository: CompanyRepository,
        index_membership_repository: IndexMembershipRepository,
        classification_repository: Nasdaq100ClassificationRepository,
        get_financials: GetCompanyFinancialsUseCase,
        compute_financial_analysis: ComputeFinancialAnalysisUseCase,
        compute_valuation: ComputeValuationUseCase,
        classifier: Nasdaq100Classifier,
    ) -> None:
        self._company_repository = company_repository
        self._index_membership_repository = index_membership_repository
        self._classification_repository = classification_repository
        self._get_financials = get_financials
        self._compute_financial_analysis = compute_financial_analysis
        self._compute_valuation = compute_valuation
        self._classifier = classifier

    def _find_nasdaq100_companies(self) -> list:
        all_companies = self._company_repository.list_all()
        memberships = self._index_membership_repository.get_memberships_for_tickers(
            [c.ticker for c in all_companies]
        )
        return [c for c in all_companies if _NASDAQ_100_INDEX_NAME in memberships.get(c.ticker, [])]

    def _compute_market_structure(self, company) -> tuple[str | None, float | None]:
        peers = [c for c in self._company_repository.list_all() if c.industry == company.industry]
        revenues: dict[str, float] = {}
        for peer in peers:
            revenue = _latest_revenue(self._get_financials, peer.ticker)
            if revenue is not None:
                revenues[peer.ticker] = revenue

        market_shares = compute_market_shares(revenues)
        hhi = compute_hhi(market_shares) if market_shares else None
        company_share = market_shares.get(company.ticker)
        peer_count = len(market_shares)
        category = classify_market_structure(hhi, company_share, peer_count)
        return category, hhi

    def execute(self) -> tuple[int, int]:
        """Returns (succeeded_count, failed_count). A ticker "failing"
        here means it was skipped entirely for this run (e.g. an
        unexpected error) -- its prior row, if any, is left untouched
        until this refresh's save_batch call replaces the whole table,
        at which point a persistently-failing ticker would genuinely,
        correctly disappear rather than show a silently stale row."""
        companies = self._find_nasdaq100_companies()
        as_of = datetime.now(timezone.utc)
        results: list[Nasdaq100Classification] = []
        failed = 0

        for company in companies:
            try:
                market_structure_category, hhi = self._compute_market_structure(company)

                market_cap_tier = None
                market_cap = None
                try:
                    valuation = self._compute_valuation.execute(company.ticker)
                    market_cap = valuation.market_cap
                    market_cap_tier = classify_market_cap_tier(market_cap)
                except Exception as exc:
                    logger.warning("%s: couldn't compute valuation: %s", company.ticker, exc)

                maturity_stage = None
                revenue_growth = None
                try:
                    analysis = self._compute_financial_analysis.execute(company.ticker, years=2)
                    if analysis.yearly_ratios:
                        revenue_growth = analysis.yearly_ratios[-1].revenue_growth_yoy
                        maturity_stage = classify_maturity_stage(revenue_growth)
                except Exception as exc:
                    logger.warning("%s: couldn't compute financial analysis: %s", company.ticker, exc)

                value_chain_position = None
                business_model = None
                try:
                    classification = self._classifier.classify(
                        company.ticker, company.name, company.industry, company.description,
                    )
                    value_chain_position = classification.value_chain_position
                    business_model = classification.business_model
                except Nasdaq100ClassificationError as exc:
                    logger.warning("%s: LLM classification failed: %s", company.ticker, exc)

                results.append(Nasdaq100Classification(
                    ticker=company.ticker, as_of=as_of, industry=company.industry,
                    market_structure_category=market_structure_category, hhi=hhi,
                    value_chain_position=value_chain_position, business_model=business_model,
                    market_cap_tier=market_cap_tier, maturity_stage=maturity_stage,
                    market_cap=market_cap, revenue_growth=revenue_growth,
                ))
            except Exception as exc:
                logger.warning("%s: skipped entirely for this batch run: %s", company.ticker, exc)
                failed += 1

        self._classification_repository.save_batch(results)
        return len(results), failed
