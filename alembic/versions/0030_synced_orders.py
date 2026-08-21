"""add synced_orders table

Revision ID: 0030_synced_orders
Revises: 0029_index_memberships
Create Date: 2026-08-21

Tracks which brokerage order_ids have already been synced into a
portfolio -- a real, live bug was caught directly by the user
tonight: SyncFilledOrderToPortfolioUseCase correctly accumulates
shares each time it's called (necessary for genuinely buying more of
a ticker over time), but with nothing recording "this specific order
was already synced," clicking the "Sync to portfolio" button multiple
times on the SAME order silently double- and triple-counted its real
shares. A client-side-only fix (disabling the button after one click)
would not have survived a page refresh or a direct API call, so this
needs to be enforced at the source of truth -- the database -- not
just the UI.

order_id is the primary key specifically because uniqueness across
ALL orders, not per-user or per-portfolio, is the real invariant that
matters: a specific, real brokerage order was either already synced
once, or it wasn't.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0030_synced_orders"
down_revision: Union[str, None] = "0029_index_memberships"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "synced_orders",
        sa.Column("order_id", sa.String(), primary_key=True),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("synced_orders")
