from __future__ import annotations

import logging
import time
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.exc import OperationalError

from src.domain.entities.institutional_holding import InstitutionalHolding
from src.domain.repositories.institutional_holding_repository import (
    InstitutionalHoldingRepository,
)
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import InstitutionalHoldingModel

logger = logging.getLogger(__name__)

# Chunk size for bulk_save: keeps any single INSERT statement (and its
# transaction) to a sane size when ingesting a quarter's worth of
# holdings, which can genuinely run into the millions of rows —
# inserting one enormous statement risks exceeding driver/server
# limits and makes a mid-batch failure lose far more progress than
# committing incrementally does.
_BULK_INSERT_CHUNK_SIZE = 5000

# A real, confirmed production failure: a multi-minute bulk insert run
# over the public internet (rather than this app's normal internal
# VPC connection) hit "server closed the connection unexpectedly" --
# confirmed directly from RDS's own Postgres log as "could not receive
# data from client: Connection timed out", i.e. the CLIENT side's
# connection went quiet, not an RDS-side resource limit. Retrying the
# one failed chunk (each already its own independent transaction) is
# far cheaper than re-running the entire multi-minute ingestion.
_MAX_CHUNK_ATTEMPTS = 4
_BASE_BACKOFF_SECONDS = 3.0


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
            self._save_chunk_with_retry(chunk)
            total_inserted += len(chunk)
        return total_inserted

    def _save_chunk_with_retry(self, chunk: list[InstitutionalHolding]) -> None:
        last_error: OperationalError | None = None
        for attempt in range(1, _MAX_CHUNK_ATTEMPTS + 1):
            try:
                with session_scope() as session:
                    session.add_all(_to_model(h) for h in chunk)
                return
            except OperationalError as exc:
                last_error = exc
                if attempt < _MAX_CHUNK_ATTEMPTS:
                    backoff = _BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
                    logger.warning(
                        "Institutional holdings chunk insert attempt %d/%d failed (%s), retrying in %.1fs",
                        attempt, _MAX_CHUNK_ATTEMPTS, exc, backoff,
                    )
                    time.sleep(backoff)

        logger.error(
            "Institutional holdings chunk of %d rows failed after %d attempts",
            len(chunk), _MAX_CHUNK_ATTEMPTS,
        )
        raise last_error

    def delete_period(self, period_of_report: date) -> int:
        with session_scope() as session:
            result = session.execute(
                delete(InstitutionalHoldingModel).where(
                    InstitutionalHoldingModel.period_of_report == period_of_report,
                )
            )
            return result.rowcount or 0

    def get_existing_accession_numbers(self, period_of_report: date) -> set[str]:
        with session_scope() as session:
            rows = session.execute(
                select(InstitutionalHoldingModel.accession_number)
                .where(InstitutionalHoldingModel.period_of_report == period_of_report)
                .distinct()
            ).scalars().all()
            return set(rows)

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

    def search_by_issuer_name(
        self, name_query: str, period_of_report: date, limit: int = 50,
    ) -> list[InstitutionalHolding]:
        with session_scope() as session:
            rows = session.execute(
                select(InstitutionalHoldingModel)
                .where(
                    InstitutionalHoldingModel.issuer_name.ilike(f"%{name_query}%"),
                    InstitutionalHoldingModel.period_of_report == period_of_report,
                )
                .order_by(InstitutionalHoldingModel.value_usd.desc())
                .limit(limit)
            ).scalars().all()
            return [_to_entity(r) for r in rows]

    def search_by_filer_name(
        self, name_query: str, period_of_report: date, limit: int = 50,
    ) -> list[InstitutionalHolding]:
        with session_scope() as session:
            rows = session.execute(
                select(InstitutionalHoldingModel)
                .where(
                    InstitutionalHoldingModel.filer_name.ilike(f"%{name_query}%"),
                    InstitutionalHoldingModel.period_of_report == period_of_report,
                )
                .order_by(InstitutionalHoldingModel.value_usd.desc())
                .limit(limit)
            ).scalars().all()
            return [_to_entity(r) for r in rows]

    def get_latest_period_of_report(self) -> date | None:
        with session_scope() as session:
            return session.execute(
                select(InstitutionalHoldingModel.period_of_report)
                .order_by(InstitutionalHoldingModel.period_of_report.desc())
                .limit(1)
            ).scalar_one_or_none()
