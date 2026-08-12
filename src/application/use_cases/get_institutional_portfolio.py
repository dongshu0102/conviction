"""Use case: "what does this filer hold" -- one institutional
manager's full reported portfolio for the latest quarter actually
ingested, largest positions first.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.domain.entities.institutional_holding import InstitutionalHolding
from src.domain.repositories.institutional_holding_repository import (
    InstitutionalHoldingRepository,
)

DEFAULT_LIMIT = 50


class GetInstitutionalPortfolioError(Exception):
    """A real, visible failure — e.g. nothing has ever been ingested
    yet — never silently swallowed."""


@dataclass(frozen=True, slots=True)
class GetInstitutionalPortfolioResult:
    filer_query: str
    period_of_report: date
    holdings: tuple[InstitutionalHolding, ...]


class GetInstitutionalPortfolioUseCase:
    def __init__(self, repository: InstitutionalHoldingRepository) -> None:
        self._repository = repository

    def execute(self, filer_query: str, limit: int = DEFAULT_LIMIT) -> GetInstitutionalPortfolioResult:
        period = self._repository.get_latest_period_of_report()
        if period is None:
            raise GetInstitutionalPortfolioError(
                "No Form 13F data has been ingested yet — nothing to search."
            )

        holdings = self._repository.search_by_filer_name(filer_query, period, limit=limit)
        return GetInstitutionalPortfolioResult(
            filer_query=filer_query, period_of_report=period, holdings=tuple(holdings),
        )
