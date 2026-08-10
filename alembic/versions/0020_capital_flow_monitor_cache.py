"""capital_flow_monitor_agent_cache table

Revision ID: 0020_capital_flow_monitor_cache
Revises: 0019_capital_flow_monitor
Create Date: 2026-08-10

A shared, GLOBAL cache (module_id is the primary key, no user_id) for
the Capital Flow Monitor's 9 agent-backed module results — every
user's load of the same module within the cache window is served from
one real, costly web_search-enabled Anthropic call instead of each
triggering its own. Deliberately separate from
capital_flow_monitor_snapshots (per-user history), a different concern.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0020_capital_flow_monitor_cache"
down_revision: Union[str, None] = "0019_capital_flow_monitor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "capital_flow_monitor_agent_cache",
        sa.Column("module_id", sa.String(length=32), primary_key=True),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("cached_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_capital_flow_monitor_agent_cache_cached_at",
        "capital_flow_monitor_agent_cache", ["cached_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_capital_flow_monitor_agent_cache_cached_at", table_name="capital_flow_monitor_agent_cache")
    op.drop_table("capital_flow_monitor_agent_cache")
