"""Interface for the agent that backs the 9 Capital Flow Monitor
modules with no free structured API — a Claude + web_search agent
that searches the live web and returns its best-effort, source-cited
reading. Kept as a Protocol so the application layer never imports
`anthropic` directly, matching this codebase's established quarantine
principle for third-party SDKs (see ChatAgent, ThemeSynthesisGenerator).
"""
from __future__ import annotations

from typing import Protocol

from src.domain.entities.capital_flow_monitor import (
    CapitalFlowMonitorModuleDef,
    CapitalFlowMonitorModuleResult,
    CapitalFlowMonitorSynthesis,
)


class CapitalFlowMonitorAgentError(Exception):
    """Raised when the agent call itself fails, or its response can't
    be parsed/validated into the expected shape — never silently
    swallowed, since a failed module load must be visibly distinct
    from a module that's simply idle/not-yet-loaded."""


class CapitalFlowMonitorAgent(Protocol):
    def fetch_module(self, module_def: CapitalFlowMonitorModuleDef) -> CapitalFlowMonitorModuleResult:
        """Sends the agent to search the web per module_def.prompt and
        returns its best-effort, source-cited reading. Raises
        CapitalFlowMonitorAgentError on any failure — a network error,
        an API error, or a response that doesn't parse into valid JSON
        matching module_def.schema."""
        ...

    def synthesize(
        self, loaded: list[tuple[str, str, CapitalFlowMonitorModuleResult]],
    ) -> CapitalFlowMonitorSynthesis:
        """loaded: [(title, group, result), ...] for every module the
        caller has already loaded. Returns one overall verdict across
        the board. Raises CapitalFlowMonitorAgentError on failure."""
        ...
