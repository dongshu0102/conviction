"""Use case: generate an AI research report for a company.

Structurally enforces grounding: this use case fetches real financial
data via GetCompanyFinancialsUseCase FIRST, and the only way to reach
the LLM is by passing that data into ResearchGenerator.generate(). There
is no code path here that lets a report get generated without real,
ingested data behind it — if a company hasn't been ingested yet, this
use case fails loudly rather than letting the LLM improvise from
training-data recollection.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.application.interfaces.research_generator import (
    ResearchGenerationError,
    ResearchGenerator,
)
from src.application.use_cases.get_company_financials import (
    CompanyNotFoundError,
    GetCompanyFinancialsUseCase,
)
from src.domain.entities.research_report import CompanyResearchReport
from src.domain.repositories.research_report_repository import ResearchReportRepository

logger = logging.getLogger(__name__)


class NoFinancialDataError(Exception):
    """Raised when a company exists but has no ingested statements yet —
    distinct from CompanyNotFoundError (company doesn't exist at all).
    A research report grounded in zero financial data would just be the
    LLM's unverified recollection, which defeats the entire point.
    """

    def __init__(self, ticker: str) -> None:
        self.ticker = ticker
        super().__init__(
            f"'{ticker}' has a company profile but no ingested financial "
            f"statements — run ingestion before generating research."
        )


class GenerateCompanyResearchUseCase:
    def __init__(
        self,
        get_financials: GetCompanyFinancialsUseCase,
        research_generator: ResearchGenerator,
        report_repository: ResearchReportRepository,
    ) -> None:
        self._get_financials = get_financials
        self._research_generator = research_generator
        self._report_repository = report_repository

    def execute(self, ticker: str) -> CompanyResearchReport:
        ticker = ticker.strip().upper()

        try:
            financials = self._get_financials.execute(ticker)
        except CompanyNotFoundError:
            raise

        if not financials.income_statements:
            raise NoFinancialDataError(ticker)

        try:
            result = self._research_generator.generate(financials)
        except ResearchGenerationError:
            logger.exception("Research generation failed for %s", ticker)
            raise

        report = CompanyResearchReport(
            ticker=ticker,
            business_overview=result.business_overview,
            financial_highlights=result.financial_highlights,
            competitive_position=result.competitive_position,
            key_risks=result.key_risks,
            generated_at=datetime.now(timezone.utc),
            model_used=result.model_used,
            grounded_fiscal_year=financials.income_statements[0].key.fiscal_year,
            raw_response=result.raw_response,
        )
        self._report_repository.save(report)
        logger.info("Generated research report for %s (model=%s)", ticker, result.model_used)
        return report
