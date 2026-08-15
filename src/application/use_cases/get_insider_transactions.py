"""Use case: every reported Form 3/4/5 transaction for one company's
insiders -- officers, directors, and 10%+ owners buying, selling, or
otherwise changing their reported holdings in their own company's
stock, most recent first.

Genuinely simpler than the three 13F use cases, matching
get_beneficial_ownership_disclosures's own shape: no free, official
SEC bulk data set exists for structured Form 3/4/5 transaction data
the way one does for 13F, so there is no local database, no ingestion
pipeline, and no "freshness fallback" concept here -- every call is
genuinely, always live against the real, current FMP data. Accepts a
ticker directly, matching this codebase's established convention for
other ticker-based features.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.application.interfaces.data_provider import FinancialDataProvider
from src.domain.entities.insider_transaction import InsiderTransaction


class GetInsiderTransactionsError(Exception):
    """A real, visible failure — e.g. this provider doesn't support
    the capability at all — never silently swallowed."""


@dataclass(frozen=True, slots=True)
class GetInsiderTransactionsResult:
    ticker: str
    transactions: tuple[InsiderTransaction, ...]


class GetInsiderTransactionsUseCase:
    def __init__(self, provider: FinancialDataProvider) -> None:
        self._provider = provider

    def execute(self, ticker: str) -> GetInsiderTransactionsResult:
        try:
            transactions = self._provider.get_insider_transactions(ticker.upper())
        except NotImplementedError as exc:
            raise GetInsiderTransactionsError(
                "This data provider does not support Form 3/4/5 insider transactions."
            ) from exc

        transactions = sorted(transactions, key=lambda t: t.filing_date, reverse=True)

        return GetInsiderTransactionsResult(
            ticker=ticker.upper(), transactions=tuple(transactions),
        )
