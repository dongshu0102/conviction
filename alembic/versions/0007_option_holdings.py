"""add option_holdings table

Revision ID: 0007_option_holdings
Revises: 0006_api_keys
Create Date: 2026-07-31

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_option_holdings"
down_revision: Union[str, None] = "0006_api_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "option_holdings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "portfolio_id", sa.String(36), sa.ForeignKey("portfolios.portfolio_id"),
            nullable=False,
        ),
        # No FK to companies.ticker (unlike portfolio_holdings) — options
        # can exist on indices/ETFs outside our ingested company universe.
        sa.Column("underlying_ticker", sa.String(16), nullable=False),
        sa.Column("strike", sa.Float(), nullable=False),
        sa.Column("expiration", sa.Date(), nullable=False),
        sa.Column("option_type", sa.String(4), nullable=False),
        sa.Column("contracts_held", sa.Integer(), nullable=False),
        sa.Column("cost_basis_per_contract", sa.Float(), nullable=False),
        sa.Column("acquired_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "portfolio_id", "underlying_ticker", "strike", "expiration", "option_type",
            name="uq_option_holding_contract",
        ),
    )
    op.create_index("ix_option_holdings_portfolio_id", "option_holdings", ["portfolio_id"])
    op.create_index("ix_option_holdings_underlying_ticker", "option_holdings", ["underlying_ticker"])


def downgrade() -> None:
    op.drop_table("option_holdings")
