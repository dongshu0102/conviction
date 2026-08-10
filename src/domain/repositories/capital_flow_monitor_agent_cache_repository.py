from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.capital_flow_monitor import CapitalFlowMonitorModuleResult


class CapitalFlowMonitorAgentCacheRepository(ABC):
    """A shared, GLOBAL cache (not per-user) for the 9 agent-backed
    modules' results — the underlying real-world data (ETF flows, Fed
    expectations, etc.) is the same for every user, so caching it
    globally means one real, costly web_search-enabled Anthropic call
    can serve every user who loads that module within the cache
    window, instead of each triggering its own. The 2 real-FRED
    modules (credit, liquidity) never use this — FRED calls are free
    and fast, with nothing to cache against."""

    @abstractmethod
    def get_cached(self, module_id: str, max_age_seconds: float) -> CapitalFlowMonitorModuleResult | None:
        """The cached result for module_id if one exists and is
        younger than max_age_seconds, else None (either never cached,
        or the cached entry has aged past the caller's own freshness
        requirement)."""

    @abstractmethod
    def set_cached(self, result: CapitalFlowMonitorModuleResult) -> None:
        """Stores/overwrites the cached result for this module_id."""
