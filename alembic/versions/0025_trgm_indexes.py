"""add trigram indexes for fast ILIKE search on institutional_holdings

Revision ID: 0025_trgm_indexes
Revises: 0024_widen_alembic_version
Create Date: 2026-08-12

Real, confirmed performance fix, not speculative: EXPLAIN ANALYZE
against real production data (6.4M rows across two ingested quarters)
showed a single filer_name ILIKE '%...%' search taking 9.4 SECONDS,
doing a parallel sequential scan and filtering out 2.1M+ rows per
worker -- confirmed directly, not assumed. A standard B-tree index
cannot help a leading-wildcard ILIKE query at all; a GIN trigram index
(pg_trgm, a standard, built-in Postgres extension) can, since it
indexes 3-character substrings rather than whole-value prefixes.

Uses CREATE INDEX CONCURRENTLY, which cannot run inside a transaction
block -- Alembic's autocommit_block() context handles this correctly.
This matters here specifically because App Runner's deploy process
runs `alembic upgrade head` as a startup step; a long-running,
lock-holding CREATE INDEX on 6.4M rows risked a deploy health-check
timeout, on top of blocking writes for however long it took.
CONCURRENTLY avoids both: no exclusive lock, and it does not hold up
the migration transaction that gates the rest of startup.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0025_trgm_indexes"
down_revision: Union[str, None] = "0024_widen_alembic_version"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_institutional_holdings_filer_name_trgm "
            "ON institutional_holdings USING gin (filer_name gin_trgm_ops)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_institutional_holdings_issuer_name_trgm "
            "ON institutional_holdings USING gin (issuer_name gin_trgm_ops)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_institutional_holdings_issuer_name_trgm")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_institutional_holdings_filer_name_trgm")
