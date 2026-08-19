"""Contract any LLM-backed Master Lens narrative generator must satisfy.

Same pattern as ResearchGenerator: the use case depends on this
abstraction, never on the Anthropic SDK directly.

Deliberately generates all 10 narratives in ONE call, not ten separate
ones -- they're all for the same ticker and each one's own score and
score_basis are already computed deterministically before this is ever
invoked, so a single request with all ten (score, basis) pairs in
context is both cheaper and faster than ten round trips for an
on-demand, single-ticker feature.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.domain.entities.financial_analysis import CompanyFinancialAnalysis
from src.domain.entities.valuation_snapshot import ValuationSnapshot


@dataclass(frozen=True, slots=True)
class MasterLensScoredInput:
    """One lens's own, already-computed score and basis -- the ONLY
    grounding this specific narrative is allowed to draw from, plus
    the master's own name and lens label for the prompt to address."""
    master_name: str
    lens_label: str
    score: float | None
    score_basis: str


@dataclass(frozen=True, slots=True)
class MasterLensNarrativeResult:
    narratives: dict[str, str]  # keyed by master_name, exactly the 10 given as input
    model_used: str
    raw_response: dict


class MasterLensNarrativeGenerator(ABC):
    @abstractmethod
    def generate(
        self,
        ticker: str,
        analysis: CompanyFinancialAnalysis,
        valuation: ValuationSnapshot | None,
        scored_inputs: list[MasterLensScoredInput],
    ) -> MasterLensNarrativeResult:
        """Produce one grounded narrative per master, explaining each
        one's OWN already-computed score and score_basis through that
        investor's real, documented framework -- never independently
        re-deriving or contradicting the deterministic score itself."""


class MasterLensGenerationError(Exception):
    """Raised on any LLM provider failure -- use cases catch this,
    never a provider-specific exception."""
