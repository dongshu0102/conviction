"""curated investment universe: global themes + many-to-many membership

Revision ID: 0010_universe_themes
Revises: 0009_factor_scores
Create Date: 2026-08-01

Themes are global (system-wide), not per-user — a shared taxonomy, same
scope as the S&P 500 universe itself. Membership is a proper join table
(not a label column like watchlist list_name) because an empty,
not-yet-populated theme is a legitimate state here: themes are typically
created first, then populated, unlike personal watchlists.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_universe_themes"
down_revision: Union[str, None] = "0009_factor_scores"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "universe_themes",
        sa.Column("name", sa.String(128), primary_key=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "universe_theme_memberships",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("theme_name", sa.String(128), sa.ForeignKey("universe_themes.name"), nullable=False),
        sa.Column("ticker", sa.String(), sa.ForeignKey("companies.ticker"), nullable=False),
    )
    op.create_index("ix_theme_membership_theme_name", "universe_theme_memberships", ["theme_name"])
    op.create_index("ix_theme_membership_ticker", "universe_theme_memberships", ["ticker"])
    op.create_unique_constraint(
        "uq_theme_membership_theme_ticker",
        "universe_theme_memberships",
        ["theme_name", "ticker"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_theme_membership_theme_ticker", "universe_theme_memberships", type_="unique"
    )
    op.drop_index("ix_theme_membership_ticker", table_name="universe_theme_memberships")
    op.drop_index("ix_theme_membership_theme_name", table_name="universe_theme_memberships")
    op.drop_table("universe_theme_memberships")
    op.drop_table("universe_themes")
