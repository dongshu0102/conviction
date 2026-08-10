from datetime import date, datetime, timedelta, timezone

from src.application.use_cases.load_capital_flow_monitor_module import (
    LoadCapitalFlowMonitorModuleError,
    LoadCapitalFlowMonitorModuleUseCase,
)
from src.domain.entities.capital_flow_monitor import CapitalFlowMonitorModuleResult
from src.domain.entities.economic_indicator import EconomicIndicatorReading
from tests.unit.fakes import (
    FakeCapitalFlowMonitorAgent,
    FakeCapitalFlowMonitorSnapshotRepository,
    FakeMacroHistoryProviderForMonitor,
)


def _agent_result(module_id="etf") -> CapitalFlowMonitorModuleResult:
    return CapitalFlowMonitorModuleResult(
        module_id=module_id, headline_value="+$4.2B", headline_direction="inflow",
        headline_label="ETF net flow", details=(), read="Strong demand.",
        source_note="etf.com", as_of="2026-08-10", fetched_at=datetime.now(timezone.utc),
        is_agent_estimate=True,
    )


def _credit_readings() -> list[EconomicIndicatorReading]:
    today = date(2026, 8, 8)
    out = []
    d = today
    val = 2.71
    for _ in range(760):
        if d.weekday() < 5:
            out.append(EconomicIndicatorReading(name="BAMLH0A0HYM2", as_of=d, value=round(val, 2)))
        d -= timedelta(days=1)
        val += 0.001
    return out


def test_execute_dispatches_agent_backed_modules_to_the_agent() -> None:
    agent = FakeCapitalFlowMonitorAgent(results_by_module_id={"etf": _agent_result()})
    fred = FakeMacroHistoryProviderForMonitor()
    repo = FakeCapitalFlowMonitorSnapshotRepository()
    use_case = LoadCapitalFlowMonitorModuleUseCase(agent, fred, repo)

    result = use_case.execute("alice", "etf")

    assert result.module_id == "etf"
    assert result.is_agent_estimate is True
    assert agent.fetch_calls == ["etf"]


def test_execute_dispatches_credit_to_real_fred_not_the_agent() -> None:
    agent = FakeCapitalFlowMonitorAgent()
    fred = FakeMacroHistoryProviderForMonitor(readings_by_series={"BAMLH0A0HYM2": _credit_readings()})
    repo = FakeCapitalFlowMonitorSnapshotRepository()
    use_case = LoadCapitalFlowMonitorModuleUseCase(agent, fred, repo)

    result = use_case.execute("alice", "credit")

    assert result.module_id == "credit"
    assert result.is_agent_estimate is False
    assert agent.fetch_calls == []  # never touched the agent at all


def test_execute_dispatches_liquidity_to_real_fred_not_the_agent() -> None:
    agent = FakeCapitalFlowMonitorAgent()
    today = date(2026, 8, 8)
    walcl = [EconomicIndicatorReading(name="WALCL", as_of=today - timedelta(days=7 * i), value=6_700_000 - i * 1000) for i in range(20)]
    fred = FakeMacroHistoryProviderForMonitor(readings_by_series={"WALCL": walcl})
    repo = FakeCapitalFlowMonitorSnapshotRepository()
    use_case = LoadCapitalFlowMonitorModuleUseCase(agent, fred, repo)

    result = use_case.execute("alice", "liquidity")

    assert result.module_id == "liquidity"
    assert result.is_agent_estimate is False
    assert agent.fetch_calls == []


def test_execute_raises_for_an_unknown_module_id() -> None:
    agent = FakeCapitalFlowMonitorAgent()
    fred = FakeMacroHistoryProviderForMonitor()
    repo = FakeCapitalFlowMonitorSnapshotRepository()
    use_case = LoadCapitalFlowMonitorModuleUseCase(agent, fred, repo)

    try:
        use_case.execute("alice", "not_a_real_module")
        assert False, "expected LoadCapitalFlowMonitorModuleError"
    except LoadCapitalFlowMonitorModuleError:
        pass


def test_execute_wraps_a_real_agent_failure_in_the_use_cases_own_error() -> None:
    agent = FakeCapitalFlowMonitorAgent(raise_for_module_ids={"etf"})
    fred = FakeMacroHistoryProviderForMonitor()
    repo = FakeCapitalFlowMonitorSnapshotRepository()
    use_case = LoadCapitalFlowMonitorModuleUseCase(agent, fred, repo)

    try:
        use_case.execute("alice", "etf")
        assert False, "expected LoadCapitalFlowMonitorModuleError"
    except LoadCapitalFlowMonitorModuleError:
        pass


def test_execute_raises_when_credit_fred_returns_no_data() -> None:
    agent = FakeCapitalFlowMonitorAgent()
    fred = FakeMacroHistoryProviderForMonitor(readings_by_series={})  # BAMLH0A0HYM2 genuinely missing
    repo = FakeCapitalFlowMonitorSnapshotRepository()
    use_case = LoadCapitalFlowMonitorModuleUseCase(agent, fred, repo)

    try:
        use_case.execute("alice", "credit")
        assert False, "expected LoadCapitalFlowMonitorModuleError"
    except LoadCapitalFlowMonitorModuleError:
        pass


def test_execute_saves_a_snapshot_after_a_successful_load() -> None:
    """Regression test for the real, intended behavior: every
    successful load persists immediately, not only on synthesis."""
    agent = FakeCapitalFlowMonitorAgent(results_by_module_id={"etf": _agent_result()})
    fred = FakeMacroHistoryProviderForMonitor()
    repo = FakeCapitalFlowMonitorSnapshotRepository()
    use_case = LoadCapitalFlowMonitorModuleUseCase(agent, fred, repo)

    use_case.execute("alice", "etf")

    saved = repo.list_recent("alice")
    assert len(saved) == 1
    assert "etf" in saved[0].signals
    assert saved[0].signals["etf"] == ("+$4.2B", "inflow", "2026-08-10")


def test_execute_does_not_save_a_snapshot_when_the_load_fails() -> None:
    agent = FakeCapitalFlowMonitorAgent(raise_for_module_ids={"etf"})
    fred = FakeMacroHistoryProviderForMonitor()
    repo = FakeCapitalFlowMonitorSnapshotRepository()
    use_case = LoadCapitalFlowMonitorModuleUseCase(agent, fred, repo)

    try:
        use_case.execute("alice", "etf")
    except LoadCapitalFlowMonitorModuleError:
        pass

    assert repo.list_recent("alice") == []
