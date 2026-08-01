"""Domain entities for watchlist triage.

The triage score is a deterministic composite of real, computed
signals — the LLM narrates the result but never invents or adjusts
the numbers, same discipline as the stock screener.

SIGN CONVENTION — learned the hard way from the screener's inverted
narrative bug: triage_score is an ATTENTION score, so HIGHER = more
attention-worthy. It is not a quality or buy ranking; a stock can
score high because it's collapsing. Every consumer of this data must
be told this explicitly (see the scoring_note embedded in the chat
tool's response).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class TriageSignals:
    """Each signal is None when the underlying data needed to compute
    it doesn't exist (no prior snapshot, no add-time baseline, no
    P/E) — never silently zero. A None signal contributes nothing to
    the score AND is visibly absent, so the narrative can be honest
    about what the score is and isn't based on."""

    day_move_pct: float | None  # vs last monitoring snapshot
    move_since_added_pct: float | None  # vs added_price baseline
    pe_drift_pct: float | None  # current P/E vs added_pe baseline
    target_crossed: bool  # current price at or below target_price
    current_price: float | None
    current_pe: float | None


@dataclass(frozen=True, slots=True)
class WatchlistTriageItem:
    ticker: str
    list_name: str
    triage_score: float  # HIGHER = more attention-worthy (not a quality rank)
    signals: TriageSignals
    notes: str | None  # the user's thesis, passed through for the narrative


@dataclass(frozen=True, slots=True)
class WatchlistTriageResult:
    user_id: str
    as_of: datetime
    items: list[WatchlistTriageItem] = field(default_factory=list)  # sorted, highest score first
    tickers_excluded: list[str] = field(default_factory=list)  # quote fetch failed entirely
