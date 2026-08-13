"""drop the abandoned, empty form_13f_holdings table

Revision ID: 0026_drop_ghost_13f_table
Revises: 0025_trgm_indexes
Create Date: 2026-08-12

Real, confirmed cleanup, not speculative: a table named
form_13f_holdings was found to exist in the real production database
with NO corresponding migration anywhere in this repo, and NO
reference anywhere in current application code (the real, working 13F
feature built tonight uses institutional_holdings instead). Confirmed
directly before dropping, not assumed: the table has 0 rows, and its
column names (cik, shares_or_principal_amt, name_of_issuer,
value_usd as double precision) are all subtly different from
institutional_holdings' actual, current schema -- clear evidence of
an earlier, different, abandoned design iteration of this same
feature that predates tonight's actual build and was never migrated
through Alembic at all, hence the drift between the tracked schema
history and the real database. Safe to drop: empty, unreferenced,
untracked.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0026_drop_ghost_13f_table"
down_revision: Union[str, None] = "0025_trgm_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS form_13f_holdings")


def downgrade() -> None:
    # Deliberately not recreated: this table was never a real part of
    # the tracked schema history to begin with, and its abandoned
    # design (float value_usd, different column names) should not be
    # reintroduced even on downgrade.
    pass
