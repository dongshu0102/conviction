"""add index_memberships table

Revision ID: 0029_index_memberships
Revises: 0028_conviction_screener_results
Create Date: 2026-08-17

Tracks which major index(es) each ticker belongs to (S&P 500,
Nasdaq-100, Dow Jones) -- genuinely many-to-many, not one-to-one:
substantial real overlap exists between these indices (AAPL, MSFT,
NVDA all belong to multiple), confirmed directly tonight when
ingesting Nasdaq-100 + Dow Jones found only 8 tickers genuinely new
beyond the existing S&P 500 universe out of 123 combined.

A separate table rather than a column on companies, since a single
ticker can have zero, one, or several memberships -- a fixed set of
nullable boolean columns would work for exactly three, named indices,
but a table scales honestly to whichever indices this app decides to
track later without another migration.

No FK to companies.ticker's own primary key is enforced as NOT NULL
membership -- a ticker can genuinely exist in companies without being
in this table yet (freshly ingested via a path that doesn't populate
membership), and that absence is meaningful, not an error.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0029_index_memberships"
down_revision: Union[str, None] = "0028_conviction_screener_results"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "index_memberships",
        sa.Column("ticker", sa.String(), sa.ForeignKey("companies.ticker"), primary_key=True),
        sa.Column("index_name", sa.String(), primary_key=True),
    )
    op.create_index(
        "ix_index_memberships_index_name", "index_memberships", ["index_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_index_memberships_index_name", table_name="index_memberships")
    op.drop_table("index_memberships")
