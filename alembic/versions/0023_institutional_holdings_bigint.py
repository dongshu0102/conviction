"""widen institutional_holdings numeric columns to BigInteger

Revision ID: 0023_institutional_holdings_bigint
Revises: 0022_institutional_holdings
Create Date: 2026-08-10

Real, confirmed bug fix: a real ingestion run against actual SEC
production data hit psycopg2.errors.NumericValueOutOfRange on
value_usd -- a single mega-fund's position in a mega-cap stock
genuinely exceeds standard 32-bit INTEGER's ~2.147 billion range.
Widens value_usd, shares_or_principal_amount, and the three
voting_authority_* columns to BigInteger, the same real overflow risk
applying to all of them even though only value_usd was hit in
practice so far.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0023_institutional_holdings_bigint"
down_revision: Union[str, None] = "0022_institutional_holdings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = (
    "value_usd",
    "shares_or_principal_amount",
    "voting_authority_sole",
    "voting_authority_shared",
    "voting_authority_none",
)


def upgrade() -> None:
    for column in _COLUMNS:
        op.alter_column("institutional_holdings", column, type_=sa.BigInteger())


def downgrade() -> None:
    for column in _COLUMNS:
        op.alter_column("institutional_holdings", column, type_=sa.Integer())
