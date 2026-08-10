from datetime import datetime, timezone

from src.application.use_cases.synthesize_capital_flow_monitor import (
    SynthesizeCapitalFlowMonitorError,
    SynthesizeCapitalFlowMonitorUseCase,
)
from src.domain.entities.capital_flow_monitor import (
    CapitalFlowMonitorModuleResult,
    CapitalFlowMonitorSynthesis,
)
from tests.unit.fakes import FakeCapitalFlowMonitorAgent, FakeCapitalFlowMonitorSnapshotRepository


def _result(module_id: str) -> CapitalFlowMonitorModuleResult:
    return CapitalFlowMonitorModuleResult(
        module_id=module_id, headline_value="x", headline_direction="inflow",
        headline_label="x", details=(), read="x", source_note="x", as_of="2026-08-10",
        fetched_at=datetime.now(timezone.utc), is_agent_estimate=True,
    )


def _synthesis() -> CapitalFlowMonitorSynthesis:
    return CapitalFlowMonitorSynthesis(
        regime="Cautious risk-on", stance="mixed", supportive=("Fed easing",),
        headwinds=("Wide spreads",), conflict="Mixed signals.", watch="CPI next week.",
        synthesized_at=datetime.now(timezone.utc),
    )


def test_execute_requires_at_least_3_loaded_modules() -> None:
    agent = FakeCapitalFlowMonitorAgent(synthesis_result=_synthesis())
    repo = FakeCapitalFlowMonitorSnapshotRepository()
    use_case = SynthesizeCapitalFlowMonitorUseCase(agent, repo)

    loaded = [("ETF Flows", "flow", _result("etf")), ("ICI", "flow", _result("ici"))]  # only 2
    try:
        use_case.execute("alice", loaded)
        assert False, "expected SynthesizeCapitalFlowMonitorError"
    except SynthesizeCapitalFlowMonitorError:
        pass
    assert agent.synthesize_calls == []  # never even reached the agent


def test_execute_calls_the_agent_and_returns_its_synthesis() -> None:
    agent = FakeCapitalFlowMonitorAgent(synthesis_result=_synthesis())
    repo = FakeCapitalFlowMonitorSnapshotRepository()
    use_case = SynthesizeCapitalFlowMonitorUseCase(agent, repo)

    loaded = [("ETF Flows", "flow", _result("etf")), ("ICI", "flow", _result("ici")), ("CFTC", "flow", _result("cftc"))]
    result = use_case.execute("alice", loaded)

    assert result.regime == "Cautious risk-on"
    assert result.stance == "mixed"
    assert len(agent.synthesize_calls) == 1
    assert agent.synthesize_calls[0] == loaded


def test_execute_saves_the_regime_into_todays_snapshot() -> None:
    agent = FakeCapitalFlowMonitorAgent(synthesis_result=_synthesis())
    repo = FakeCapitalFlowMonitorSnapshotRepository()
    use_case = SynthesizeCapitalFlowMonitorUseCase(agent, repo)

    loaded = [("ETF Flows", "flow", _result("etf")), ("ICI", "flow", _result("ici")), ("CFTC", "flow", _result("cftc"))]
    use_case.execute("alice", loaded)

    saved = repo.list_recent("alice")
    assert len(saved) == 1
    assert saved[0].regime_label == "Cautious risk-on"
    assert saved[0].regime_stance == "mixed"


def test_execute_wraps_a_real_agent_failure() -> None:
    agent = FakeCapitalFlowMonitorAgent(raise_on_synthesize=True)
    repo = FakeCapitalFlowMonitorSnapshotRepository()
    use_case = SynthesizeCapitalFlowMonitorUseCase(agent, repo)

    loaded = [("ETF Flows", "flow", _result("etf")), ("ICI", "flow", _result("ici")), ("CFTC", "flow", _result("cftc"))]
    try:
        use_case.execute("alice", loaded)
        assert False, "expected SynthesizeCapitalFlowMonitorError"
    except SynthesizeCapitalFlowMonitorError:
        pass
