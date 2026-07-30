from __future__ import annotations

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from src.api.routers.companies import get_company_repository, get_statement_repository
from src.api.schemas import ResearchReportSchema
from src.application.interfaces.research_generator import ResearchGenerationError
from src.application.use_cases.generate_company_research import (
    GenerateCompanyResearchUseCase,
    NoFinancialDataError,
)
from src.application.use_cases.get_company_financials import (
    CompanyNotFoundError,
    GetCompanyFinancialsUseCase,
)
from src.infrastructure.config import get_settings
from src.infrastructure.llm_providers.anthropic_research_generator import (
    AnthropicResearchGenerator,
)
from src.infrastructure.persistence.company_repository_impl import SqlAlchemyCompanyRepository
from src.infrastructure.persistence.financial_statement_repository_impl import (
    SqlAlchemyFinancialStatementRepository,
)
from src.infrastructure.persistence.research_report_repository_impl import (
    SqlAlchemyResearchReportRepository,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/companies", tags=["research"])


def get_research_report_repository() -> SqlAlchemyResearchReportRepository:
    return SqlAlchemyResearchReportRepository()


def get_research_generator() -> AnthropicResearchGenerator:
    return AnthropicResearchGenerator(settings=get_settings())


def get_generate_research_use_case(
    company_repo: SqlAlchemyCompanyRepository = Depends(get_company_repository),
    statement_repo: SqlAlchemyFinancialStatementRepository = Depends(get_statement_repository),
    research_generator: AnthropicResearchGenerator = Depends(get_research_generator),
    report_repo: SqlAlchemyResearchReportRepository = Depends(get_research_report_repository),
) -> GenerateCompanyResearchUseCase:
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    return GenerateCompanyResearchUseCase(get_financials, research_generator, report_repo)


def _to_schema(report) -> ResearchReportSchema:
    return ResearchReportSchema(
        ticker=report.ticker,
        business_overview=report.business_overview,
        financial_highlights=report.financial_highlights,
        competitive_position=report.competitive_position,
        key_risks=report.key_risks,
        generated_at=report.generated_at,
        model_used=report.model_used,
        grounded_fiscal_year=report.grounded_fiscal_year,
    )


@router.post("/{ticker}/research", response_model=ResearchReportSchema)
def generate_research(
    ticker: str,
    use_case: GenerateCompanyResearchUseCase = Depends(get_generate_research_use_case),
) -> ResearchReportSchema:
    try:
        report = use_case.execute(ticker)
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NoFinancialDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ResearchGenerationError as exc:
        logger.warning("Research generation failed for %s: %s", ticker, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _to_schema(report)


@router.get("/{ticker}/research", response_model=ResearchReportSchema)
def get_latest_research(
    ticker: str,
    report_repo: SqlAlchemyResearchReportRepository = Depends(get_research_report_repository),
) -> ResearchReportSchema:
    report = report_repo.get_latest(ticker)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"No research report exists for '{ticker.upper()}' yet — "
            f"POST to this endpoint to generate one.",
        )
    return _to_schema(report)
