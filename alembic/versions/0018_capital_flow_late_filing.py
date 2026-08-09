"""capital_flow_events: add is_late_filing column

Revision ID: 0018_capital_flow_late_filing
Revises: 0017_capital_flow
Create Date: 2026-08-09

Fixes a real, genuine gap found during a review pass: the
is_late_filing field was added to the CapitalFlowEvent domain entity
and correctly computed by build_politician_event() (hand-verified
against a real production case — a Senate disclosure filed 817 days
late), but the SqlAlchemyCapitalFlowRepository never actually wrote or
read this field, and CapitalFlowEventModel never had a column for it
at all. Every real is_late_filing flag was being silently discarded
the moment an event was saved. This migration adds the missing
column; the repository fix ships in the same commit.

Nullable, matching the domain entity's own convention — only ever
True/False for SENATE/HOUSE events (the only sources with a real
STOCK Act deadline), genuinely NULL for INSIDER/VOLUME/MACRO rather
than a fabricated False standing in for "not applicable." Existing
rows (all inserted before this column existed) will read back as NULL
automatically, which is the correct, honest value for them — this
platform genuinely doesn't know whether they were late, since the
flag was never computed and stored for them at the time.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0018_capital_flow_late_filing"
down_revision: Union[str, None] = "0017_capital_flow"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "capital_flow_events",
        sa.Column("is_late_filing", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("capital_flow_events", "is_late_filing")
