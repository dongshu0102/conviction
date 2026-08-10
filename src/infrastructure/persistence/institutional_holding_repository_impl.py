from __future__ import annotations

from datetime import date

from sqlalchemy import delete, select

from src.domain.entities.institutional_holding import InstitutionalHolding
from src.domain.repositories.institutional_holding_repository import (
    InstitutionalHoldingRepository,
)
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import InstitutionalHoldingModel

# Chunk size for bulk_save: keeps any single INSERT statement (and its
# transaction) to a sane size when ingesting a quarter's worth of
# holdings, which can genuinely run into the millions of rows —
# inserting one enormous statement risks exceeding driver/server
# limits and makes a mid-batch failure lose far more progress than
# committing incrementally does.
_BULK_INSERT_CHUNK_SIZE = 5000


def _to_model(h: InstitutionalHolding) -> InstitutionalHoldingModel:
    return InstitutionalHoldingModel(
        accession_number=h.accession_number,
        filer_cik=h.filer_cik,
        filer_name=h.filer_name,
        period_of_report=h.period_of_report,
        issuer_name=h.issuer_name,
        title_of_class=h.title_of_class,
        cusip=h.cusip,
        value_usd=h.value_usd,
        shares_or_principal_amount=h.shares_or_principal_amount,
        share_type=h.share_type,
        put_call=h.put_call,
        investment_discretion=h.investment_discretion,
        voting_authority_sole=h.voting_authority_sole,
        voting_authority_shared=h.voting_authority_shared,
        voting_authority_none=h.voting_authority_none,
    )


def _to_entity(row: InstitutionalHoldingModel) -> InstitutionalHolding:
    return InstitutionalHolding(
        accession_number=row.accession_number,
        filer_cik=row.filer_cik,
        filer_name=row.filer_name,
        period_of_report=row.period_of_report,
        issuer_name=row.issuer_name,
        title_of_class=row.title_of_class,
        cusip=row.cusip,
        value_usd=row.value_usd,
        shares_or_principal_amount=row.shares_or_principal_amount,
        share_type=row.share_type,
        put_call=row.put_call,
        investment_discretion=row.investment_discretion,
        voting_authority_sole=row.voting_authority_sole,
        voting_authority_shared=row.voting_authority_shared,
        voting_authority_none=row.voting_authority_none,
    )


class SqlAlchemyInstitutionalHoldingRepository(InstitutionalHoldingRepository):
    def bulk_save(self, holdings: list[InstitutionalHolding]) -> int:
        total_inserted = 0
        for start in range(0, len(holdings), _BULK_INSERT_CHUNK_SIZE):
            chunk = holdings[start : start + _BULK_INSERT_CHUNK_SIZE]
            with session_scope() as session:
                session.add_all(_to_model(h) for h in chunk)
            total_inserted += len(chunk)
        return total_inserted

    def delete_period(self, period_of_report: date) -> int:
        with session_scope() as session:
            result = session.execute(
                delete(InstitutionalHoldingModel).where(
                    InstitutionalHoldingModel.period_of_report == period_of_report,
                )
            )
            return result.rowcount or 0

    def get_by_cusip(self, cusip: str, period_of_report: date) -> list[InstitutionalHolding]:
        with session_scope() as session:
            rows = session.execute(
                select(InstitutionalHoldingModel).where(
                    InstitutionalHoldingModel.cusip == cusip,
                    InstitutionalHoldingModel.period_of_report == period_of_report,
                )
            ).scalars().all()
            return [_to_entity(r) for r in rows]

    def get_by_filer(self, filer_cik: str, period_of_report: date) -> list[InstitutionalHolding]:
        with session_scope() as session:
            rows = session.execute(
                select(InstitutionalHoldingModel).where(
                    InstitutionalHoldingModel.filer_cik == filer_cik,
                    InstitutionalHoldingModel.period_of_report == period_of_report,
                )
            ).scalars().all()
            return [_to_entity(r) for r in rows]
