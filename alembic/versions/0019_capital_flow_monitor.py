"""capital_flow_monitor_snapshots table

Revision ID: 0019_capital_flow_monitor
Revises: 0018_capital_flow_late_filing
Create Date: 2026-08-10

Creates the persistence for the new Capital Flow Monitor feature — a
periodic snapshot dashboard, distinct from the existing capital_flow_
events table (the Capital Flow Agent's discrete event detector).
Replaces the original artifact's window.storage persistence with real,
per-user Postgres rows, one per (user_id, snapshot_date).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0019_capital_flow_monitor"
down_revision: Union[str, None] = "0018_capital_flow_late_filing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "capital_flow_monitor_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("signals", sa.JSON(), nullable=False),
        sa.Column("regime_label", sa.String(), nullable=True),
        sa.Column("regime_stance", sa.String(length=16), nullable=True),
        sa.UniqueConstraint("user_id", "snapshot_date", name="uq_cfm_snapshot_user_date"),
    )
    op.create_index(
        "ix_capital_flow_monitor_snapshots_user_id",
        "capital_flow_monitor_snapshots", ["user_id"],
    )
    op.create_index(
        "ix_capital_flow_monitor_snapshots_snapshot_date",
        "capital_flow_monitor_snapshots", ["snapshot_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_capital_flow_monitor_snapshots_snapshot_date", table_name="capital_flow_monitor_snapshots")
    op.drop_index("ix_capital_flow_monitor_snapshots_user_id", table_name="capital_flow_monitor_snapshots")
    op.drop_table("capital_flow_monitor_snapshots")
