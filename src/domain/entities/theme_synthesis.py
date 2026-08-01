"""Domain entity for an AI-generated thematic synthesis across a
curated universe theme.

Deliberately NOT persisted, unlike CompanyResearchReport — a company
research report is meant to be revisited over time as a record of what
was known then; a theme synthesis is exploratory and cheap to
regenerate fresh (grounded in whatever screening/factor data is current
right now), so a stored copy would just as easily go stale and mislead
as help. Generated fresh on every request.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ThemeSynthesisReport:
    theme_name: str
    generated_at: datetime
    tickers_covered: list[str]
    # Tickers in the theme with neither screening nor factor data
    # available — flagged explicitly, same "honest gap" principle used
    # everywhere else, rather than silently narrated around.
    tickers_excluded: list[str]
    overview: str
    common_threads: str
    notable_divergences: str
    key_risks: str
    model_used: str
    raw_response: dict = field(default_factory=dict, repr=False, compare=False)
