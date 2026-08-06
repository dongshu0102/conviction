from __future__ import annotations

from sqlalchemy import select

from src.domain.entities.speculative_growth_candidate import SpeculativeGrowthCandidate
from src.domain.repositories.speculative_growth_candidate_repository import (
    SpeculativeGrowthCandidateRepository,
)
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import SpeculativeGrowthCandidateModel


def _to_domain(row: SpeculativeGrowthCandidateModel) -> SpeculativeGrowthCandidate:
    return SpeculativeGrowthCandidate(
        user_id=row.user_id,
        ticker=row.ticker,
        added_at=row.added_at,
        last_growth_trend=row.last_growth_trend,
        last_cash_runway_months=row.last_cash_runway_months,
        last_market_cap=row.last_market_cap,
        last_checked_at=row.last_checked_at,
    )


class SqlAlchemySpeculativeGrowthCandidateRepository(SpeculativeGrowthCandidateRepository):
    def add(self, candidate: SpeculativeGrowthCandidate) -> SpeculativeGrowthCandidate:
        with session_scope() as session:
            existing = session.execute(
                select(SpeculativeGrowthCandidateModel).where(
                    SpeculativeGrowthCandidateModel.user_id == candidate.user_id,
                    SpeculativeGrowthCandidateModel.ticker == candidate.ticker,
                )
            ).scalar_one_or_none()
            if existing is not None:
                return _to_domain(existing)

            row = SpeculativeGrowthCandidateModel(
                user_id=candidate.user_id,
                ticker=candidate.ticker,
                added_at=candidate.added_at,
                last_growth_trend=candidate.last_growth_trend,
                last_cash_runway_months=candidate.last_cash_runway_months,
                last_market_cap=candidate.last_market_cap,
                last_checked_at=candidate.last_checked_at,
            )
            session.add(row)
            session.flush()
            return _to_domain(row)

    def remove(self, user_id: str, ticker: str) -> bool:
        with session_scope() as session:
            row = session.execute(
                select(SpeculativeGrowthCandidateModel).where(
                    SpeculativeGrowthCandidateModel.user_id == user_id,
                    SpeculativeGrowthCandidateModel.ticker == ticker,
                )
            ).scalar_one_or_none()
            if row is None:
                return False
            session.delete(row)
            return True

    def list_for_user(self, user_id: str) -> list[SpeculativeGrowthCandidate]:
        with session_scope() as session:
            rows = session.execute(
                select(SpeculativeGrowthCandidateModel)
                .where(SpeculativeGrowthCandidateModel.user_id == user_id)
                .order_by(SpeculativeGrowthCandidateModel.added_at)
            ).scalars().all()
            return [_to_domain(r) for r in rows]

    def update_last_state(
        self,
        user_id: str,
        ticker: str,
        growth_trend: str | None,
        cash_runway_months: float | None,
        market_cap: float | None,
        checked_at,
    ) -> None:
        with session_scope() as session:
            row = session.execute(
                select(SpeculativeGrowthCandidateModel).where(
                    SpeculativeGrowthCandidateModel.user_id == user_id,
                    SpeculativeGrowthCandidateModel.ticker == ticker,
                )
            ).scalar_one_or_none()
            if row is None:
                return
            row.last_growth_trend = growth_trend
            row.last_cash_runway_months = cash_runway_months
            row.last_market_cap = market_cap
            row.last_checked_at = checked_at
