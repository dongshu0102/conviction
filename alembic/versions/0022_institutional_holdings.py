"""institutional_holdings table

Revision ID: 0022_institutional_holdings
Revises: 0020_capital_flow_monitor_cache
Create Date: 2026-08-10

Bulk-ingested SEC Form 13F institutional holdings data, sourced
directly from SEC's own free, official quarterly data sets (not a
live per-request API — see scripts/ingest_form_13f.py for the actual
download-and-parse pipeline). No foreign key to companies: the raw
SEC data has no ticker symbol at all, only CUSIP.

Deliberately revision 0022, skipping 0021 — an untrusted,
unverifiable file already occupied that slot in this sandbox from an
unrelated, unexplained source with no confirmed provenance.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0022_institutional_holdings"
down_revision: Union[str, None] = "0020_capital_flow_monitor_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "institutional_holdings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("accession_number", sa.String(length=32), nullable=False),
        sa.Column("filer_cik", sa.String(length=16), nullable=False),
        sa.Column("filer_name", sa.String(length=255), nullable=False),
        sa.Column("period_of_report", sa.Date(), nullable=False),
        sa.Column("issuer_name", sa.String(length=255), nullable=False),
        sa.Column("title_of_class", sa.String(length=150), nullable=False),
        sa.Column("cusip", sa.String(length=9), nullable=False),
        sa.Column("value_usd", sa.Integer(), nullable=False),
        sa.Column("shares_or_principal_amount", sa.Integer(), nullable=False),
        sa.Column("share_type", sa.String(length=10), nullable=False),
        sa.Column("put_call", sa.String(length=10), nullable=True),
        sa.Column("investment_discretion", sa.String(length=20), nullable=False),
        sa.Column("voting_authority_sole", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("voting_authority_shared", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("voting_authority_none", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ingested_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_institutional_holdings_accession_number", "institutional_holdings", ["accession_number"])
    op.create_index("ix_institutional_holdings_filer_cik", "institutional_holdings", ["filer_cik"])
    op.create_index("ix_institutional_holdings_period_of_report", "institutional_holdings", ["period_of_report"])
    op.create_index("ix_institutional_holdings_cusip", "institutional_holdings", ["cusip"])


def downgrade() -> None:
    op.drop_index("ix_institutional_holdings_cusip", table_name="institutional_holdings")
    op.drop_index("ix_institutional_holdings_period_of_report", table_name="institutional_holdings")
    op.drop_index("ix_institutional_holdings_filer_cik", table_name="institutional_holdings")
    op.drop_index("ix_institutional_holdings_accession_number", table_name="institutional_holdings")
    op.drop_table("institutional_holdings")
