"""add conviction_screener_results table

Revision ID: 0028_conviction_screener_results
Revises: 0027_cusip_ticker_map
Create Date: 2026-08-16

Backs the market-wide Conviction Summary screener: a full S&P 500 scan
runs as a background job (hundreds of tickers, thousands of live API
calls, minutes to complete -- genuinely too slow and expensive to run
per-request), storing one lightweight summary row per ticker here so
browsing/sorting/filtering the results afterward is fast and free of
further live calls. Same "latest-only cache" pattern as
factor_scores: one row per ticker, overwritten on each refresh, with a
shared as_of timestamp so staleness is honestly knowable from any
single row -- deliberately no separate metadata/status table.

Lightweight by design: only the three signal booleans and the tally,
not the full holder/disclosure/transaction detail behind them, which
stays live-only and is fetched fresh (via GetConvictionSummaryUseCase,
the existing single-ticker endpoint) only when a specific ticker's
full detail is actually requested -- keeping this table small and the
scan itself as cheap as it can genuinely be.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0028_conviction_screener_results"
down_revision: Union[str, None] = "0027_cusip_ticker_map"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conviction_screener_results",
        sa.Column("ticker", sa.String(), sa.ForeignKey("companies.ticker"), primary_key=True),
        sa.Column("as_of", sa.DateTime(), nullable=False),
        sa.Column("institutional_signal", sa.Boolean(), nullable=False),
        sa.Column("activist_signal", sa.Boolean(), nullable=False),
        sa.Column("insider_signal", sa.Boolean(), nullable=False),
        sa.Column("signal_count", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_conviction_screener_results_as_of", "conviction_screener_results", ["as_of"],
    )
    op.create_index(
        "ix_conviction_screener_results_signal_count", "conviction_screener_results", ["signal_count"],
    )


def downgrade() -> None:
    op.drop_index("ix_conviction_screener_results_signal_count", table_name="conviction_screener_results")
    op.drop_index("ix_conviction_screener_results_as_of", table_name="conviction_screener_results")
    op.drop_table("conviction_screener_results")
