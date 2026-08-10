from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class InstitutionalHolding:
    """One row from a Form 13F information table — one security held
    by one institutional manager as of one quarter-end.

    Deliberately keyed by CUSIP, not ticker: the raw SEC 13F data
    never includes a ticker symbol at all (confirmed directly from
    SEC's own schema and multiple independent parsing guides) — only
    CUSIP and the issuer's name as the filer typed it. Resolving
    CUSIP -> ticker would need a separate mapping source this build
    deliberately doesn't depend on; issuer_name and cusip alone are
    still genuinely useful for display and lookups."""

    accession_number: str
    filer_cik: str
    filer_name: str
    period_of_report: date
    issuer_name: str
    title_of_class: str
    cusip: str
    value_usd: int
    shares_or_principal_amount: int
    share_type: str  # "SH" (shares) or "PRN" (principal amount)
    put_call: str | None
    investment_discretion: str
    voting_authority_sole: int
    voting_authority_shared: int
    voting_authority_none: int
