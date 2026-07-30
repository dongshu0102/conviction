"""Domain entity for AI-generated company research.

Deliberately stores the model identifier and the financial data snapshot
it was grounded in, alongside the generated text. This is what makes the
report auditable later — "what data was this conclusion based on, and
which model produced it" — rather than an opaque LLM output no one can
trace back to a source.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CompanyResearchReport:
    ticker: str
    business_overview: str
    financial_highlights: str
    competitive_position: str
    key_risks: str
    generated_at: datetime
    model_used: str
    # Fiscal year of the data this report was grounded in — lets a
    # consumer know if a report is stale relative to newer filings.
    grounded_fiscal_year: int | None = None
    raw_response: dict = field(default_factory=dict, repr=False, compare=False)
