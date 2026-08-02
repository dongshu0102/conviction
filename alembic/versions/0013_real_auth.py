"""Real auth: users table (email + password, hashed)

Revision ID: 0013_real_auth
Revises: 0012_etf_support
Create Date: 2026-08-02

Purely additive — no existing table touched. user_id here is the
normalized email, the SAME string type already used as the join key
across watchlists/portfolios/alerts/api_keys, so nothing downstream of
authentication needs any migration at all. Pre-existing API keys
created under the old open POST /api-keys flow (before this migration)
continue working exactly as before — they simply have no corresponding
users row, which is fine, since API-key auth never required one.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013_real_auth"
down_revision: Union[str, None] = "0012_etf_support"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(128), primary_key=True),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("users")
