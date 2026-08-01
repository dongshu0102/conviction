"""smart watchlist: named lists, targets, thresholds, add-time baselines

Revision ID: 0008_smart_watchlist
Revises: 0007_option_holdings
Create Date: 2026-07-31

Existing rows get list_name='Default' via server_default, so the new
NOT NULL column is safe on a populated table. The unique constraint
changes from (user_id, ticker) to (user_id, list_name, ticker) so the
same ticker can appear on two different named lists.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_smart_watchlist"
down_revision: Union[str, None] = "0007_option_holdings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "watchlist_items",
        sa.Column("list_name", sa.String(128), nullable=False, server_default="Default"),
    )
    op.add_column("watchlist_items", sa.Column("target_price", sa.Float(), nullable=True))
    op.add_column("watchlist_items", sa.Column("alert_threshold_pct", sa.Float(), nullable=True))
    op.add_column("watchlist_items", sa.Column("added_price", sa.Float(), nullable=True))
    op.add_column("watchlist_items", sa.Column("added_pe", sa.Float(), nullable=True))

    op.drop_constraint("uq_watchlist_user_ticker", "watchlist_items", type_="unique")
    op.create_unique_constraint(
        "uq_watchlist_user_list_ticker", "watchlist_items", ["user_id", "list_name", "ticker"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_watchlist_user_list_ticker", "watchlist_items", type_="unique")
    op.create_unique_constraint(
        "uq_watchlist_user_ticker", "watchlist_items", ["user_id", "ticker"]
    )
    op.drop_column("watchlist_items", "added_pe")
    op.drop_column("watchlist_items", "added_price")
    op.drop_column("watchlist_items", "alert_threshold_pct")
    op.drop_column("watchlist_items", "target_price")
    op.drop_column("watchlist_items", "list_name")
