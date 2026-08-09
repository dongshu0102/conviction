from __future__ import annotations

from sqlalchemy import select

from src.domain.entities.capital_flow import (
    CapitalFlowDirection,
    CapitalFlowEvent,
    CapitalFlowSource,
)
from src.domain.repositories.capital_flow_repository import CapitalFlowRepository
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import CapitalFlowEventModel


class SqlAlchemyCapitalFlowRepository(CapitalFlowRepository):
    def save_new_events(self, events: list[CapitalFlowEvent]) -> list[CapitalFlowEvent]:
        if not events:
            return []

        with session_scope() as session:
            # Query which of THIS BATCH's dedup keys already exist,
            # once, rather than relying on catching a per-row
            # IntegrityError from the unique constraint — a batch
            # insert that partially fails mid-transaction is a much
            # messier failure mode than filtering first.
            candidate_keys = [e.dedup_key for e in events]
            existing_keys = set(
                session.execute(
                    select(CapitalFlowEventModel.dedup_key).where(
                        CapitalFlowEventModel.dedup_key.in_(candidate_keys)
                    )
                ).scalars().all()
            )

            new_events = [e for e in events if e.dedup_key not in existing_keys]
            # The same real-world event can also appear twice within a
            # single batch (e.g. FMP returning an overlapping page on
            # two sources) — dedup within the batch itself too, not
            # just against what's already stored.
            seen_this_batch: set[str] = set()
            deduped_new_events: list[CapitalFlowEvent] = []
            for event in new_events:
                if event.dedup_key in seen_this_batch:
                    continue
                seen_this_batch.add(event.dedup_key)
                deduped_new_events.append(event)

            for event in deduped_new_events:
                session.add(
                    CapitalFlowEventModel(
                        symbol=event.symbol,
                        source=event.source.value,
                        direction=event.direction.value,
                        event_date=event.event_date,
                        headline=event.headline,
                        detail_url=event.detail_url,
                        detected_at=event.detected_at,
                        dedup_key=event.dedup_key,
                    )
                )

            return deduped_new_events

    def list_recent(
        self, source: CapitalFlowSource | None = None, limit: int = 50,
    ) -> list[CapitalFlowEvent]:
        with session_scope() as session:
            stmt = select(CapitalFlowEventModel)
            if source is not None:
                stmt = stmt.where(CapitalFlowEventModel.source == source.value)
            stmt = stmt.order_by(CapitalFlowEventModel.detected_at.desc()).limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [
                CapitalFlowEvent(
                    source=CapitalFlowSource(row.source),
                    symbol=row.symbol,
                    event_date=row.event_date,
                    direction=CapitalFlowDirection(row.direction),
                    headline=row.headline,
                    detail_url=row.detail_url,
                    detected_at=row.detected_at,
                    dedup_key=row.dedup_key,
                )
                for row in rows
            ]
