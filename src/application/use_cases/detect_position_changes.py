"""Use case: detect real position changes for one filer between the
two most recent quarters actually ingested.

Real, confirmed freshness gap, same as the other two 13F use cases:
SEC's own bulk data set is published once, "closely after" the filing
deadline, not continuously; FMP had a real filer's same-day filing
available within hours. Genuinely the hardest of the three freshness
fallbacks to get right: this needs BOTH a prior and a current quarter
for the same filer, and only the current one can ever come from FMP --
the prior quarter always comes from the local database, since FMP's
per-filer endpoint only ever returns whichever single quarter is
requested, not a full history. When the local pipeline hasn't caught
up to the quarter that should already exist, this fetches that one,
specific, fresher quarter live from FMP for this one filer, aggregates
it the same way the local data already is (see
institutional_holding_aggregation's own docstring), and compares it
against the local database's own most recent quarter as the prior
period -- never against a stale, doubly-outdated pair of local
quarters when a genuinely fresher current quarter exists.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone

from src.application.interfaces.data_provider import FinancialDataProvider
from src.domain.entities.aggregated_position import AggregatedPosition
from src.domain.entities.position_change import PositionChange
from src.domain.repositories.institutional_holding_repository import (
    InstitutionalHoldingRepository,
)
from src.domain.services.form_13f_freshness import latest_expected_complete_period
from src.domain.services.institutional_holding_aggregation import aggregate_holdings_by_cusip
from src.domain.services.position_change_detection import detect_position_changes

DEFAULT_MIN_PCT_CHANGE = 0.0

logger = logging.getLogger(__name__)


class DetectPositionChangesError(Exception):
    """A real, visible failure — fewer than 2 quarters ingested (and no
    fresher quarter available live either), or no filer matched the
    search — never silently swallowed."""


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
    source: str  # "sec_bulk" or "fmp_live" — honest about where the current period came from


def _year_and_quarter(period: date) -> tuple[int, int]:
    """period is always a real calendar quarter-end (Mar/Jun/Sep/Dec
    31), so month // 3 is an exact, safe quarter number -- 3->1,
    6->2, 9->3, 12->4."""
    return period.year, period.month // 3


class DetectPositionChangesUseCase:
    def __init__(
        self,
        repository: InstitutionalHoldingRepository,
        provider: FinancialDataProvider | None = None,
    ) -> None:
        self._repository = repository
        self._provider = provider

    def execute(
        self, filer_query: str, min_pct_change: float = DEFAULT_MIN_PCT_CHANGE, as_of: date | None = None,
    ) -> DetectPositionChangesResult:
        local_periods = self._repository.get_all_periods_of_report()
        if len(local_periods) == 0:
            raise DetectPositionChangesError(
                "No Form 13F data has been ingested yet — nothing to search."
            )
        most_recent_local_period = local_periods[0]

        # Same real bug fix applied in GetInstitutionalPortfolioUseCase:
        # resolving to "whichever single row has the largest value_usd"
        # is not the same as "whichever filer has the largest TOTAL
        # portfolio value" -- confirmed directly (searching "Circle"
        # wrongly resolved to an unrelated mutual fund with fewer,
        # larger individual rows instead of the real company).
        # resolve_filer_by_name sums by filer_cik first, so this can't
        # happen here either.
        resolved = self._repository.resolve_filer_by_name(filer_query, most_recent_local_period)
        if resolved is None:
            raise DetectPositionChangesError(
                f"No filer matching '{filer_query}' found for the latest quarter ({most_recent_local_period})."
            )
        filer_cik, filer_name = resolved

        if as_of is None:
            as_of = datetime.now(timezone.utc).date()
        fresher_result = self._try_fresher_fmp_data(
            filer_cik, filer_name, filer_query, most_recent_local_period, min_pct_change, as_of,
        )
        if fresher_result is not None:
            return fresher_result

        if len(local_periods) < 2:
            raise DetectPositionChangesError(
                f"Need at least 2 ingested quarters to detect changes; only {len(local_periods)} available."
            )
        current_period, prior_period = local_periods[0], local_periods[1]

        prior_portfolio = self._repository.get_aggregated_portfolio(filer_cik, prior_period)
        current_portfolio = self._repository.get_aggregated_portfolio(filer_cik, current_period)

        changes = detect_position_changes(prior_portfolio, current_portfolio, min_pct_change=min_pct_change)

        return DetectPositionChangesResult(
            filer_query=filer_query, filer_name=filer_name, filer_cik=filer_cik,
            prior_period=prior_period, current_period=current_period,
            changes=tuple(changes),
            filer_had_no_prior_period_data=(len(prior_portfolio) == 0),
            source="sec_bulk",
        )

    def _try_fresher_fmp_data(
        self, filer_cik: str, filer_name: str, filer_query: str,
        local_period: date, min_pct_change: float, as_of: date,
    ) -> DetectPositionChangesResult | None:
        """Returns a fresher result comparing local_period (the prior
        period) against a live, FMP-sourced current period if the
        local data is genuinely stale AND FMP actually has something
        newer for this specific filer yet -- returns None (meaning:
        use the purely-local two-quarter comparison) in every other
        case, including when FMP itself errors, since a live-data
        hiccup should never take down a feature the free, local
        pipeline already serves correctly on its own."""
        if self._provider is None:
            return None

        expected_period = latest_expected_complete_period(as_of)
        if expected_period is None or expected_period <= local_period:
            return None  # local data is already at least as fresh as expected

        year, quarter = _year_and_quarter(expected_period)
        try:
            fresher_holdings = self._provider.get_institutional_holdings_by_filer(
                cik=filer_cik, year=year, quarter=quarter, filer_name=filer_name,
            )
        except NotImplementedError:
            return None  # this provider doesn't support live fallback at all
        except Exception:
            logger.warning(
                "FMP live fallback failed for filer_cik=%s, quarter=%s-Q%s — "
                "falling back to a purely local comparison instead of failing the whole request",
                filer_cik, year, quarter, exc_info=True,
            )
            return None

        if not fresher_holdings:
            return None  # this filer genuinely hasn't filed for the fresher quarter yet either

        current_portfolio: list[AggregatedPosition] = aggregate_holdings_by_cusip(fresher_holdings)
        prior_portfolio = self._repository.get_aggregated_portfolio(filer_cik, local_period)

        changes = detect_position_changes(prior_portfolio, current_portfolio, min_pct_change=min_pct_change)

        return DetectPositionChangesResult(
            filer_query=filer_query, filer_name=filer_name, filer_cik=filer_cik,
            prior_period=local_period, current_period=expected_period,
            changes=tuple(changes),
            filer_had_no_prior_period_data=(len(prior_portfolio) == 0),
            source="fmp_live",
        )

