"""Use case: "who holds this security" -- every filer's reported
position in one issuer for the latest quarter actually ingested,
biggest holders first.

Real, confirmed freshness gap, same as GetInstitutionalPortfolioUseCase:
SEC's own bulk 13F data set is published once, "closely after" the
filing deadline, not continuously; FMP had a real filer's same-day
filing available within hours. This falls back to a live FMP call for
one specific security when the local pipeline hasn't caught up to the
quarter that should already exist -- but unlike the filer-side
fallback, FMP's per-security endpoint needs a TICKER SYMBOL, not a
CUSIP, so this first resolves cusip -> ticker via
ResolveCusipTickerUseCase (which itself caches the result, so a given
CUSIP is only ever sent to FMP's search-cusip endpoint once). If no
US-listed ticker can be resolved for this CUSIP at all, this falls
back to local data -- the same honest, never-crash-the-whole-request
principle as the filer-side fallback.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone

from src.application.interfaces.data_provider import FinancialDataProvider
from src.application.use_cases.resolve_cusip_ticker import ResolveCusipTickerUseCase
from src.domain.entities.institutional_holding import InstitutionalHolding
from src.domain.repositories.institutional_holding_repository import (
    InstitutionalHoldingRepository,
)
from src.domain.services.form_13f_freshness import latest_expected_complete_period

DEFAULT_LIMIT = 20

logger = logging.getLogger(__name__)


class GetInstitutionalHoldersError(Exception):
    """A real, visible failure — e.g. nothing has ever been ingested
    yet — never silently swallowed."""


@dataclass(frozen=True, slots=True)
class GetInstitutionalHoldersResult:
    issuer_query: str
    issuer_name: str
    period_of_report: date
    holders: tuple[InstitutionalHolding, ...]
    source: str  # "sec_bulk" or "fmp_live" — honest about where this came from


def _year_and_quarter(period: date) -> tuple[int, int]:
    """period is always a real calendar quarter-end (Mar/Jun/Sep/Dec
    31), so month // 3 is an exact, safe quarter number -- 3->1,
    6->2, 9->3, 12->4."""
    return period.year, period.month // 3


class GetInstitutionalHoldersUseCase:
    def __init__(
        self,
        repository: InstitutionalHoldingRepository,
        provider: FinancialDataProvider | None = None,
        ticker_resolver: ResolveCusipTickerUseCase | None = None,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._ticker_resolver = ticker_resolver

    def execute(
        self, issuer_query: str, limit: int = DEFAULT_LIMIT, as_of: date | None = None,
    ) -> GetInstitutionalHoldersResult:
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

        if as_of is None:
            as_of = datetime.now(timezone.utc).date()
        fresher_result = self._try_fresher_fmp_data(cusip, issuer_name, issuer_query, period, limit, as_of)
        if fresher_result is not None:
            return fresher_result

        holders = self._repository.get_by_cusip(cusip, period)
        holders = sorted(holders, key=lambda h: h.value_usd, reverse=True)[:limit]

        return GetInstitutionalHoldersResult(
            issuer_query=issuer_query, issuer_name=issuer_name,
            period_of_report=period, holders=tuple(holders), source="sec_bulk",
        )

    def _try_fresher_fmp_data(
        self, cusip: str, issuer_name: str, issuer_query: str,
        local_period: date, limit: int, as_of: date,
    ) -> GetInstitutionalHoldersResult | None:
        """Returns a fresher result from FMP if the local data is
        genuinely stale, a real US ticker can be resolved for this
        CUSIP, AND FMP actually has something newer yet -- returns
        None (meaning: use the local data) in every other case,
        including when FMP or ticker resolution itself errors, since a
        live-data hiccup should never take down a feature the free,
        local pipeline already serves correctly."""
        if self._provider is None or self._ticker_resolver is None:
            return None

        expected_period = latest_expected_complete_period(as_of)
        if expected_period is None or expected_period <= local_period:
            return None  # local data is already at least as fresh as expected

        year, quarter = _year_and_quarter(expected_period)
        try:
            ticker_mapping = self._ticker_resolver.execute(cusip)
        except Exception:
            logger.warning(
                "CUSIP-to-ticker resolution failed for cusip=%s — "
                "falling back to local data instead of failing the whole request",
                cusip, exc_info=True,
            )
            return None

        if ticker_mapping.ticker is None:
            return None  # no US-listed ticker exists for this CUSIP at all

        try:
            fresher_holders = self._provider.get_institutional_holders_by_symbol(
                symbol=ticker_mapping.ticker, year=year, quarter=quarter, limit=limit,
            )
        except NotImplementedError:
            return None  # this provider doesn't support live fallback at all
        except Exception:
            logger.warning(
                "FMP live fallback failed for symbol=%s, quarter=%s-Q%s — "
                "falling back to local data instead of failing the whole request",
                ticker_mapping.ticker, year, quarter, exc_info=True,
            )
            return None

        if not fresher_holders:
            return None  # this security genuinely has no holders reported yet either

        fresher_holders = sorted(fresher_holders, key=lambda h: h.value_usd, reverse=True)[:limit]
        return GetInstitutionalHoldersResult(
            issuer_query=issuer_query, issuer_name=fresher_holders[0].issuer_name,
            period_of_report=expected_period, holders=tuple(fresher_holders), source="fmp_live",
        )

