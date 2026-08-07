"""Use case: comparable-company valuation.

Deliberately reuses ComputeValuationUseCase for every peer's own
multiple rather than recomputing that logic here — same multiples the
rest of the platform already shows for a single company, just
aggregated across a peer set and applied to the target. Peer discovery
is same-sector, same-universe (whatever's been ingested), excluding
the target itself; a peer that fails to value (missing data, bad
quote) is skipped rather than aborting the whole analysis, but every
skip is reported, not silently dropped.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from src.application.use_cases.compute_valuation import ComputeValuationUseCase
from src.application.use_cases.get_company_financials import (
    CompanyNotFoundError,
    GetCompanyFinancialsUseCase,
)
from src.domain.repositories.company_repository import CompanyRepository
from src.domain.services.valuation_math import CompsResult, compute_comps_valuation


class CompsMetric(str, Enum):
    PE = "pe"                # price_to_earnings, equity-level, target metric = net_income
    EV_EBITDA = "ev_ebitda"  # ev_to_ebitda, enterprise-level, target metric = ebitda
    PS = "ps"                 # price_to_sales, equity-level, target metric = revenue
    PFCF = "pfcf"              # price_to_free_cash_flow, equity-level, target metric = free_cash_flow


_ENTERPRISE_LEVEL_METRICS = {CompsMetric.EV_EBITDA}


class InsufficientPeerDataError(Exception):
    """Raised when zero peers could be valued at all — a comps
    analysis with no peers isn't a comps analysis."""


class InsufficientTargetDataError(Exception):
    """Raised when the target itself lacks the specific metric this
    multiple needs (e.g. asking for EV/EBITDA comps on a company with
    no reported EBITDA)."""


def _most_recent_balance_sheet(balance_sheets):
    if not balance_sheets:
        return None
    return sorted(balance_sheets, key=lambda s: s.key.fiscal_year, reverse=True)[0]


def _most_recent_income_statement(income_statements):
    if not income_statements:
        return None
    return sorted(income_statements, key=lambda s: s.key.fiscal_year, reverse=True)[0]


def _most_recent_cash_flow_statement(cash_flow_statements):
    if not cash_flow_statements:
        return None
    return sorted(cash_flow_statements, key=lambda s: s.key.fiscal_year, reverse=True)[0]


@dataclass(frozen=True, slots=True)
class CompsAssessment:
    ticker: str
    as_of: datetime
    metric: CompsMetric
    peers_considered: list[str]
    peers_used: list[str]
    peers_skipped: list[str]
    result: CompsResult


class ComputeCompsValuationUseCase:
    def __init__(
        self,
        company_repo: CompanyRepository,
        get_financials: GetCompanyFinancialsUseCase,
        compute_valuation: ComputeValuationUseCase,
        max_peers: int = 10,
    ) -> None:
        self._company_repo = company_repo
        self._get_financials = get_financials
        self._compute_valuation = compute_valuation
        self._max_peers = max_peers

    def execute(self, ticker: str, metric: CompsMetric) -> CompsAssessment:
        ticker = ticker.strip().upper()
        target_company = self._company_repo.get_by_ticker(ticker)
        if target_company is None:
            raise CompanyNotFoundError(ticker)

        peers_considered = [
            c.ticker for c in self._company_repo.list_all()
            if c.sector == target_company.sector and c.ticker != ticker
        ][: self._max_peers]

        peer_multiples: list[float] = []
        peers_used: list[str] = []
        peers_skipped: list[str] = []
        for peer_ticker in peers_considered:
            try:
                snapshot = self._compute_valuation.execute(peer_ticker)
            except Exception:
                peers_skipped.append(peer_ticker)
                continue
            value = getattr(snapshot, _SNAPSHOT_FIELD[metric])
            if value is None:
                peers_skipped.append(peer_ticker)
                continue
            peer_multiples.append(value)
            peers_used.append(peer_ticker)

        if not peer_multiples:
            raise InsufficientPeerDataError(
                f"None of {len(peers_considered)} peers considered for {ticker} "
                f"had a usable {metric.value} multiple."
            )

        financials = self._get_financials.execute(ticker, years=1)
        target_metric_value = self._target_metric_value(financials, metric)
        if target_metric_value is None:
            raise InsufficientTargetDataError(
                f"{ticker} has no usable {_TARGET_METRIC_NAME[metric]} figure "
                f"to apply the peer {metric.value} multiple against."
            )

        balance_sheet = _most_recent_balance_sheet(financials.balance_sheets)
        net_debt = (
            (balance_sheet.total_debt or 0.0) - (balance_sheet.cash_and_equivalents or 0.0)
            if balance_sheet else 0.0
        )
        shares_outstanding = balance_sheet.shares_outstanding if balance_sheet else None

        result = compute_comps_valuation(
            peer_multiples=peer_multiples, target_metric=target_metric_value,
            metric_is_enterprise_level=metric in _ENTERPRISE_LEVEL_METRICS,
            net_debt=net_debt, shares_outstanding=shares_outstanding,
        )

        return CompsAssessment(
            ticker=ticker, as_of=datetime.now(timezone.utc), metric=metric,
            peers_considered=peers_considered, peers_used=peers_used,
            peers_skipped=peers_skipped, result=result,
        )

    def _target_metric_value(self, financials, metric: CompsMetric) -> float | None:
        if metric == CompsMetric.PE:
            income = _most_recent_income_statement(financials.income_statements)
            return income.net_income if income else None
        if metric == CompsMetric.EV_EBITDA:
            income = _most_recent_income_statement(financials.income_statements)
            return income.ebitda if income else None
        if metric == CompsMetric.PS:
            income = _most_recent_income_statement(financials.income_statements)
            return income.revenue if income else None
        if metric == CompsMetric.PFCF:
            cash_flow = _most_recent_cash_flow_statement(financials.cash_flow_statements)
            return cash_flow.free_cash_flow if cash_flow else None
        return None


_SNAPSHOT_FIELD = {
    CompsMetric.PE: "price_to_earnings",
    CompsMetric.EV_EBITDA: "ev_to_ebitda",
    CompsMetric.PS: "price_to_sales",
    CompsMetric.PFCF: "price_to_free_cash_flow",
}

_TARGET_METRIC_NAME = {
    CompsMetric.PE: "net income",
    CompsMetric.EV_EBITDA: "EBITDA",
    CompsMetric.PS: "revenue",
    CompsMetric.PFCF: "free cash flow",
}
