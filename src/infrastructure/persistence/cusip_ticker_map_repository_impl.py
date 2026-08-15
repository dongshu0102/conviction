from __future__ import annotations

from src.domain.entities.cusip_ticker_mapping import CusipTickerMapping
from src.domain.repositories.cusip_ticker_map_repository import (
    CusipTickerMapRepository,
)
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import CusipTickerMapModel


def _to_entity(m: CusipTickerMapModel) -> CusipTickerMapping:
    return CusipTickerMapping(
        cusip=m.cusip, ticker=m.ticker,
        company_name=m.company_name, resolved_at=m.resolved_at,
    )


class SqlAlchemyCusipTickerMapRepository(CusipTickerMapRepository):
    def get(self, cusip: str) -> CusipTickerMapping | None:
        with session_scope() as session:
            model = session.get(CusipTickerMapModel, cusip)
            return _to_entity(model) if model is not None else None

    def get_many(self, cusips: list[str]) -> dict[str, CusipTickerMapping]:
        if not cusips:
            return {}
        with session_scope() as session:
            rows = (
                session.query(CusipTickerMapModel)
                .filter(CusipTickerMapModel.cusip.in_(cusips))
                .all()
            )
            return {m.cusip: _to_entity(m) for m in rows}

    def save(self, mapping: CusipTickerMapping) -> None:
        with session_scope() as session:
            existing = session.get(CusipTickerMapModel, mapping.cusip)
            if existing is not None:
                existing.ticker = mapping.ticker
                existing.company_name = mapping.company_name
                existing.resolved_at = mapping.resolved_at
            else:
                session.add(CusipTickerMapModel(
                    cusip=mapping.cusip, ticker=mapping.ticker,
                    company_name=mapping.company_name, resolved_at=mapping.resolved_at,
                ))

    def get_unresolved(self, cusips: list[str]) -> list[str]:
        if not cusips:
            return []
        with session_scope() as session:
            already_resolved = {
                row[0] for row in session.query(CusipTickerMapModel.cusip)
                .filter(CusipTickerMapModel.cusip.in_(cusips))
                .all()
            }
            return [c for c in cusips if c not in already_resolved]
