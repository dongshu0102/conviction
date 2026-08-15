"""add cusip_ticker_map table

Revision ID: 0027_cusip_ticker_map
Revises: 0026_drop_ghost_13f_table
Create Date: 2026-08-13

Supplements the free, bulk-ingested SEC 13F pipeline with real ticker
symbols from FMP's Ultimate-tier search-cusip endpoint (confirmed
newly accessible tonight, not assumed -- HTTP 200 with real data,
matching this pipeline's own independently-sourced SEC data for the
same real positions). Deliberately NOT a replacement for the SEC
pipeline itself: FMP's 13F endpoints are scoped per-filer or
per-security, with no true bulk/quarterly download, so full-coverage
ingestion would mean thousands of separate API calls every quarter --
a real architectural cost weighed against, not accepted. This table
is a lightweight, one-row-per-CUSIP cache instead: resolved once per
unique security (there are far fewer distinct CUSIPs than holding
rows), not re-queried on every read.

A NULL ticker is a real, meaningful, different state from "never
resolved" (no row at all): it means resolution was genuinely
attempted and no US-listed ticker was found (see
pick_primary_us_ticker's own docstring for why a wrong, foreign
ticker is never guessed as a fallback), so it will not be retried on
every ingestion run.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0027_cusip_ticker_map"
down_revision: Union[str, None] = "0026_drop_ghost_13f_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cusip_ticker_map",
        sa.Column("cusip", sa.String(length=9), primary_key=True, nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=True),
        sa.Column("company_name", sa.String(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("cusip_ticker_map")
