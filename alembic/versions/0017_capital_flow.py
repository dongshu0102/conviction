"""capital flow events: broad market-wide insider/political trading scan results

Revision ID: 0017_capital_flow
Revises: 0016_growth_candidates
Create Date: 2026-08-09

Deliberately platform-wide, not per-user, unlike every other monitoring
table in this schema (alerts, price_snapshots, speculative_growth_candidates
are all scoped to a user_id) — Capital Flow is a broad market scan with
no watchlist, so there's nothing to scope it to. symbol is NOT a foreign
key to companies.ticker, unlike alerts.ticker: most symbols this scan
detects were never ingested into this platform's own companies table at
all, and a foreign key here would make a real insert fail for the common
case, not the exception. dedup_key carries a real, enforced unique
constraint — it's the actual mechanism preventing the same real-world
event from being persisted twice across separate scan runs, not just an
application-layer convention.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017_capital_flow"
down_revision: Union[str, None] = "0016_growth_candidates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "capital_flow_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(), nullable=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("headline", sa.String(), nullable=False),
        sa.Column("detail_url", sa.String(), nullable=True),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.Column("dedup_key", sa.String(), nullable=False),
    )
    op.create_index("ix_capital_flow_symbol", "capital_flow_events", ["symbol"])
    op.create_index("ix_capital_flow_source", "capital_flow_events", ["source"])
    op.create_index("ix_capital_flow_detected_at", "capital_flow_events", ["detected_at"])
    op.create_unique_constraint(
        "uq_capital_flow_dedup_key", "capital_flow_events", ["dedup_key"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_capital_flow_dedup_key", "capital_flow_events", type_="unique")
    op.drop_index("ix_capital_flow_detected_at", table_name="capital_flow_events")
    op.drop_index("ix_capital_flow_source", table_name="capital_flow_events")
    op.drop_index("ix_capital_flow_symbol", table_name="capital_flow_events")
    op.drop_table("capital_flow_events")
