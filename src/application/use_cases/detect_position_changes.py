"""Use case: detect real position changes for one filer between the
two most recent quarters actually ingested.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.domain.entities.position_change import PositionChange
from src.domain.repositories.institutional_holding_repository import (
    InstitutionalHoldingRepository,
)
from src.domain.services.position_change_detection import detect_position_changes

DEFAULT_MIN_PCT_CHANGE = 0.0


class DetectPositionChangesError(Exception):
    """A real, visible failure — fewer than 2 quarters ingested, or no
    filer matched the search — never silently swallowed."""


@dataclass(frozen=True, slots=True)
class DetectPositionChangesResult:
    filer_query: str
    filer_name: str
    filer_cik: str
    prior_period: date
    current_period: date
    changes: tuple[PositionChange, ...]
    filer_had_no_prior_period_data: bool
    """True when this filer has ZERO rows anywhere in the prior
    quarter — a real, confirmed scenario (e.g. a newly-registered
    manager whose first-ever 13F was this quarter), not a data bug.
    Distinguishes this from the normal case of individual positions
    being genuinely new. Every position renders as "new" in both
    cases, but the honest story behind that is completely different:
    "this manager started reporting this quarter" is not the same
    claim as "this manager just bought their whole book" — callers
    should surface this flag rather than presenting an undifferentiated
    wall of "new" positions either way."""


class DetectPositionChangesUseCase:
    def __init__(self, repository: InstitutionalHoldingRepository) -> None:
        self._repository = repository

    def execute(
        self, filer_query: str, min_pct_change: float = DEFAULT_MIN_PCT_CHANGE,
    ) -> DetectPositionChangesResult:
        periods = self._repository.get_all_periods_of_report()
        if len(periods) < 2:
            raise DetectPositionChangesError(
                f"Need at least 2 ingested quarters to detect changes; only {len(periods)} available."
            )
        current_period, prior_period = periods[0], periods[1]

        matches = self._repository.search_by_filer_name(filer_query, current_period, limit=1)
        if not matches:
            raise DetectPositionChangesError(
                f"No filer matching '{filer_query}' found for the latest quarter ({current_period})."
            )
        filer_cik = matches[0].filer_cik
        filer_name = matches[0].filer_name

        prior_portfolio = self._repository.get_aggregated_portfolio(filer_cik, prior_period)
        current_portfolio = self._repository.get_aggregated_portfolio(filer_cik, current_period)

        changes = detect_position_changes(prior_portfolio, current_portfolio, min_pct_change=min_pct_change)

        return DetectPositionChangesResult(
            filer_query=filer_query, filer_name=filer_name, filer_cik=filer_cik,
            prior_period=prior_period, current_period=current_period,
            changes=tuple(changes),
            filer_had_no_prior_period_data=(len(prior_portfolio) == 0),
        )
