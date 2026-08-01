from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from src.domain.entities.factor_scores import FactorRawMetrics, FactorScore, FactorZScores
from src.domain.repositories.factor_score_repository import FactorScoreRepository
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import FactorScoreModel


def _to_domain(row: FactorScoreModel) -> FactorScore:
    # Postgres's plain `timestamp` column (not `timestamptz`) strips
    # timezone info on storage — SQLAlchemy reads it back as a NAIVE
    # datetime even though it was saved with datetime.now(timezone.utc).
    # Every value written by this app is UTC by convention (see
    # ComputeUniverseFactorSnapshotUseCase), so re-attaching UTC here is
    # correct, not an assumption. Without this, any arithmetic against
    # a fresh datetime.now(timezone.utc) raises
    # "can't subtract offset-naive and offset-aware datetimes" —
    # confirmed in production (GetFactorScoresUseCase._ensure_fresh).
    as_of = row.as_of if row.as_of.tzinfo is not None else row.as_of.replace(tzinfo=timezone.utc)
    return FactorScore(
        ticker=row.ticker,
        as_of=as_of,
        raw=FactorRawMetrics(
            price_to_earnings=row.price_to_earnings,
            return_on_equity=row.return_on_equity,
            revenue_growth_yoy=row.revenue_growth_yoy,
            momentum_1m_pct=row.momentum_1m_pct,
            market_cap=row.market_cap,
        ),
        z_scores=FactorZScores(
            value=row.value_z,
            quality=row.quality_z,
            growth=row.growth_z,
            momentum=row.momentum_z,
            size=row.size_z,
        ),
    )


class SqlAlchemyFactorScoreRepository(FactorScoreRepository):
    def save_batch(self, scores: list[FactorScore]) -> None:
        with session_scope() as session:
            # Full-refresh semantics: clear the whole cache first so a
            # ticker dropped from the universe doesn't linger forever.
            session.execute(delete(FactorScoreModel))
            for s in scores:
                session.add(
                    FactorScoreModel(
                        ticker=s.ticker,
                        as_of=s.as_of,
                        price_to_earnings=s.raw.price_to_earnings,
                        return_on_equity=s.raw.return_on_equity,
                        revenue_growth_yoy=s.raw.revenue_growth_yoy,
                        momentum_1m_pct=s.raw.momentum_1m_pct,
                        market_cap=s.raw.market_cap,
                        value_z=s.z_scores.value,
                        quality_z=s.z_scores.quality,
                        growth_z=s.z_scores.growth,
                        momentum_z=s.z_scores.momentum,
                        size_z=s.z_scores.size,
                    )
                )

    def get_latest_as_of(self) -> datetime | None:
        with session_scope() as session:
            result = session.execute(select(func.max(FactorScoreModel.as_of))).scalar_one_or_none()
            if result is None or result.tzinfo is not None:
                return result
            # Same Postgres-strips-tzinfo gap as _to_domain — this raw
            # scalar query bypasses _to_domain entirely, so it needs its
            # own fix. This is the exact call site that crashed
            # GetFactorScoresUseCase._ensure_fresh() in production.
            return result.replace(tzinfo=timezone.utc)

    def get(self, ticker: str) -> FactorScore | None:
        with session_scope() as session:
            row = session.execute(
                select(FactorScoreModel).where(FactorScoreModel.ticker == ticker.strip().upper())
            ).scalar_one_or_none()
            return _to_domain(row) if row else None

    def get_all(self) -> list[FactorScore]:
        with session_scope() as session:
            rows = session.execute(select(FactorScoreModel)).scalars().all()
            return [_to_domain(row) for row in rows]
