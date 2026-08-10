from datetime import date

from src.application.use_cases.get_capital_flow_monitor_history import (
    GetCapitalFlowMonitorHistoryUseCase,
)
from src.domain.entities.capital_flow_monitor import CapitalFlowMonitorSnapshot
from tests.unit.fakes import FakeCapitalFlowMonitorSnapshotRepository


def test_execute_returns_this_users_recent_snapshots() -> None:
    repo = FakeCapitalFlowMonitorSnapshotRepository()
    repo.save_snapshot("alice", CapitalFlowMonitorSnapshot(snapshot_date=date(2026, 8, 10), signals={"etf": ("x", "inflow", "x")}))
    repo.save_snapshot("bob", CapitalFlowMonitorSnapshot(snapshot_date=date(2026, 8, 10), signals={"ici": ("y", "outflow", "y")}))
    use_case = GetCapitalFlowMonitorHistoryUseCase(repo)

    result = use_case.execute("alice")

    assert len(result) == 1
    assert "etf" in result[0].signals


def test_execute_respects_the_limit_parameter() -> None:
    repo = FakeCapitalFlowMonitorSnapshotRepository()
    for day in range(1, 6):
        repo.save_snapshot("alice", CapitalFlowMonitorSnapshot(snapshot_date=date(2026, 8, day), signals={}))
    use_case = GetCapitalFlowMonitorHistoryUseCase(repo)

    result = use_case.execute("alice", limit=2)

    assert len(result) == 2
    # most recent first
    assert result[0].snapshot_date == date(2026, 8, 5)
    assert result[1].snapshot_date == date(2026, 8, 4)
