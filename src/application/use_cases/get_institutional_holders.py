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
        matches = self._repository.search_by_issuer_name(issuer_query, period, limit=1)
        if not matches:
            raise GetInstitutionalHoldersError(
                f"No security matching '{issuer_query}' found for the latest quarter ({period})."
            )
        cusip = matches[0].cusip
        issuer_name = matches[0].issuer_name

        holders = self._repository.get_by_cusip(cusip, period)
        holders = sorted(holders, key=lambda h: h.value_usd, reverse=True)[:limit]

        return GetInstitutionalHoldersResult(
            issuer_query=issuer_query, issuer_name=issuer_name,
            period_of_report=period, holders=tuple(holders),
        )
