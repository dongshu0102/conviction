"""factor scores: cross-sectional universe cache

Revision ID: 0009_factor_scores
Revises: 0008_smart_watchlist
Create Date: 2026-08-01

Latest-only cache table, one row per ticker, overwritten on each
universe refresh — same shape as the price_snapshots table's
latest-value pattern. No history is kept; a historical factor time
series is a deliberately deferred future scope, not an oversight.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_factor_scores"
down_revision: Union[str, None] = "0008_smart_watchlist"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "factor_scores",
        sa.Column("ticker", sa.String(), sa.ForeignKey("companies.ticker"), primary_key=True),
        sa.Column("as_of", sa.DateTime(), nullable=False),
        sa.Column("price_to_earnings", sa.Float(), nullable=True),
        sa.Column("return_on_equity", sa.Float(), nullable=True),
        sa.Column("revenue_growth_yoy", sa.Float(), nullable=True),
        sa.Column("momentum_1m_pct", sa.Float(), nullable=True),
        sa.Column("market_cap", sa.Float(), nullable=True),
        sa.Column("value_z", sa.Float(), nullable=True),
        sa.Column("quality_z", sa.Float(), nullable=True),
        sa.Column("growth_z", sa.Float(), nullable=True),
        sa.Column("momentum_z", sa.Float(), nullable=True),
        sa.Column("size_z", sa.Float(), nullable=True),
    )
    op.create_index("ix_factor_scores_as_of", "factor_scores", ["as_of"])


def downgrade() -> None:
    op.drop_index("ix_factor_scores_as_of", table_name="factor_scores")
    op.drop_table("factor_scores")
