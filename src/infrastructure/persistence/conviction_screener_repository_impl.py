from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, desc, func, select

from src.domain.entities.conviction_summary import ConvictionScreenerResult
from src.domain.repositories.conviction_screener_repository import ConvictionScreenerRepository
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import ConvictionScreenerResultModel


def _to_domain(row: ConvictionScreenerResultModel) -> ConvictionScreenerResult:
    # Same Postgres-strips-tzinfo gap as FactorScoreModel's own
    # _to_domain, confirmed in production for that table: a plain
    # `timestamp` column (not `timestamptz`) loses timezone info on
    # storage, so SQLAlchemy reads it back NAIVE even though it was
    # saved with datetime.now(timezone.utc). Every value written by
    # this app is UTC by convention, so re-attaching UTC here is
    # correct, not an assumption -- without it, comparing against a
    # fresh datetime.now(timezone.utc) elsewhere would raise "can't
    # subtract offset-naive and offset-aware datetimes."
    as_of = row.as_of if row.as_of.tzinfo is not None else row.as_of.replace(tzinfo=timezone.utc)
    return ConvictionScreenerResult(
        ticker=row.ticker, as_of=as_of,
        institutional_signal=row.institutional_signal, activist_signal=row.activist_signal,
        insider_signal=row.insider_signal, signal_count=row.signal_count,
    )


class SqlAlchemyConvictionScreenerRepository(ConvictionScreenerRepository):
    def save_batch(self, results: list[ConvictionScreenerResult]) -> None:
        with session_scope() as session:
            # Full-refresh semantics, same rationale as
            # SqlAlchemyFactorScoreRepository: clear the whole cache
            # first so a ticker dropped from the universe doesn't
            # linger forever with a stale result.
            session.execute(delete(ConvictionScreenerResultModel))
            for r in results:
                session.add(ConvictionScreenerResultModel(
                    ticker=r.ticker, as_of=r.as_of,
                    institutional_signal=r.institutional_signal, activist_signal=r.activist_signal,
                    insider_signal=r.insider_signal, signal_count=r.signal_count,
                ))

    def get_latest_as_of(self) -> datetime | None:
        with session_scope() as session:
            result = session.execute(
                select(func.max(ConvictionScreenerResultModel.as_of))
            ).scalar_one_or_none()
            if result is None or result.tzinfo is not None:
                return result
            return result.replace(tzinfo=timezone.utc)

    def get_all(self, min_signal_count: int = 0) -> list[ConvictionScreenerResult]:
        with session_scope() as session:
            rows = session.execute(
                select(ConvictionScreenerResultModel)
                .where(ConvictionScreenerResultModel.signal_count >= min_signal_count)
                .order_by(desc(ConvictionScreenerResultModel.signal_count), ConvictionScreenerResultModel.ticker)
            ).scalars().all()
            return [_to_domain(row) for row in rows]
