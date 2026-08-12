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

        holders = self._repository.search_by_issuer_name(issuer_query, period, limit=limit)
        return GetInstitutionalHoldersResult(
            issuer_query=issuer_query, period_of_report=period, holders=tuple(holders),
        )
