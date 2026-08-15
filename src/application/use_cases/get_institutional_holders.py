"""Use case: "who holds this security" -- every filer's reported
position in one issuer for the latest quarter actually ingested,
biggest holders first.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.domain.entities.institutional_holding import InstitutionalHolding
from src.domain.repositories.institutional_holding_repository import (
    InstitutionalHoldingRepository,
)

DEFAULT_LIMIT = 20


class GetInstitutionalHoldersError(Exception):
    """A real, visible failure — e.g. nothing has ever been ingested
    yet — never silently swallowed."""


@dataclass(frozen=True, slots=True)
class GetInstitutionalHoldersResult:
    issuer_query: str
    issuer_name: str
    period_of_report: date
    holders: tuple[InstitutionalHolding, ...]


class GetInstitutionalHoldersUseCase:
    def __init__(self, repository: InstitutionalHoldingRepository) -> None:
        self._repository = repository

    def execute(self, issuer_query: str, limit: int = DEFAULT_LIMIT) -> GetInstitutionalHoldersResult:
        period = self._repository.get_latest_period_of_report()
        if period is None:
            raise GetInstitutionalHoldersError(
                "No Form 13F data has been ingested yet — nothing to search."
            )

        # Real, confirmed bug fix, the sibling of the one already found
        # and fixed in GetInstitutionalPortfolioUseCase: resolving
        # directly against a broad issuer-name search (e.g. "American")
        # returned rows blended together from several genuinely
        # different, unrelated SECURITIES that happen to share a name
        # prefix (confirmed directly against real production data:
        # "AMERICAN ELEC PWR CO INC", "AMERICAN EXPRESS CO", and
        # "AMERICAN TOWER CORP" all appeared in a single "who holds X"
        # response, with no indication which holder owned which
        # security). Resolving to ONE security's CUSIP first, then
        # fetching only that CUSIP's own rows, makes that impossible.
        #
        # A second, separate real bug was found and fixed here too:
        # resolving to "whichever single row has the largest
        # value_usd" is NOT the same as resolving to "whichever
        # security has the largest TOTAL value" -- confirmed directly
        # against real production data, searching "Circle" resolved to
        # "ADVISORS INNER CIRCLE FD III" (an unrelated mutual fund, 9
        # holders, $1.43B total) instead of the real Circle Internet
        # Group (535 holders, $14.36B total), because one single row
        # within that smaller, less-diversified fund happened to be
        # larger than any single row within Circle's own, more
        # evenly-distributed holder base. resolve_issuer_by_name sums
        # by cusip first, so this can't happen.
        resolved = self._repository.resolve_issuer_by_name(issuer_query, period)
        if resolved is None:
            raise GetInstitutionalHoldersError(
                f"No security matching '{issuer_query}' found for the latest quarter ({period})."
            )
        cusip, issuer_name = resolved

        holders = self._repository.get_by_cusip(cusip, period)
        holders = sorted(holders, key=lambda h: h.value_usd, reverse=True)[:limit]

        return GetInstitutionalHoldersResult(
            issuer_query=issuer_query, issuer_name=issuer_name,
            period_of_report=period, holders=tuple(holders),
        )
