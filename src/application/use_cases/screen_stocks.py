"""Use case: screen a bounded set of tickers for value/quality.

Composite ranking, not a single magic number — same "explainable, not
a black box" principle as everywhere else. Value score ranks candidates
by cheapness (P/E, P/S, EV/EBITDA, lower is better); quality score
ranks by fundamentals (ROE, net margin — higher is better; leverage —
lower is better). Composite blends the two, so "recommend" and "value"
are the same underlying computation, just sorted/read differently by
the caller.

Candidates are excluded (not silently zeroed or guessed) when a
required metric is missing, or when a valuation multiple is negative —
a negative P/E means negative earnings, which is a fundamentally
different situation from "cheap," not a lower value on the same scale.
Negative debt-to-equity (implying negative shareholders' equity) is
excluded for the same reason — a real red flag, not a data point to
silently rank as "low leverage."
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.application.interfaces.data_provider import DataProviderError
from src.application.use_cases.compute_financial_analysis import (
    ComputeFinancialAnalysisUseCase,
)
from src.application.use_cases.compute_valuation import ComputeValuationUseCase, NoFinancialDataError
from src.application.use_cases.get_company_financials import CompanyNotFoundError
from src.domain.entities.stock_screen import ScreenedStock, ScreenResult


def _ranks(values: list[float], ascending: bool) -> list[float]:
    """1-indexed ranks for each value, in the order given. Lower rank
    number always means 'better' by the caller's convention (pass
    ascending=True when a smaller raw value is better, e.g. P/E; pass
    ascending=False when a larger raw value is better, e.g. ROE)."""
    order = sorted(range(len(values)), key=lambda i: values[i], reverse=not ascending)
    ranks = [0.0] * len(values)
    for rank, original_index in enumerate(order, start=1):
        ranks[original_index] = float(rank)
    return ranks


class ScreenStocksUseCase:
    def __init__(
        self,
        compute_valuation: ComputeValuationUseCase,
        compute_analysis: ComputeFinancialAnalysisUseCase,
    ) -> None:
        self._compute_valuation = compute_valuation
        self._compute_analysis = compute_analysis

    def execute(self, tickers: list[str]) -> ScreenResult:
        raw: list[dict] = []
        excluded: list[str] = []

        for ticker in tickers:
            try:
                valuation = self._compute_valuation.execute(ticker)
                analysis = self._compute_analysis.execute(ticker, years=1)
            except (CompanyNotFoundError, NoFinancialDataError, DataProviderError):
                excluded.append(ticker)
                continue

            if not analysis.yearly_ratios:
                excluded.append(ticker)
                continue
            latest = analysis.yearly_ratios[-1]  # ascending order — last is most recent

            pe, ps, ev_ebitda = (
                valuation.price_to_earnings,
                valuation.price_to_sales,
                valuation.ev_to_ebitda,
            )
            roe, net_margin, debt_to_equity = (
                latest.return_on_equity,
                latest.net_margin,
                latest.debt_to_equity,
            )

            if None in (pe, ps, ev_ebitda, roe, net_margin, debt_to_equity):
                excluded.append(ticker)
                continue
            if pe <= 0 or ps <= 0 or ev_ebitda <= 0:
                excluded.append(ticker)  # negative earnings/sales/EBITDA — not "cheap"
                continue
            if debt_to_equity < 0:
                excluded.append(ticker)  # negative equity — a red flag, not low leverage
                continue

            raw.append(
                {
                    "ticker": ticker,
                    "price": valuation.price,
                    "pe": pe,
                    "ps": ps,
                    "ev_ebitda": ev_ebitda,
                    "roe": roe,
                    "net_margin": net_margin,
                    "debt_to_equity": debt_to_equity,
                }
            )

        if not raw:
            return ScreenResult(
                as_of=datetime.now(timezone.utc),
                candidates_requested=len(tickers),
                excluded=excluded,
                results=[],
            )

        pe_ranks = _ranks([r["pe"] for r in raw], ascending=True)
        ps_ranks = _ranks([r["ps"] for r in raw], ascending=True)
        ev_ranks = _ranks([r["ev_ebitda"] for r in raw], ascending=True)
        roe_ranks = _ranks([r["roe"] for r in raw], ascending=False)
        margin_ranks = _ranks([r["net_margin"] for r in raw], ascending=False)
        leverage_ranks = _ranks([r["debt_to_equity"] for r in raw], ascending=True)

        results = []
        for i, r in enumerate(raw):
            value_score = (pe_ranks[i] + ps_ranks[i] + ev_ranks[i]) / 3
            quality_score = (roe_ranks[i] + margin_ranks[i] + leverage_ranks[i]) / 3
            composite_score = (value_score + quality_score) / 2
            results.append(
                ScreenedStock(
                    ticker=r["ticker"],
                    price=r["price"],
                    price_to_earnings=r["pe"],
                    price_to_sales=r["ps"],
                    ev_to_ebitda=r["ev_ebitda"],
                    return_on_equity=r["roe"],
                    net_margin=r["net_margin"],
                    debt_to_equity=r["debt_to_equity"],
                    value_score=value_score,
                    quality_score=quality_score,
                    composite_score=composite_score,
                )
            )

        results.sort(key=lambda s: s.composite_score)

        return ScreenResult(
            as_of=datetime.now(timezone.utc),
            candidates_requested=len(tickers),
            excluded=excluded,
            results=results,
        )
