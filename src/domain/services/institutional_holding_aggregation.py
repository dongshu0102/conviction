"""Pure logic: sum shares and value across every individual
InstitutionalHolding row for the same CUSIP, producing one
AggregatedPosition per distinct security.

Extracted as a real, shared, pure domain function rather than
re-implemented a third time -- the real SQLAlchemy repository already
does this via SQL GROUP BY (get_aggregated_portfolio), and the fake
test repository duplicates the same logic in pure Python for tests.
This is the same logic again, in reusable form, needed for a genuinely
new case: aggregating FMP-sourced holdings (which arrive as a plain
Python list, not from a query this app's own database can GROUP BY),
for the freshness fallback in position-change detection.
"""
from __future__ import annotations

from src.domain.entities.aggregated_position import AggregatedPosition
from src.domain.entities.institutional_holding import InstitutionalHolding


def aggregate_holdings_by_cusip(holdings: list[InstitutionalHolding]) -> list[AggregatedPosition]:
    by_cusip: dict[str, dict] = {}
    for h in holdings:
        if h.cusip not in by_cusip:
            by_cusip[h.cusip] = {"issuer_name": h.issuer_name, "shares": 0, "value": 0}
        by_cusip[h.cusip]["shares"] += h.shares_or_principal_amount
        by_cusip[h.cusip]["value"] += h.value_usd
    return [
        AggregatedPosition(
            cusip=cusip, issuer_name=data["issuer_name"],
            total_shares=data["shares"], total_value_usd=data["value"],
        )
        for cusip, data in by_cusip.items()
    ]
