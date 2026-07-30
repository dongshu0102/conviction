"""baseline schema — companies + financial statements

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-27

This migration mirrors src/infrastructure/persistence/models.py exactly
as it stood after Phase 1 was validated against 175 real S&P 500
companies. Written by hand rather than via `alembic revision
--autogenerate`, since that requires a live DB connection.

IMPORTANT — if you're adopting this on a database that already has these
tables (created via the app's create_all() during development, as this
project's did), do NOT run `alembic upgrade head` directly — it will try
to CREATE TABLE on tables that already exist and fail. Instead run:

    alembic stamp head

This tells Alembic "the schema already matches this revision" without
re-running the DDL. Every migration after this one uses upgrade/downgrade
normally.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("ticker", sa.String(10), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("sector", sa.String(64), nullable=False),
        sa.Column("industry", sa.String(128), nullable=False),
        sa.Column("exchange", sa.String(32), nullable=False),
        sa.Column("country", sa.String(64), nullable=False),
        sa.Column("ipo_date", sa.Date(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("website", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "income_statements",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(10), sa.ForeignKey("companies.ticker"), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("fiscal_quarter", sa.Integer(), nullable=True),
        sa.Column("period", sa.String(16), nullable=False),
        sa.Column("fiscal_date_ending", sa.Date(), nullable=False),
        sa.Column("reported_currency", sa.String(8), nullable=False),
        sa.Column("revenue", sa.Float(), nullable=True),
        sa.Column("cost_of_revenue", sa.Float(), nullable=True),
        sa.Column("gross_profit", sa.Float(), nullable=True),
        sa.Column("operating_expenses", sa.Float(), nullable=True),
        sa.Column("operating_income", sa.Float(), nullable=True),
        sa.Column("net_income", sa.Float(), nullable=True),
        sa.Column("eps_basic", sa.Float(), nullable=True),
        sa.Column("eps_diluted", sa.Float(), nullable=True),
        sa.Column("ebitda", sa.Float(), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.UniqueConstraint(
            "ticker", "fiscal_year", "fiscal_quarter", "period", name="uq_income_period"
        ),
    )
    op.create_index("ix_income_statements_ticker", "income_statements", ["ticker"])

    op.create_table(
        "balance_sheets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(10), sa.ForeignKey("companies.ticker"), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("fiscal_quarter", sa.Integer(), nullable=True),
        sa.Column("period", sa.String(16), nullable=False),
        sa.Column("fiscal_date_ending", sa.Date(), nullable=False),
        sa.Column("reported_currency", sa.String(8), nullable=False),
        sa.Column("total_assets", sa.Float(), nullable=True),
        sa.Column("total_current_assets", sa.Float(), nullable=True),
        sa.Column("cash_and_equivalents", sa.Float(), nullable=True),
        sa.Column("total_liabilities", sa.Float(), nullable=True),
        sa.Column("total_current_liabilities", sa.Float(), nullable=True),
        sa.Column("total_debt", sa.Float(), nullable=True),
        sa.Column("total_equity", sa.Float(), nullable=True),
        sa.Column("shares_outstanding", sa.Float(), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.UniqueConstraint(
            "ticker", "fiscal_year", "fiscal_quarter", "period", name="uq_balance_period"
        ),
    )
    op.create_index("ix_balance_sheets_ticker", "balance_sheets", ["ticker"])

    op.create_table(
        "cash_flow_statements",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(10), sa.ForeignKey("companies.ticker"), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("fiscal_quarter", sa.Integer(), nullable=True),
        sa.Column("period", sa.String(16), nullable=False),
        sa.Column("fiscal_date_ending", sa.Date(), nullable=False),
        sa.Column("reported_currency", sa.String(8), nullable=False),
        sa.Column("operating_cash_flow", sa.Float(), nullable=True),
        sa.Column("capital_expenditures", sa.Float(), nullable=True),
        sa.Column("free_cash_flow", sa.Float(), nullable=True),
        sa.Column("dividends_paid", sa.Float(), nullable=True),
        sa.Column("net_change_in_cash", sa.Float(), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.UniqueConstraint(
            "ticker", "fiscal_year", "fiscal_quarter", "period", name="uq_cashflow_period"
        ),
    )
    op.create_index("ix_cash_flow_statements_ticker", "cash_flow_statements", ["ticker"])


def downgrade() -> None:
    op.drop_table("cash_flow_statements")
    op.drop_table("balance_sheets")
    op.drop_table("income_statements")
    op.drop_table("companies")
