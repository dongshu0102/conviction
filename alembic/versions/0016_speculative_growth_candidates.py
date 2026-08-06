"""speculative growth candidates: per-user tracked tickers + last-known state

Revision ID: 0016_speculative_growth_candidates
Revises: 0015_user_roles
Create Date: 2026-08-06

Per-user, unlike universe themes — a candidate is one person's explicit
decision to track a ticker against the "is 100x possible" conditions,
not a shared taxonomy. The last-known-state columns mirror PriceSnapshot's
role for price monitoring: they exist purely so a later check can detect
a genuine change instead of re-alerting on steady-state every run.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016_speculative_growth_candidates"
down_revision: Union[str, None] = "0015_user_roles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "speculative_growth_candidates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        sa.Column("last_growth_trend", sa.String(), nullable=True),
        sa.Column("last_cash_runway_months", sa.Float(), nullable=True),
        sa.Column("last_market_cap", sa.Float(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_growth_candidate_user_id", "speculative_growth_candidates", ["user_id"]
    )
    op.create_unique_constraint(
        "uq_growth_candidate_user_ticker",
        "speculative_growth_candidates",
        ["user_id", "ticker"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_growth_candidate_user_ticker", "speculative_growth_candidates", type_="unique"
    )
    op.drop_index("ix_growth_candidate_user_id", table_name="speculative_growth_candidates")
    op.drop_table("speculative_growth_candidates")
