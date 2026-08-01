"""ETF support: asset_type flag + fund-specific fields on companies

Revision ID: 0012_etf_support
Revises: 0011_earnings_alerts
Create Date: 2026-08-01

ETFs are modeled as a variant of the SAME companies table (asset_type
column) rather than a parallel entity — every existing "is this ticker
known" check across watchlists, themes, and screening already queries
this table, and reusing it means ETFs participate in all of that for
free. Existing rows get asset_type='EQUITY' via server_default, safe on
a populated table.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_etf_support"
down_revision: Union[str, None] = "0011_earnings_alerts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("asset_type", sa.String(16), nullable=False, server_default="EQUITY"),
    )
    op.add_column("companies", sa.Column("expense_ratio", sa.Float(), nullable=True))
    op.add_column("companies", sa.Column("aum", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "aum")
    op.drop_column("companies", "expense_ratio")
    op.drop_column("companies", "asset_type")
