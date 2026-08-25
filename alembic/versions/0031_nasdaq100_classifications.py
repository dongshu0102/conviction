"""add nasdaq100_classifications table

Revision ID: 0031_nasdaq100_classifications
Revises: 0030_synced_orders
Create Date: 2026-08-25

Backs a 6-dimension Nasdaq-100 screener (GICS industry, market
concentration/HHI, value chain position, business model, factor
segmentation, market cap tier/maturity stage). Two of these six
dimensions -- value chain position and business model -- have no
existing structured data to derive from at all; they require a real
LLM classification, not just an LLM explanation of an already-computed
value (a genuinely different discipline than Master Lens or Market
Structure, where the LLM only narrates a fixed, deterministic result).

Computing that LLM classification on-demand per screener request
across ~100 companies would mean up to 100 real LLM calls on every
page load -- genuinely too slow and expensive, the same reasoning
that led to caching the Conviction Screener's own results (see
0028_conviction_screener_results.py). Same "latest-only cache"
pattern here: one row per ticker, overwritten on each refresh, with a
shared as_of timestamp.

industry, market_cap, and revenue_growth are stored here too even
though they're derived from data that lives elsewhere -- deliberately
denormalized so the screener can filter/sort on all six dimensions
from this one table without needing five separate joins or live calls
per request.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0031_nasdaq100_classifications"
down_revision: Union[str, None] = "0030_synced_orders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "nasdaq100_classifications",
        sa.Column("ticker", sa.String(), sa.ForeignKey("companies.ticker"), primary_key=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("industry", sa.String(), nullable=False),
        sa.Column("market_structure_category", sa.String(), nullable=True),
        sa.Column("hhi", sa.Float(), nullable=True),
        sa.Column("value_chain_position", sa.String(), nullable=True),
        sa.Column("business_model", sa.String(), nullable=True),
        sa.Column("market_cap_tier", sa.String(), nullable=True),
        sa.Column("maturity_stage", sa.String(), nullable=True),
        sa.Column("market_cap", sa.Float(), nullable=True),
        sa.Column("revenue_growth", sa.Float(), nullable=True),
    )
    op.create_index(
        "ix_nasdaq100_classifications_industry", "nasdaq100_classifications", ["industry"],
    )
    op.create_index(
        "ix_nasdaq100_classifications_market_structure_category",
        "nasdaq100_classifications", ["market_structure_category"],
    )
    op.create_index(
        "ix_nasdaq100_classifications_value_chain_position",
        "nasdaq100_classifications", ["value_chain_position"],
    )
    op.create_index(
        "ix_nasdaq100_classifications_business_model", "nasdaq100_classifications", ["business_model"],
    )
    op.create_index(
        "ix_nasdaq100_classifications_market_cap_tier", "nasdaq100_classifications", ["market_cap_tier"],
    )
    op.create_index(
        "ix_nasdaq100_classifications_maturity_stage", "nasdaq100_classifications", ["maturity_stage"],
    )


def downgrade() -> None:
    op.drop_index("ix_nasdaq100_classifications_maturity_stage", table_name="nasdaq100_classifications")
    op.drop_index("ix_nasdaq100_classifications_market_cap_tier", table_name="nasdaq100_classifications")
    op.drop_index("ix_nasdaq100_classifications_business_model", table_name="nasdaq100_classifications")
    op.drop_index("ix_nasdaq100_classifications_value_chain_position", table_name="nasdaq100_classifications")
    op.drop_index(
        "ix_nasdaq100_classifications_market_structure_category", table_name="nasdaq100_classifications"
    )
    op.drop_index("ix_nasdaq100_classifications_industry", table_name="nasdaq100_classifications")
    op.drop_table("nasdaq100_classifications")
