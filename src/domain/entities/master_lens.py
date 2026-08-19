"""Domain entities for the "Master Lens" watchlist feature.

Ten historically significant investors, each represented as a
distinct analytical MODEL applied to a ticker's real, already-ingested
financial data -- deliberately not a biography or a quote generator.
Every lens produces two things: a deterministic, arithmetic score (0
to 10, computed the same way every time from the same inputs, same
"pure function" discipline as ComputeFinancialAnalysisUseCase) and an
LLM-generated narrative that explains the score using that specific
investor's real, documented framework -- grounded in the same
underlying numbers the score itself was computed from, never
independently improvised.

Score is deliberately None, not a fabricated 0-10 value, when the
underlying data can't support the calculation (e.g. a single-year-old
company with no year-over-year growth to measure) -- same "missing is
not zero" discipline as YearlyRatios itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class MasterLensResult:
    master_name: str  # e.g. "Buffett"
    lens_label: str  # e.g. "Moats & Owner Earnings" -- the model's own name, not a bio title
    score: float | None  # 0-10, deterministic; None when inputs are insufficient
    score_basis: str  # a short, honest note on exactly what was computed, e.g. "avg gross margin 42%, FCF margin 12%"
    narrative: str  # LLM-generated, grounded explicitly in the same real numbers behind the score


@dataclass(frozen=True, slots=True)
class MasterLensAnalysis:
    ticker: str
    generated_at: datetime
    results: tuple[MasterLensResult, ...]  # always exactly 10, in the fixed, documented order below
    model_used: str
