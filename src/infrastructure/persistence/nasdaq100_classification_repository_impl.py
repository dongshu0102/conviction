from __future__ import annotations

from sqlalchemy import delete, select

from src.domain.entities.nasdaq100_classification import Nasdaq100Classification
from src.domain.repositories.nasdaq100_classification_repository import (
    Nasdaq100ClassificationRepository,
)
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import Nasdaq100ClassificationModel


def _to_domain(row: Nasdaq100ClassificationModel) -> Nasdaq100Classification:
    return Nasdaq100Classification(
        ticker=row.ticker, as_of=row.as_of, industry=row.industry,
        market_structure_category=row.market_structure_category, hhi=row.hhi,
        value_chain_position=row.value_chain_position, business_model=row.business_model,
        market_cap_tier=row.market_cap_tier, maturity_stage=row.maturity_stage,
        market_cap=row.market_cap, revenue_growth=row.revenue_growth,
    )


class SqlAlchemyNasdaq100ClassificationRepository(Nasdaq100ClassificationRepository):
    def save_batch(self, results: list[Nasdaq100Classification]) -> None:
        with session_scope() as session:
            # Full-refresh semantics, same rationale as
            # SqlAlchemyConvictionScreenerRepository.save_batch: clear
            # the whole cache first so a ticker dropped from the
            # Nasdaq-100 doesn't linger forever with a stale row.
            session.execute(delete(Nasdaq100ClassificationModel))
            for r in results:
                session.add(Nasdaq100ClassificationModel(
                    ticker=r.ticker, as_of=r.as_of, industry=r.industry,
                    market_structure_category=r.market_structure_category, hhi=r.hhi,
                    value_chain_position=r.value_chain_position, business_model=r.business_model,
                    market_cap_tier=r.market_cap_tier, maturity_stage=r.maturity_stage,
                    market_cap=r.market_cap, revenue_growth=r.revenue_growth,
                ))

    def get_all(
        self,
        industry: str | None = None,
        market_structure_category: str | None = None,
        value_chain_position: str | None = None,
        business_model: str | None = None,
        market_cap_tier: str | None = None,
        maturity_stage: str | None = None,
    ) -> list[Nasdaq100Classification]:
        with session_scope() as session:
            query = select(Nasdaq100ClassificationModel)
            if industry is not None:
                query = query.where(Nasdaq100ClassificationModel.industry == industry)
            if market_structure_category is not None:
                query = query.where(
                    Nasdaq100ClassificationModel.market_structure_category == market_structure_category
                )
            if value_chain_position is not None:
                query = query.where(
                    Nasdaq100ClassificationModel.value_chain_position == value_chain_position
                )
            if business_model is not None:
                query = query.where(Nasdaq100ClassificationModel.business_model == business_model)
            if market_cap_tier is not None:
                query = query.where(Nasdaq100ClassificationModel.market_cap_tier == market_cap_tier)
            if maturity_stage is not None:
                query = query.where(Nasdaq100ClassificationModel.maturity_stage == maturity_stage)

            rows = session.execute(query.order_by(Nasdaq100ClassificationModel.ticker)).scalars().all()
            return [_to_domain(row) for row in rows]
