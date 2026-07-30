from __future__ import annotations

from sqlalchemy import select

from src.domain.entities.research_report import CompanyResearchReport
from src.domain.repositories.research_report_repository import ResearchReportRepository
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import ResearchReportModel


def _to_domain(row: ResearchReportModel) -> CompanyResearchReport:
    return CompanyResearchReport(
        ticker=row.ticker,
        business_overview=row.business_overview,
        financial_highlights=row.financial_highlights,
        competitive_position=row.competitive_position,
        key_risks=row.key_risks,
        generated_at=row.generated_at,
        model_used=row.model_used,
        grounded_fiscal_year=row.grounded_fiscal_year,
        raw_response=row.raw_response or {},
    )


class SqlAlchemyResearchReportRepository(ResearchReportRepository):
    def save(self, report: CompanyResearchReport) -> None:
        with session_scope() as session:
            session.add(
                ResearchReportModel(
                    ticker=report.ticker,
                    business_overview=report.business_overview,
                    financial_highlights=report.financial_highlights,
                    competitive_position=report.competitive_position,
                    key_risks=report.key_risks,
                    model_used=report.model_used,
                    grounded_fiscal_year=report.grounded_fiscal_year,
                    raw_response=report.raw_response,
                    generated_at=report.generated_at,
                )
            )

    def get_latest(self, ticker: str) -> CompanyResearchReport | None:
        with session_scope() as session:
            row = session.execute(
                select(ResearchReportModel)
                .where(ResearchReportModel.ticker == ticker.strip().upper())
                .order_by(ResearchReportModel.generated_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            return _to_domain(row) if row else None

    def list_history(self, ticker: str, limit: int = 10) -> list[CompanyResearchReport]:
        with session_scope() as session:
            rows = session.execute(
                select(ResearchReportModel)
                .where(ResearchReportModel.ticker == ticker.strip().upper())
                .order_by(ResearchReportModel.generated_at.desc())
                .limit(limit)
            ).scalars().all()
            return [_to_domain(row) for row in rows]
