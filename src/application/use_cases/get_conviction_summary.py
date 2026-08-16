"""Use case: combine three genuinely different, independent SEC
disclosure regimes into one, honest "conviction summary" for a single
ticker -- institutional accumulation (13F), activist intent (13D), and
insider buying (Form 4).

Deliberately scoped to one ticker at a time, not a full-market scan:
checking even a handful of top institutional holders' own
quarter-over-quarter changes means several chained calls per ticker
(get_institutional_holders, then detect_position_changes once per
checked holder), which is genuinely too expensive to run unbounded
across hundreds of tickers in a single request. See
screen_for_conviction.py for the market-wide version built on top of
this same, single-ticker logic.

Each of the three signal categories is fetched and evaluated
independently, with its own, isolated error handling -- a real
failure in one (e.g. no 13F data exists yet for a newly-listed ticker)
degrades that one signal to "not found" rather than failing the whole
summary. This matches the same "never let one failure break the whole
request" principle already established for every other multi-source
feature tonight.
"""
from __future__ import annotations

import logging

from src.application.use_cases.detect_position_changes import (
    DetectPositionChangesError,
    DetectPositionChangesUseCase,
)
from src.application.use_cases.get_beneficial_ownership_disclosures import (
    GetBeneficialOwnershipDisclosuresError,
    GetBeneficialOwnershipDisclosuresUseCase,
)
from src.application.use_cases.get_institutional_holders import (
    GetInstitutionalHoldersError,
    GetInstitutionalHoldersUseCase,
)
from src.application.use_cases.get_insider_transactions import (
    GetInsiderTransactionsError,
    GetInsiderTransactionsUseCase,
)
from src.domain.entities.conviction_summary import ConvictionSummary, InstitutionalHolderSignal
from src.domain.repositories.company_repository import CompanyRepository

logger = logging.getLogger(__name__)

# Bounds the number of detect_position_changes calls per summary --
# checking every holder would be genuinely, unreasonably expensive for
# a single request. Deliberately small: the largest holders are most
# often passive index funds (BlackRock, Vanguard) whose "increase" is
# usually just index rebalancing, not a real conviction signal, so
# there's limited value in checking more of them anyway.
TOP_HOLDERS_TO_CHECK = 5


class GetConvictionSummaryUseCase:
    def __init__(
        self,
        get_institutional_holders: GetInstitutionalHoldersUseCase,
        detect_position_changes: DetectPositionChangesUseCase,
        get_beneficial_ownership_disclosures: GetBeneficialOwnershipDisclosuresUseCase,
        get_insider_transactions: GetInsiderTransactionsUseCase,
        company_repository: CompanyRepository,
    ) -> None:
        self._get_institutional_holders = get_institutional_holders
        self._detect_position_changes = detect_position_changes
        self._get_beneficial_ownership_disclosures = get_beneficial_ownership_disclosures
        self._get_insider_transactions = get_insider_transactions
        self._company_repository = company_repository

    def execute(self, ticker: str) -> ConvictionSummary:
        holder_signals, institutional_signal, ground_truth_cusip = self._get_institutional_signal(ticker)
        disclosures_13d, activist_signal = self._get_activist_signal(ticker, ground_truth_cusip)
        purchases, insider_signal = self._get_insider_signal(ticker)

        return ConvictionSummary(
            ticker=ticker.upper(),
            institutional_holders=tuple(holder_signals),
            institutional_signal=institutional_signal,
            activist_disclosures_13d=tuple(disclosures_13d),
            activist_signal=activist_signal,
            insider_purchases=tuple(purchases),
            insider_signal=insider_signal,
            signal_count=sum([institutional_signal, activist_signal, insider_signal]),
        )

    def _get_institutional_signal(self, ticker: str) -> tuple[list[InstitutionalHolderSignal], bool, str | None]:
        # Real, confirmed bug caught during self-review before shipping:
        # get_institutional_holders searches by company NAME
        # (issuer_query against the raw 13F issuer_name field), not by
        # ticker -- raw 13F data has no ticker field at all. Passing a
        # bare ticker like "AAPL" directly would silently fail to
        # match "APPLE INC" in the database, degrading every summary's
        # institutional signal to false regardless of the real, true
        # answer. Resolves through this app's own companies table
        # first; if the company genuinely isn't ingested there yet,
        # degrades honestly to "not found" rather than falling back to
        # a raw ticker string that's very unlikely to match anything.
        company = self._company_repository.get_by_ticker(ticker.upper())
        if company is None:
            return [], False, None

        try:
            holders_result = self._get_institutional_holders.execute(company.name, limit=TOP_HOLDERS_TO_CHECK)
        except GetInstitutionalHoldersError:
            return [], False, None

        # Real, confirmed bug caught live tonight, not a hypothetical:
        # FMP's beneficial-ownership endpoint returns filings where the
        # requested ticker is EITHER the issuer OR the filer -- for
        # large institutions that are themselves active 13D/13G filers
        # (JPMorgan Chase, and likely other big banks/asset managers),
        # this silently mixes in filings about entirely different
        # companies. Confirmed directly: 15 separate "activist"
        # disclosures for JPM all carried CUSIPs starting with "092...",
        # none matching JPM's own, real CUSIP ("46625H100") -- every
        # one was JPMorgan itself, as filer, disclosing a stake in some
        # other company. The ground-truth CUSIP here comes from this
        # ticker's own real 13F holdings (every holding of the same
        # issuer shares one CUSIP), reusing data already fetched for
        # the institutional signal above -- no extra API or DB calls.
        ground_truth_cusip = holders_result.holders[0].cusip if holders_result.holders else None

        signals = []
        any_increasing = False
        for h in holders_result.holders:
            is_increasing = None
            try:
                changes_result = self._detect_position_changes.execute(h.filer_name)
                for c in changes_result.changes:
                    if c.cusip == h.cusip:
                        is_increasing = c.change_type == "increased"
                        break
                else:
                    is_increasing = False  # this filer's changes were checked, but this cusip wasn't in them
            except DetectPositionChangesError as exc:
                logger.warning(
                    "Couldn't determine position change for filer '%s' on %s: %s", h.filer_name, ticker, exc,
                )
            if is_increasing:
                any_increasing = True
            signals.append(InstitutionalHolderSignal(
                filer_name=h.filer_name, current_shares=h.shares_or_principal_amount,
                current_value_usd=h.value_usd, is_increasing=is_increasing,
            ))
        return signals, any_increasing, ground_truth_cusip

    def _get_activist_signal(self, ticker: str, ground_truth_cusip: str | None) -> tuple[list, bool]:
        try:
            result = self._get_beneficial_ownership_disclosures.execute(ticker)
        except GetBeneficialOwnershipDisclosuresError:
            return [], False

        disclosures_13d = [d for d in result.disclosures if d.form_type == "13D"]

        # Filter out misattributed filings when a real, verified CUSIP
        # is available -- see the ground_truth_cusip comment above for
        # the real, confirmed reason this check exists. When no ground
        # truth is available (this ticker has no 13F holdings data at
        # all), this can't be validated either way -- honestly logged
        # rather than silently either trusting or discarding
        # unverifiable data.
        if ground_truth_cusip is not None:
            mismatched = [d for d in disclosures_13d if d.cusip != ground_truth_cusip]
            if mismatched:
                logger.warning(
                    "Discarding %d likely-misattributed 13D filing(s) for %s: "
                    "CUSIP didn't match this ticker's own, real CUSIP (%s)",
                    len(mismatched), ticker, ground_truth_cusip,
                )
            disclosures_13d = [d for d in disclosures_13d if d.cusip == ground_truth_cusip]
        else:
            logger.warning(
                "No ground-truth CUSIP available for %s (no 13F holdings data) -- "
                "13D filings shown unfiltered and may include misattributed results.",
                ticker,
            )

        return disclosures_13d, len(disclosures_13d) > 0

    def _get_insider_signal(self, ticker: str) -> tuple[list, bool]:
        try:
            result = self._get_insider_transactions.execute(ticker)
        except GetInsiderTransactionsError:
            return [], False

        # Only a real, discretionary purchase at a genuine, non-zero
        # price counts -- excludes option exercises, RSU vesting, and
        # other routine, price=0 compensation events, matching the
        # same honest distinction already established in the insider
        # transactions feature itself.
        purchases = [
            t for t in result.transactions
            if t.transaction_type == "P-Purchase" and t.price > 0
        ]
        return purchases, len(purchases) > 0
