"""add portfolios and portfolio_holdings tables

Revision ID: 0004_portfolios
Revises: 0003_watchlist
Create Date: 2026-07-28

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_portfolios"
down_revision: Union[str, None] = "0003_watchlist"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "portfolios",
        sa.Column("portfolio_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_portfolios_user_id", "portfolios", ["user_id"])

    op.create_table(
        "portfolio_holdings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "portfolio_id", sa.String(36), sa.ForeignKey("portfolios.portfolio_id"),
            nullable=False,
        ),
        sa.Column("ticker", sa.String(10), sa.ForeignKey("companies.ticker"), nullable=False),
        sa.Column("shares", sa.Float(), nullable=False),
        sa.Column("cost_basis_per_share", sa.Float(), nullable=False),
        sa.Column("acquired_at", sa.Date(), nullable=True),
        sa.UniqueConstraint("portfolio_id", "ticker", name="uq_portfolio_holding_ticker"),
    )
    op.create_index("ix_portfolio_holdings_portfolio_id", "portfolio_holdings", ["portfolio_id"])


def downgrade() -> None:
    op.drop_table("portfolio_holdings")
    op.drop_table("portfolios")
