"""widen alembic_version.version_num to prevent this failure class recurring

Revision ID: 0024_widen_alembic_version
Revises: 0023_holdings_bigint
Create Date: 2026-08-12

Defensive fix, not a feature change: alembic's own version_num column
defaults to VARCHAR(32), and 0023's original, longer revision id
("0023_institutional_holdings_bigint", 35 chars) silently exceeded it
-- confirmed directly from real App Runner application logs as
psycopg2.errors.StringDataRightTruncation, right after that
migration's actual schema changes had already succeeded. App Runner
then automatically rolled back every deployment for over a day without
this ever surfacing as an obviously-labeled error anywhere in CI.
Widening this column to VARCHAR(128) removes the failure mode itself,
rather than relying solely on remembering to keep every future
revision id under 32 characters by hand.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0024_widen_alembic_version"
down_revision: Union[str, None] = "0023_holdings_bigint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "alembic_version", "version_num",
        existing_type=sa.String(length=32), type_=sa.String(length=128),
    )


def downgrade() -> None:
    op.alter_column(
        "alembic_version", "version_num",
        existing_type=sa.String(length=128), type_=sa.String(length=32),
    )
