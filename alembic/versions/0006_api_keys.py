"""add api_keys table

Revision ID: 0006_api_keys
Revises: 0005_monitoring
Create Date: 2026-07-28

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_api_keys"
down_revision: Union[str, None] = "0005_monitoring"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("key_hash", sa.String(64), primary_key=True),
        sa.Column("key_prefix", sa.String(32), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])


def downgrade() -> None:
    op.drop_table("api_keys")
