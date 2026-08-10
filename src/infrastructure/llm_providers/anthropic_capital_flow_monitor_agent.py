"""Anthropic (Claude + web_search) adapter for the Capital Flow
Monitor's 9 agent-backed modules — the only module that knows this
specific "search the web, return strict JSON" wire pattern, same
quarantine principle as every other adapter in this package.

Unlike anthropic_chat_agent.py's custom tools, web_search is a
server-side tool: Anthropic executes the searches itself and the
response comes back already containing the model's final text after
searching — no client-side tool_use/tool_result loop is needed here.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import anthropic

from src.application.interfaces.capital_flow_monitor_agent import (
    CapitalFlowMonitorAgent,
    CapitalFlowMonitorAgentError,
)
from src.domain.entities.capital_flow_monitor import (
    CapitalFlowMonitorDetail,
    CapitalFlowMonitorModuleDef,
    CapitalFlowMonitorModuleResult,
    CapitalFlowMonitorSynthesis,
)
from src.infrastructure.config import Settings

logger = logging.getLogger(__name__)

_MODULE_REQUIRED_KEYS = {"as_of", "headline_value", "headline_label", "read", "source_note"}
_SYNTHESIS_REQUIRED_KEYS = {"regime", "stance", "supportive", "headwinds", "conflict", "watch"}


def _extract_text(response) -> str:
    text_blocks = [b.text for b in response.content if b.type == "text"]
    return "".join(text_blocks).strip()


def _parse_json_object(raw_text: str, context: str) -> dict:
    """Locates and parses the {...} JSON object anywhere in raw_text —
    robust to markdown fences, a preamble, or trailing commentary
    around it, all in one pass, regardless of newline placement.

    Deliberately does NOT special-case markdown fences with a
    newline-dependent split: a real production failure showed the
    model sometimes emits ```json {...}``` all on one line (no
    newline right after the fence) rather than the tidier
    ```json\\n{...}\\n``` shape a naive split assumes — splitting on
    "the first newline anywhere in the string" in that case tears the
    JSON object apart wherever a newline happens to occur later in the
    text, not at the fence boundary. find/rfind sidesteps this
    entirely by locating the actual braces directly, no matter what
    surrounds them."""
    clean = raw_text.strip()
    start = clean.find("{")
    end = clean.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise CapitalFlowMonitorAgentError(f"{context}: no JSON object found in response: {raw_text[:500]}")

    try:
        return json.loads(clean[start : end + 1])
    except json.JSONDecodeError as exc:
        raise CapitalFlowMonitorAgentError(f"{context}: response was not valid JSON: {raw_text[:500]}") from exc


class AnthropicCapitalFlowMonitorAgent(CapitalFlowMonitorAgent):
    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None) -> None:
        self._settings = settings
        self._client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def fetch_module(self, module_def: CapitalFlowMonitorModuleDef) -> CapitalFlowMonitorModuleResult:
        if module_def.prompt is None or module_def.schema is None:
            raise CapitalFlowMonitorAgentError(
                f"{module_def.id} has no prompt/schema — it should be routed to the real "
                f"FRED-backed path (capital_flow_monitor_math.py), not the agent"
            )

        system_instruction = f"""You are a capital-markets data agent. {module_def.prompt}

Respond with ONLY a single valid JSON object, no markdown fences, no preamble, no commentary. Use exactly this shape:
{module_def.schema}

Rules: every string must be short and display-ready, and must be a single line — never include a literal line break inside a string value, since that breaks JSON parsing. If an exact figure can't be found, give the most recent figure you CAN verify and say the period in "as_of". Never invent precise numbers — if genuinely nothing is found, set "headline_value" to "unavailable" and explain briefly in "read"."""

        try:
            response = self._client.messages.create(
                model=self._settings.anthropic_model,
                # A real search round-trip needs budget for the search
                # query itself, the retrieved result content the model
                # reads, and only then the final JSON text — a plain
                # tool-free call's budget (1000) proved too tight in a
                # real production failure: the model's response came
                # back with no text block at all, consistent with the
                # exchange being cut off mid-search before any final
                # answer was produced.
                max_tokens=4000,
                messages=[{"role": "user", "content": system_instruction}],
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
            )
        except anthropic.APIError as exc:
            raise CapitalFlowMonitorAgentError(f"Anthropic API request failed for {module_def.id}: {exc}") from exc

        raw_text = _extract_text(response)
        if not raw_text:
            raise CapitalFlowMonitorAgentError(
                f"{module_def.id}: empty response text (stop_reason={getattr(response, 'stop_reason', 'unknown')})"
            )
        parsed = _parse_json_object(raw_text, context=module_def.id)

        missing = _MODULE_REQUIRED_KEYS - parsed.keys()
        if missing:
            raise CapitalFlowMonitorAgentError(f"{module_def.id}: response missing keys: {missing}")

        details = tuple(
            CapitalFlowMonitorDetail(label=str(d.get("label", "")), value=str(d.get("value", "")))
            for d in parsed.get("details", [])
            if isinstance(d, dict)
        )

        return CapitalFlowMonitorModuleResult(
            module_id=module_def.id,
            headline_value=str(parsed["headline_value"]),
            headline_direction=parsed.get("headline_direction"),
            headline_label=str(parsed["headline_label"]),
            details=details,
            read=str(parsed["read"]),
            source_note=str(parsed["source_note"]),
            as_of=str(parsed["as_of"]),
            fetched_at=datetime.now(timezone.utc),
            is_agent_estimate=True,
        )

    def synthesize(
        self, loaded: list[tuple[str, str, CapitalFlowMonitorModuleResult]],
    ) -> CapitalFlowMonitorSynthesis:
        board = [
            {
                "signal": title,
                "group": group,
                "data": {
                    "headline_value": result.headline_value,
                    "headline_direction": result.headline_direction,
                    "headline_label": result.headline_label,
                    "details": [{"label": d.label, "value": d.value} for d in result.details],
                    "read": result.read,
                    "as_of": result.as_of,
                },
            }
            for title, group, result in loaded
        ]

        prompt = f"""You are a markets strategist. Below is a board of US stock market signals just gathered from public sources. Synthesize them into one overall read.

{json.dumps(board, indent=2)}

Respond with ONLY a single valid JSON object, no markdown fences, no preamble:
{{
  "regime": "2-4 word label for the current flow/macro regime, e.g. 'Cautious risk-on'",
  "stance": "supportive" | "mixed" | "headwind",
  "supportive": [ "short bullet", ... up to 3 signals currently helping stocks ],
  "headwinds": [ "short bullet", ... up to 3 signals currently hurting or warning ],
  "conflict": "one sentence on where the signals disagree, or 'Signals broadly aligned' if they don't",
  "watch": "one sentence: the single most important thing to watch next"
}}
Base everything strictly on the board above. Be specific — cite the actual figures."""

        try:
            response = self._client.messages.create(
                model=self._settings.anthropic_model,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            raise CapitalFlowMonitorAgentError(f"Anthropic API request failed for synthesis: {exc}") from exc

        raw_text = _extract_text(response)
        parsed = _parse_json_object(raw_text, context="synthesis")

        missing = _SYNTHESIS_REQUIRED_KEYS - parsed.keys()
        if missing:
            raise CapitalFlowMonitorAgentError(f"synthesis: response missing keys: {missing}")

        return CapitalFlowMonitorSynthesis(
            regime=str(parsed["regime"]),
            stance=str(parsed["stance"]),
            supportive=tuple(str(s) for s in parsed.get("supportive", [])),
            headwinds=tuple(str(s) for s in parsed.get("headwinds", [])),
            conflict=str(parsed["conflict"]),
            watch=str(parsed["watch"]),
            synthesized_at=datetime.now(timezone.utc),
        )
