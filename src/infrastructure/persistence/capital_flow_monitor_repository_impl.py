from __future__ import annotations

from sqlalchemy import select

from src.domain.entities.capital_flow_monitor import CapitalFlowMonitorSnapshot
from src.domain.repositories.capital_flow_monitor_repository import (
    CapitalFlowMonitorSnapshotRepository,
)
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import CapitalFlowMonitorSnapshotModel


def _row_to_domain(row: CapitalFlowMonitorSnapshotModel) -> CapitalFlowMonitorSnapshot:
    # JSON round-trips lists, not tuples — each stored signal comes
    # back as a 3-element list; converted to a tuple here so the
    # domain entity's own type (dict[str, tuple[str, str | None, str]])
    # is genuinely honored, not silently violated by whatever JSON
    # happened to deserialize to.
    signals = {
        module_id: (v[0], v[1], v[2])
        for module_id, v in (row.signals or {}).items()
    }
    return CapitalFlowMonitorSnapshot(
        snapshot_date=row.snapshot_date,
        signals=signals,
        regime_label=row.regime_label,
        regime_stance=row.regime_stance,
    )


class SqlAlchemyCapitalFlowMonitorSnapshotRepository(CapitalFlowMonitorSnapshotRepository):
    def save_snapshot(self, user_id: str, snapshot: CapitalFlowMonitorSnapshot) -> None:
        with session_scope() as session:
            existing = session.execute(
                select(CapitalFlowMonitorSnapshotModel).where(
                    CapitalFlowMonitorSnapshotModel.user_id == user_id,
                    CapitalFlowMonitorSnapshotModel.snapshot_date == snapshot.snapshot_date,
                )
            ).scalar_one_or_none()

            # Lists, not tuples, for JSON storage — tuples aren't a
            # native JSON type and would round-trip as lists anyway on
            # the way back out; storing them as lists from the start
            # avoids a silent, confusing type change between save and
            # load.
            new_signals_json = {
                module_id: list(v) for module_id, v in snapshot.signals.items()
            }

            if existing is None:
                session.add(
                    CapitalFlowMonitorSnapshotModel(
                        user_id=user_id,
                        snapshot_date=snapshot.snapshot_date,
                        signals=new_signals_json,
                        regime_label=snapshot.regime_label,
                        regime_stance=snapshot.regime_stance,
                    )
                )
            else:
                # Merge, don't overwrite — a morning load of 3 modules
                # followed by an afternoon load of 2 more should leave
                # all 5 in the same day's row, matching the artifact's
                # original "partial loads accumulate" behavior.
                merged = {**(existing.signals or {}), **new_signals_json}
                existing.signals = merged
                if snapshot.regime_label is not None:
                    existing.regime_label = snapshot.regime_label
                    existing.regime_stance = snapshot.regime_stance

    def list_recent(self, user_id: str, limit: int = 14) -> list[CapitalFlowMonitorSnapshot]:
        with session_scope() as session:
            rows = session.execute(
                select(CapitalFlowMonitorSnapshotModel)
                .where(CapitalFlowMonitorSnapshotModel.user_id == user_id)
                .order_by(CapitalFlowMonitorSnapshotModel.snapshot_date.desc())
                .limit(limit)
            ).scalars().all()
            return [_row_to_domain(row) for row in rows]
