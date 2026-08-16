from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InstitutionalHolderSignal:
    """One top institutional holder's real, reported position in this
    security, and whether their most recent quarter-over-quarter
    change was a genuine increase -- is_increasing is None, not False,
    when this genuinely couldn't be determined (e.g. only one quarter
    of data exists for that filer yet), since that's a real, different
    state from "confirmed not increasing" and conflating the two would
    misrepresent the data."""

    filer_name: str
    current_shares: int
    current_value_usd: int
    is_increasing: bool | None


@dataclass(frozen=True, slots=True)
class ConvictionSummary:
    """A single ticker's real, combined signal across three genuinely
    different, independent SEC disclosure regimes -- institutional
    accumulation (13F), activist intent (13D), and insider buying
    (Form 4). signal_count is a simple, honest tally (0-3) of how many
    of these three categories show real, current buying activity, not
    a fabricated, falsely-precise numeric score -- deliberately kept
    this coarse so it can't be mistaken for more rigor than the
    underlying, genuinely disparate data actually supports."""

    ticker: str
    institutional_holders: tuple[InstitutionalHolderSignal, ...]
    institutional_signal: bool  # True if any checked top holder is genuinely increasing
    activist_disclosures_13d: tuple  # tuple[BeneficialOwnershipDisclosure, ...], most recent first
    activist_signal: bool  # True if a real 13D (not just 13G) exists among recent disclosures
    insider_purchases: tuple  # tuple[InsiderTransaction, ...], genuine P-Purchase at non-zero price only
    insider_signal: bool  # True if a real, discretionary insider purchase exists
    signal_count: int  # 0-3, the honest tally of the three booleans above
