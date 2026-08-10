from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from src.domain.entities.capital_flow_monitor import (
    CapitalFlowMonitorDetail,
    CapitalFlowMonitorModuleResult,
)
from src.domain.repositories.capital_flow_monitor_agent_cache_repository import (
    CapitalFlowMonitorAgentCacheRepository,
)
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import CapitalFlowMonitorAgentCacheModel


def _result_to_json(result: CapitalFlowMonitorModuleResult) -> dict:
    return {
        "module_id": result.module_id,
        "headline_value": result.headline_value,
        "headline_direction": result.headline_direction,
        "headline_label": result.headline_label,
        "details": [{"label": d.label, "value": d.value} for d in result.details],
        "read": result.read,
        "source_note": result.source_note,
        "as_of": result.as_of,
        "fetched_at": result.fetched_at.isoformat(),
        "is_agent_estimate": result.is_agent_estimate,
    }


def _json_to_result(data: dict) -> CapitalFlowMonitorModuleResult:
    return CapitalFlowMonitorModuleResult(
        module_id=data["module_id"],
        headline_value=data["headline_value"],
        headline_direction=data["headline_direction"],
        headline_label=data["headline_label"],
        details=tuple(CapitalFlowMonitorDetail(label=d["label"], value=d["value"]) for d in data["details"]),
        read=data["read"],
        source_note=data["source_note"],
        as_of=data["as_of"],
        fetched_at=datetime.fromisoformat(data["fetched_at"]),
        is_agent_estimate=data["is_agent_estimate"],
    )


class SqlAlchemyCapitalFlowMonitorAgentCacheRepository(CapitalFlowMonitorAgentCacheRepository):
    def get_cached(self, module_id: str, max_age_seconds: float) -> CapitalFlowMonitorModuleResult | None:
        with session_scope() as session:
            row = session.execute(
                select(CapitalFlowMonitorAgentCacheModel).where(
                    CapitalFlowMonitorAgentCacheModel.module_id == module_id,
                )
            ).scalar_one_or_none()

            if row is None:
                return None

            cached_at = row.cached_at
            if cached_at.tzinfo is None:
                # Postgres DateTime columns round-trip as naive
                # datetimes even though the value written was
                # timezone-aware — re-attach UTC explicitly rather
                # than let a naive/aware comparison below raise.
                cached_at = cached_at.replace(tzinfo=timezone.utc)

            age_seconds = (datetime.now(timezone.utc) - cached_at).total_seconds()
            if age_seconds > max_age_seconds:
                return None

            return _json_to_result(row.result_json)

    def set_cached(self, result: CapitalFlowMonitorModuleResult) -> None:
        with session_scope() as session:
            existing = session.execute(
                select(CapitalFlowMonitorAgentCacheModel).where(
                    CapitalFlowMonitorAgentCacheModel.module_id == result.module_id,
                )
            ).scalar_one_or_none()

            result_json = _result_to_json(result)
            if existing is None:
                session.add(
                    CapitalFlowMonitorAgentCacheModel(
                        module_id=result.module_id,
                        result_json=result_json,
                        cached_at=datetime.now(timezone.utc),
                    )
                )
            else:
                existing.result_json = result_json
                existing.cached_at = datetime.now(timezone.utc)
