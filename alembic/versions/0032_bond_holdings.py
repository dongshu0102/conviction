"""add bond_holdings table

Revision ID: 0032_bond_holdings
Revises: 0031_nasdaq100_classifications
Create Date: 2026-09-03

Bond holdings for a portfolio, structurally analogous to
option_holdings, not stock_holdings: bonds have no real, single ticker
to key on, so identity is the full, real set of terms that genuinely
distinguish one bond from another (issuer, coupon rate, maturity
date), matching the same discipline already used for option contracts
(underlying + strike + expiration + type). cusip is stored when known
but is deliberately NOT the unique key -- it's frequently unavailable
for a manually-entered holding, and a NULL cusip must never silently
collide with another NULL cusip under a unique constraint.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0032_bond_holdings"
down_revision: Union[str, None] = "0031_nasdaq100_classifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bond_holdings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("portfolio_id", sa.String(), sa.ForeignKey("portfolios.portfolio_id"), nullable=False, index=True),
        sa.Column("cusip", sa.String(9), nullable=True),
        sa.Column("issuer_name", sa.String(), nullable=False),
        sa.Column("coupon_rate", sa.Float(), nullable=False),
        sa.Column("maturity_date", sa.Date(), nullable=False),
        sa.Column("face_value", sa.Float(), nullable=False, server_default="1000.0"),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("cost_basis_price", sa.Float(), nullable=False),
        sa.Column("acquired_at", sa.Date(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_bond_holding_terms", "bond_holdings",
        ["portfolio_id", "issuer_name", "coupon_rate", "maturity_date"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_bond_holding_terms", "bond_holdings", type_="unique")
    op.drop_table("bond_holdings")
