"""add research_reports table

Revision ID: 0002_research_reports
Revises: 0001_baseline
Create Date: 2026-07-27

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_research_reports"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_reports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(10), sa.ForeignKey("companies.ticker"), nullable=False),
        sa.Column("business_overview", sa.String(), nullable=False),
        sa.Column("financial_highlights", sa.String(), nullable=False),
        sa.Column("competitive_position", sa.String(), nullable=False),
        sa.Column("key_risks", sa.String(), nullable=False),
        sa.Column("model_used", sa.String(64), nullable=False),
        sa.Column("grounded_fiscal_year", sa.Integer(), nullable=True),
        sa.Column("raw_response", sa.JSON(), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_research_reports_ticker", "research_reports", ["ticker"])


def downgrade() -> None:
    op.drop_table("research_reports")
