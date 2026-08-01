from __future__ import annotations

from sqlalchemy import select

from src.domain.entities.company import AssetType, Company, Sector
from src.domain.repositories.company_repository import CompanyRepository
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import CompanyModel


def _to_domain(row: CompanyModel) -> Company:
    return Company(
        ticker=row.ticker,
        name=row.name,
        sector=Sector(row.sector) if row.sector in Sector._value2member_map_ else Sector.UNKNOWN,
        industry=row.industry,
        exchange=row.exchange,
        country=row.country,
        ipo_date=row.ipo_date,
        description=row.description,
        website=row.website,
        is_active=row.is_active,
        asset_type=AssetType(row.asset_type) if row.asset_type in AssetType._value2member_map_ else AssetType.EQUITY,
        expense_ratio=row.expense_ratio,
        aum=row.aum,
    )


class SqlAlchemyCompanyRepository(CompanyRepository):
    """Postgres-backed implementation of CompanyRepository.

    Opens/commits/closes its own session per call. This is the right
    granularity for an MVP; if we later need multi-repository
    transactions (e.g. atomic company + statements writes), we introduce
    a Unit-of-Work that spans repositories rather than complicating this
    interface now (YAGNI).
    """

    def save(self, company: Company) -> None:
        with session_scope() as session:
            existing = session.get(CompanyModel, company.ticker)
            if existing is None:
                session.add(
                    CompanyModel(
                        ticker=company.ticker,
                        name=company.name,
                        sector=company.sector.value,
                        industry=company.industry,
                        exchange=company.exchange,
                        country=company.country,
                        ipo_date=company.ipo_date,
                        description=company.description,
                        website=company.website,
                        is_active=company.is_active,
                        asset_type=company.asset_type.value,
                        expense_ratio=company.expense_ratio,
                        aum=company.aum,
                    )
                )
            else:
                existing.name = company.name
                existing.sector = company.sector.value
                existing.industry = company.industry
                existing.exchange = company.exchange
                existing.country = company.country
                existing.ipo_date = company.ipo_date
                existing.description = company.description
                existing.website = company.website
                existing.is_active = company.is_active
                existing.asset_type = company.asset_type.value
                existing.expense_ratio = company.expense_ratio
                existing.aum = company.aum

    def get_by_ticker(self, ticker: str) -> Company | None:
        with session_scope() as session:
            row = session.get(CompanyModel, ticker.strip().upper())
            return _to_domain(row) if row else None

    def list_all(self, active_only: bool = True) -> list[Company]:
        with session_scope() as session:
            stmt = select(CompanyModel)
            if active_only:
                stmt = stmt.where(CompanyModel.is_active.is_(True))
            rows = session.execute(stmt).scalars().all()
            return [_to_domain(row) for row in rows]
