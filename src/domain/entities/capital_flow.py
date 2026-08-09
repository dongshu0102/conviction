"""Domain entities for the Capital Flow Agent.

Deliberately NOT the same Alert/PriceSnapshot entities used by
per-user watchlist monitoring (monitoring.py) — that system is scoped
to one user's tracked tickers, comparing against a stored baseline
for THAT user. Capital Flow is a broad, market-wide scan: no ticker
list, no per-user baseline, just "did anything unusually large happen
anywhere." A CapitalFlowEvent belongs to the whole platform, not to
any one user, and the dedup baseline (CapitalFlowSeen) exists purely
so the same underlying real-world event — insider trade, political
disclosure — isn't re-reported every time the scan runs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


class CapitalFlowSource(str, Enum):
    INSIDER = "INSIDER"
    SENATE = "SENATE"
    HOUSE = "HOUSE"
    VOLUME = "VOLUME"
    MACRO = "MACRO"


class CapitalFlowDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    # Genuinely unclear which direction, or the concept doesn't apply
    # (e.g. a macro series moving without an inherent buy/sell sense) —
    # never forced into BUY or SELL when the underlying data doesn't
    # actually say which.
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class InsiderTrade:
    """One real row from FMP's insider-trading/latest feed. Kept close
    to FMP's own field names/shapes rather than renamed for "cleanliness"
    — this is the boundary layer, fmp_parsing.py already isolates the
    JSON quirks (string CIKs, etc); this entity is the clean result of
    that parsing, not a second translation layer."""

    symbol: str
    filing_date: date
    transaction_date: date
    reporting_name: str
    type_of_owner: str
    transaction_type: str  # FMP's own codes, e.g. "P-Purchase", "S-Sale", "G-Gift", "C-Conversion"
    acquisition_or_disposition: str  # "A" or "D" — the real, clean buy/sell signal, not transaction_type parsing
    securities_transacted: float
    price: float  # can genuinely be 0 (stock/option grants, not open-market activity)
    security_name: str
    url: str


@dataclass(frozen=True, slots=True)
class PoliticianTrade:
    """One real row from FMP's senate-latest or house-latest feed.
    Both chambers share this one entity — their real field shapes are
    close enough (same core columns) that a second, near-duplicate
    entity would just be noise; fmp_parsing.py's two separate parse
    functions handle each chamber's own real quirks (House's reused
    'senateID' field name, House's extra capitalGainsOver200USD field,
    Senate's plain office vs House's district-coded format)."""

    chamber: CapitalFlowSource  # SENATE or HOUSE
    symbol: str
    disclosure_date: date
    transaction_date: date
    person_name: str
    office: str
    owner: str  # "Self", "Spouse", "Joint", or genuinely "" when FMP doesn't report it (seen in real House data)
    asset_description: str
    asset_type: str
    transaction_type: str  # "Purchase" or "Sale", FMP's own real values
    amount_range: str  # legally-required disclosure RANGE, e.g. "$15,001 - $50,000" — never an exact dollar figure
    link: str


@dataclass(frozen=True, slots=True)
class CapitalFlowEvent:
    """One detected, real, unusually-large capital-flow event, ready
    to surface to a user — the common, normalized shape all 4 sources
    (insider, senate, house, volume, macro) get reduced to, so the
    REST/chat/frontend layers deal with one shape, not four."""

    source: CapitalFlowSource
    symbol: str | None  # None for MACRO events, which aren't about a single ticker
    event_date: date
    direction: CapitalFlowDirection
    headline: str  # a real, human-readable one-line summary, built from the real underlying fields — never templated filler
    detail_url: str | None
    detected_at: datetime
    # A unique, stable key identifying the underlying real-world event
    # (not this detection) — used purely for dedup against
    # CapitalFlowSeen, never shown to a user.
    dedup_key: str
    # True/False only for SENATE/HOUSE, where a real, known 45-day
    # STOCK Act deadline exists between transaction_date and
    # disclosure_date. None for every other source — INSIDER, VOLUME,
    # and MACRO have no equivalent statutory disclosure deadline, and
    # forcing a False there would misrepresent "not applicable" as
    # "on time."
    is_late_filing: bool | None = None
