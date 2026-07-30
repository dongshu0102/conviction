"""add watchlist_items table

Revision ID: 0003_watchlist
Revises: 0002_research_reports
Create Date: 2026-07-27

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_watchlist"
down_revision: Union[str, None] = "0002_research_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("ticker", sa.String(10), sa.ForeignKey("companies.ticker"), nullable=False),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.UniqueConstraint("user_id", "ticker", name="uq_watchlist_user_ticker"),
    )
    op.create_index("ix_watchlist_items_user_id", "watchlist_items", ["user_id"])


def downgrade() -> None:
    op.drop_table("watchlist_items")
