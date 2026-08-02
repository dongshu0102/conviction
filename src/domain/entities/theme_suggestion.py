"""Domain entities for AI-suggested investment themes.

The one genuine break from this platform's "AI narrates, human directs"
pattern would be an AI that creates and populates a theme on its own —
deliberately NOT what this does. SuggestThemeUseCase only ever
PROPOSES; creating the theme and tagging tickers still goes through the
existing create_universe_theme / add_ticker_to_theme tools, which is
what makes this safe rather than a new autonomous-action surface.

Ticker hallucination risk is handled structurally, not just by prompt
instruction: a suggested ticker that isn't already ingested is
explicitly flagged as such, and the natural next step (ingesting it)
will itself fail cleanly if the ticker isn't real — a hallucinated
symbol self-corrects rather than silently entering the system.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SuggestedTicker:
    ticker: str
    company_name: str
    reasoning: str
    # False means "not yet in this system" — the caller must ingest it
    # (ingest_company or ingest_etf) before it can be tagged into a
    # theme. This is the self-correcting check against a hallucinated
    # ticker: ingestion will fail cleanly if the symbol isn't real.
    already_ingested: bool


@dataclass(frozen=True, slots=True)
class ThemeSuggestion:
    theme_name: str
    rationale: str
    candidate_tickers: list[SuggestedTicker]
    # The actual headlines that grounded this suggestion — lets a
    # reviewer see exactly what real signal drove it, not just trust
    # the model's summary of "the news."
    sourced_headlines: list[str] = field(default_factory=list)
    generated_at: datetime | None = None
    model_used: str = ""
