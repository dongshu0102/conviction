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
    filer_name: str
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

        # Real, confirmed bug fix: resolving directly against a broad
        # name search (e.g. "Vanguard") returned rows blended together
        # from several genuinely different, unrelated filer entities
        # that happen to share a name prefix (confirmed directly
        # against real production data: "Vanguard Capital Management
        # LLC", "Vanguard Portfolio Management LLC", and "Vanguard
        # Advisers Inc" all appeared in a single response, presented
        # as if they were one filer's portfolio). Resolving to ONE
        # filer's CIK first, then fetching only that CIK's own rows,
        # makes that impossible -- matches the same pattern already
        # used correctly in DetectPositionChangesUseCase.
        matches = self._repository.search_by_filer_name(filer_query, period, limit=1)
        if not matches:
            raise GetInstitutionalPortfolioError(
                f"No filer matching '{filer_query}' found for the latest quarter ({period})."
            )
        filer_cik = matches[0].filer_cik
        filer_name = matches[0].filer_name

        holdings = self._repository.get_by_filer(filer_cik, period)
        holdings = sorted(holdings, key=lambda h: h.value_usd, reverse=True)[:limit]

        return GetInstitutionalPortfolioResult(
            filer_query=filer_query, filer_name=filer_name,
            period_of_report=period, holdings=tuple(holdings),
        )

