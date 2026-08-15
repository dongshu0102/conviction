"""Use case: "who has disclosed a 5%+ stake in this security, and did
they say they might want influence or not" -- every Schedule 13D/13G
reporting person's disclosure for one security, most recent first.

Genuinely simpler than the three 13F use cases: this data has no free,
official SEC bulk data set at all (confirmed directly -- SEC only
mandated structured XML filing for these schedules starting December
2024, with no equivalent to the 13F bulk archive), so there is no
local database, no ingestion pipeline, and therefore no "freshness
fallback" concept here -- every call is genuinely, always live against
the real, current FMP data. Accepts a ticker directly, matching this
codebase's established convention for other ticker-based features
(company financials, valuation, etc.), rather than the free-text
name search the 13F use cases need -- FMP's own endpoint is
ticker-based already, and there is no raw-data-has-no-ticker problem
to work around here the way there genuinely is for 13F.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.application.interfaces.data_provider import FinancialDataProvider
from src.domain.entities.beneficial_ownership_disclosure import BeneficialOwnershipDisclosure


class GetBeneficialOwnershipDisclosuresError(Exception):
    """A real, visible failure — e.g. this provider doesn't support
    the capability at all — never silently swallowed."""


@dataclass(frozen=True, slots=True)
class GetBeneficialOwnershipDisclosuresResult:
    ticker: str
    disclosures: tuple[BeneficialOwnershipDisclosure, ...]


class GetBeneficialOwnershipDisclosuresUseCase:
    def __init__(self, provider: FinancialDataProvider) -> None:
        self._provider = provider

    def execute(self, ticker: str) -> GetBeneficialOwnershipDisclosuresResult:
        try:
            disclosures = self._provider.get_beneficial_ownership_disclosures(ticker.upper())
        except NotImplementedError as exc:
            raise GetBeneficialOwnershipDisclosuresError(
                "This data provider does not support 13D/13G beneficial ownership disclosures."
            ) from exc

        disclosures = sorted(disclosures, key=lambda d: d.filing_date, reverse=True)

        return GetBeneficialOwnershipDisclosuresResult(
            ticker=ticker.upper(), disclosures=tuple(disclosures),
        )
