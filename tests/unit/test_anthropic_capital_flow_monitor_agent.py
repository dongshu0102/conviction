"""Tests for AnthropicCapitalFlowMonitorAgent, using a fake client
(same dependency-injection pattern this codebase's other Anthropic
adapters expose via their client parameter). Cannot run in this
sandbox — no PyPI access to install the real anthropic package here —
but requires nothing beyond what's already in the user's real venv,
where chat_with_agent.py already depends on this exact package
successfully in production.
"""
from src.domain.entities.capital_flow_monitor import CAPITAL_FLOW_MONITOR_MODULES, CapitalFlowMonitorModuleResult
from src.infrastructure.config import Settings
from src.infrastructure.llm_providers.anthropic_capital_flow_monitor_agent import (
    AnthropicCapitalFlowMonitorAgent,
    CapitalFlowMonitorAgentError,
)


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.content = [_FakeTextBlock(text)]


class _FakeMessages:
    def __init__(self, response_text: str) -> None:
        self._response_text = response_text
        self.last_call_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_call_kwargs = kwargs
        return _FakeResponse(self._response_text)


class _FakeAnthropicClient:
    def __init__(self, response_text: str) -> None:
        self.messages = _FakeMessages(response_text)


def _settings() -> Settings:
    return Settings(anthropic_api_key="test_key", anthropic_model="claude-test")


def _etf_module_def():
    return next(m for m in CAPITAL_FLOW_MONITOR_MODULES if m.id == "etf")


def test_fetch_module_parses_a_real_shaped_response() -> None:
    response_json = (
        '{"as_of": "2026-08-07", "headline_value": "+$4.2B", "headline_direction": "inflow", '
        '"headline_label": "US-listed ETF net flow (day)", "details": '
        '[{"label": "Top inflow", "value": "SPY +$1.8B"}], "read": "Strong demand.", '
        '"source_note": "etf.com"}'
    )
    client = _FakeAnthropicClient(response_json)
    agent = AnthropicCapitalFlowMonitorAgent(_settings(), client=client)

    result = agent.fetch_module(_etf_module_def())

    assert isinstance(result, CapitalFlowMonitorModuleResult)
    assert result.module_id == "etf"
    assert result.headline_value == "+$4.2B"
    assert result.headline_direction == "inflow"
    assert result.is_agent_estimate is True
    assert len(result.details) == 1
    assert result.details[0].label == "Top inflow"


def test_fetch_module_includes_web_search_tool_in_the_real_api_call() -> None:
    """Regression guard: this feature's entire value proposition is
    that the agent actually searches the live web — if the
    web_search tool were ever accidentally dropped from the request,
    every module would silently degrade to the model's stale training
    data instead of a real, current search."""
    client = _FakeAnthropicClient('{"as_of": "x", "headline_value": "x", "headline_label": "x", "read": "x", "source_note": "x"}')
    agent = AnthropicCapitalFlowMonitorAgent(_settings(), client=client)

    agent.fetch_module(_etf_module_def())

    tools = client.messages.last_call_kwargs["tools"]
    assert tools == [{"type": "web_search_20250305", "name": "web_search"}]


def test_fetch_module_raises_on_missing_required_keys() -> None:
    client = _FakeAnthropicClient('{"headline_value": "271bp"}')  # missing as_of, headline_label, read, source_note
    agent = AnthropicCapitalFlowMonitorAgent(_settings(), client=client)

    try:
        agent.fetch_module(_etf_module_def())
        assert False, "expected CapitalFlowMonitorAgentError"
    except CapitalFlowMonitorAgentError as exc:
        assert "missing keys" in str(exc)


def test_fetch_module_raises_for_a_fred_backed_module_with_no_prompt() -> None:
    """The 2 real-FRED modules should never reach this agent at all —
    a defensive check catching a real routing bug rather than silently
    sending a nonsense request to Claude."""
    credit_def = next(m for m in CAPITAL_FLOW_MONITOR_MODULES if m.id == "credit")
    client = _FakeAnthropicClient("irrelevant")
    agent = AnthropicCapitalFlowMonitorAgent(_settings(), client=client)

    try:
        agent.fetch_module(credit_def)
        assert False, "expected CapitalFlowMonitorAgentError"
    except CapitalFlowMonitorAgentError as exc:
        assert "credit" in str(exc)


def test_fetch_module_tolerates_prose_wrapped_json_realistic_for_web_search() -> None:
    """A web_search-enabled response is more likely to include a short
    preamble than a plain structured-output call — this must still
    parse correctly, not just the bare-JSON case."""
    response_text = (
        "Based on my search, here is the latest data:\n"
        '{"as_of": "2026-08-07", "headline_value": "271bp", "headline_label": "HY OAS", '
        '"read": "Tight.", "source_note": "FRED"}\n'
        "Let me know if you need anything else."
    )
    client = _FakeAnthropicClient(response_text)
    agent = AnthropicCapitalFlowMonitorAgent(_settings(), client=client)

    result = agent.fetch_module(_etf_module_def())
    assert result.headline_value == "271bp"


def test_synthesize_parses_a_real_shaped_response() -> None:
    response_json = (
        '{"regime": "Cautious risk-on", "stance": "mixed", '
        '"supportive": ["Fed easing"], "headwinds": ["Wide spreads"], '
        '"conflict": "Fed dovish but credit stress rising.", "watch": "CPI print next week."}'
    )
    client = _FakeAnthropicClient(response_json)
    agent = AnthropicCapitalFlowMonitorAgent(_settings(), client=client)

    result = agent.synthesize([("ETF Flows", "flow", _sample_result())])

    assert result.regime == "Cautious risk-on"
    assert result.stance == "mixed"
    assert result.supportive == ("Fed easing",)
    assert result.headwinds == ("Wide spreads",)


def test_synthesize_does_not_pass_the_web_search_tool() -> None:
    """Synthesis reasons over data already gathered — it has no
    business searching the web itself."""
    client = _FakeAnthropicClient(
        '{"regime": "x", "stance": "mixed", "supportive": [], "headwinds": [], "conflict": "x", "watch": "x"}'
    )
    agent = AnthropicCapitalFlowMonitorAgent(_settings(), client=client)

    agent.synthesize([("ETF Flows", "flow", _sample_result())])

    assert "tools" not in client.messages.last_call_kwargs


def _sample_result() -> CapitalFlowMonitorModuleResult:
    from datetime import datetime, timezone

    return CapitalFlowMonitorModuleResult(
        module_id="etf", headline_value="+$4.2B", headline_direction="inflow",
        headline_label="ETF net flow", details=(), read="Strong demand.",
        source_note="etf.com", as_of="2026-08-07", fetched_at=datetime.now(timezone.utc),
        is_agent_estimate=True,
    )
