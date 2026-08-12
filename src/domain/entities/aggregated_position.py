from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AggregatedPosition:
    """One filer's TOTAL reported position in one security for one
    quarter — shares and value summed across every individual
    InstitutionalHolding row for that (filer, cusip, period), since a
    single filing can legitimately split the same security across
    multiple line items (e.g. different voting-authority categories
    for different Berkshire Hathaway subsidiary managers, confirmed
    directly against real ingested data). Comparing un-aggregated,
    individual line items across quarters would compare arbitrary
    fragments of a position, not the true, total position size."""

    cusip: str
    issuer_name: str
    total_shares: int
    total_value_usd: int
