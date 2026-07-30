"""add price_snapshots and alerts tables

Revision ID: 0005_monitoring
Revises: 0004_portfolios
Create Date: 2026-07-28

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_monitoring"
down_revision: Union[str, None] = "0004_portfolios"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "price_snapshots",
        sa.Column("ticker", sa.String(10), sa.ForeignKey("companies.ticker"), primary_key=True),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("ticker", sa.String(10), sa.ForeignKey("companies.ticker"), nullable=False),
        sa.Column("alert_type", sa.String(32), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("change_pct", sa.Float(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_alerts_user_id", "alerts", ["user_id"])


def downgrade() -> None:
    op.drop_table("alerts")
    op.drop_table("price_snapshots")
