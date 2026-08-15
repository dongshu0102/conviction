"""Use case: "what does this filer hold" -- one institutional
manager's full reported portfolio for the latest quarter actually
ingested, largest positions first.

Real, confirmed freshness gap between the two data sources: SEC's own
bulk 13F data set is published once, "closely after" the filing
deadline (SEC's own words, from its own dataset documentation) -- not
continuously. FMP, on the Ultimate tier, had a real filer's same-day
13F filing available within hours of it being filed (confirmed
directly: Berkshire's Q2 2026 filing showed filingDate == acceptedDate
== today's real date, live in FMP's response the same day). When the
local, free pipeline hasn't caught up to the quarter that should
already exist per the SEC's own published deadline calendar, this
falls back to a live FMP call for that one filer rather than showing
stale data unnecessarily -- but once the local pipeline is re-run and
genuinely has that quarter, the free, already-ingested, full-coverage
local data is used again automatically, with no FMP call needed at
all. FMP is a live gap-filler for freshness, never the primary,
full-coverage source (see cusip_ticker_resolution's own docstring for
why: FMP's 13F endpoints are scoped per-filer/per-security, with no
true bulk/quarterly download).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone

from src.application.interfaces.data_provider import FinancialDataProvider
from src.domain.entities.institutional_holding import InstitutionalHolding
from src.domain.repositories.institutional_holding_repository import (
    InstitutionalHoldingRepository,
)
from src.domain.services.form_13f_freshness import latest_expected_complete_period

DEFAULT_LIMIT = 50

logger = logging.getLogger(__name__)


class GetInstitutionalPortfolioError(Exception):
    """A real, visible failure — e.g. nothing has ever been ingested
    yet — never silently swallowed."""


@dataclass(frozen=True, slots=True)
class GetInstitutionalPortfolioResult:
    filer_query: str
    filer_name: str
    period_of_report: date
    holdings: tuple[InstitutionalHolding, ...]
    source: str  # "sec_bulk" or "fmp_live" — honest about where this came from


def _year_and_quarter(period: date) -> tuple[int, int]:
    """period is always a real calendar quarter-end (Mar/Jun/Sep/Dec
    31), so month // 3 is an exact, safe quarter number -- 3->1,
    6->2, 9->3, 12->4."""
    return period.year, period.month // 3


class GetInstitutionalPortfolioUseCase:
    def __init__(
        self,
        repository: InstitutionalHoldingRepository,
        provider: FinancialDataProvider | None = None,
    ) -> None:
        self._repository = repository
        self._provider = provider

    def execute(
        self, filer_query: str, limit: int = DEFAULT_LIMIT, as_of: date | None = None,
    ) -> GetInstitutionalPortfolioResult:
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

        if as_of is None:
            as_of = datetime.now(timezone.utc).date()
        fresher_result = self._try_fresher_fmp_data(filer_cik, filer_name, filer_query, period, limit, as_of)
        if fresher_result is not None:
            return fresher_result

        holdings = self._repository.get_by_filer(filer_cik, period)
        holdings = sorted(holdings, key=lambda h: h.value_usd, reverse=True)[:limit]

        return GetInstitutionalPortfolioResult(
            filer_query=filer_query, filer_name=filer_name,
            period_of_report=period, holdings=tuple(holdings), source="sec_bulk",
        )

    def _try_fresher_fmp_data(
        self, filer_cik: str, filer_name: str, filer_query: str,
        local_period: date, limit: int, as_of: date,
    ) -> GetInstitutionalPortfolioResult | None:
        """Returns a fresher result from FMP if the local data is
        genuinely stale AND FMP actually has something newer for this
        specific filer yet -- returns None (meaning: use the local
        data) in every other case, including when FMP itself is
        unavailable or errors, since a live-data hiccup should never
        take down a feature the free, local pipeline already serves
        correctly."""
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
                "falling back to local data instead of failing the whole request",
                filer_cik, year, quarter, exc_info=True,
            )
            return None

        if not fresher_holdings:
            return None  # this filer genuinely hasn't filed for the fresher quarter yet either

        fresher_holdings = sorted(fresher_holdings, key=lambda h: h.value_usd, reverse=True)[:limit]
        return GetInstitutionalPortfolioResult(
            filer_query=filer_query, filer_name=filer_name,
            period_of_report=expected_period, holdings=tuple(fresher_holdings), source="fmp_live",
        )

