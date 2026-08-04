"""User roles: add role column, defaulting every existing account to 'user'

Revision ID: 0015_user_roles
Revises: 0014_password_reset
Create Date: 2026-08-04

Purely additive. Every existing account (including the operator's own)
defaults to 'user' — becoming an admin requires an explicit, separate
step documented in the README, never automatic. See auth.py's admin
router for how the very first admin gets bootstrapped.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015_user_roles"
down_revision: Union[str, None] = "0014_password_reset"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", sa.String(16), nullable=False, server_default="user"),
    )


def downgrade() -> None:
    op.drop_column("users", "role")
