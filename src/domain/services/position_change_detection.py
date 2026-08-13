"""Pure logic: diff two quarters of one filer's aggregated portfolio
into a list of real position changes.

No network or database dependency — takes two already-fetched,
already-aggregated portfolios (see AggregatedPosition's own docstring
for why aggregation across multi-line-item splits within one filing
happens BEFORE this function ever runs) and returns what actually
changed.
"""
from __future__ import annotations

from src.domain.entities.aggregated_position import AggregatedPosition
from src.domain.entities.position_change import PositionChange


def detect_position_changes(
    prior_portfolio: list[AggregatedPosition],
    current_portfolio: list[AggregatedPosition],
    min_pct_change: float = 0.0,
) -> list[PositionChange]:
    """min_pct_change filters out "increased"/"decreased" changes
    smaller than this fraction (e.g. 0.01 for 1%) — "new" and "closed"
    positions are always included regardless, since going from zero to
    something (or the reverse) is never a rounding artifact."""
    prior_by_cusip = {p.cusip: p for p in prior_portfolio}
    current_by_cusip = {p.cusip: p for p in current_portfolio}

    changes: list[PositionChange] = []

    for cusip, current in current_by_cusip.items():
        prior = prior_by_cusip.get(cusip)

        if prior is None:
            changes.append(PositionChange(
                cusip=cusip, issuer_name=current.issuer_name, change_type="new",
                prior_shares=0, current_shares=current.total_shares,
                prior_value_usd=0, current_value_usd=current.total_value_usd,
                pct_change=None,
            ))
            continue

        if prior.total_shares == current.total_shares:
            continue  # genuinely unchanged — not a "change" at all (this also
            # correctly catches prior==current==0, so no division-by-zero risk below)

        if prior.total_shares == 0:
            # Real, confirmed scenario, not hypothetical: FMR LLC (Fidelity's
            # parent) genuinely has real positions where every individual
            # line item's shares sum to exactly zero for a quarter, even
            # though the cusip is present in that quarter's raw data
            # (confirmed directly against real production data). Economically
            # this IS a new position -- the filer effectively held zero of
            # this security before -- so classify it that way rather than
            # dividing by zero to compute a percent change that has no
            # meaningful denominator.
            changes.append(PositionChange(
                cusip=cusip, issuer_name=current.issuer_name, change_type="new",
                prior_shares=0, current_shares=current.total_shares,
                prior_value_usd=prior.total_value_usd, current_value_usd=current.total_value_usd,
                pct_change=None,
            ))
            continue

        pct_change = (current.total_shares - prior.total_shares) / prior.total_shares
        if abs(pct_change) < min_pct_change:
            continue

        changes.append(PositionChange(
            cusip=cusip, issuer_name=current.issuer_name,
            change_type="increased" if pct_change > 0 else "decreased",
            prior_shares=prior.total_shares, current_shares=current.total_shares,
            prior_value_usd=prior.total_value_usd, current_value_usd=current.total_value_usd,
            pct_change=pct_change,
        ))

    for cusip, prior in prior_by_cusip.items():
        if cusip not in current_by_cusip:
            changes.append(PositionChange(
                cusip=cusip, issuer_name=prior.issuer_name, change_type="closed",
                prior_shares=prior.total_shares, current_shares=0,
                prior_value_usd=prior.total_value_usd, current_value_usd=0,
                pct_change=None,
            ))

    return changes
