"""earnings alerts: change_pct becomes nullable

Revision ID: 0011_earnings_alerts
Revises: 0010_universe_themes
Create Date: 2026-08-01

change_pct was NOT NULL, correct for the two existing alert types
(PRICE_MOVE, TARGET_REACHED) which are always about a percentage move.
The new EARNINGS_UPCOMING alert type has no percentage-move concept at
all — nullable is the honest representation, not a fabricated 0.0.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011_earnings_alerts"
down_revision: Union[str, None] = "0010_universe_themes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("alerts", "change_pct", existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    # Existing NULL rows (any EARNINGS_UPCOMING alerts) would violate
    # NOT NULL on downgrade — backfill to 0.0 first so the downgrade
    # doesn't fail outright, accepting the minor inaccuracy since this
    # only runs if someone is reverting the feature entirely.
    op.execute("UPDATE alerts SET change_pct = 0.0 WHERE change_pct IS NULL")
    op.alter_column("alerts", "change_pct", existing_type=sa.Float(), nullable=False)
