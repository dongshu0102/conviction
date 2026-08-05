"""Use case: assess a ticker as a speculative-growth (potential
"100x") candidate.

Deliberately separate from factor scoring — see
SpeculativeGrowthAssessment's own docstring for why reusing the
existing factor system here would be actively counterproductive.

Requires the ticker to already be ingested (via ingest_company), same
prerequisite as valuation/analysis elsewhere in this codebase — this
use case composes GetCompanyFinancialsUseCase and
ComputeValuationUseCase rather than duplicating ingestion or currency
handling, inheriting the existing non-USD-reporter safety net for
market cap "for free."
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.application.use_cases.compute_valuation import ComputeValuationUseCase
from src.application.use_cases.get_company_financials import GetCompanyFinancialsUseCase
from src.domain.entities.speculative_growth_assessment import SpeculativeGrowthAssessment

_SMALL_CAP_THRESHOLD = 2_000_000_000  # $2B — a common small-cap ceiling


class AssessSpeculativeGrowthUseCase:
    def __init__(
        self,
        get_financials: GetCompanyFinancialsUseCase,
        compute_valuation: ComputeValuationUseCase,
    ) -> None:
        self._get_financials = get_financials
        self._compute_valuation = compute_valuation

    def execute(self, ticker: str) -> SpeculativeGrowthAssessment:
        ticker = ticker.strip().upper()
        financials = self._get_financials.execute(ticker, years=5)

        statements = sorted(
            financials.income_statements, key=lambda s: s.key.fiscal_year, reverse=True
        )
        years_available = len(statements)

        revenue_growth_latest = None
        revenue_growth_prior = None
        growth_trend = "insufficient_data"
        if len(statements) >= 2 and statements[0].revenue and statements[1].revenue:
            revenue_growth_latest = (statements[0].revenue - statements[1].revenue) / statements[1].revenue
        if len(statements) >= 3 and statements[1].revenue and statements[2].revenue:
            revenue_growth_prior = (statements[1].revenue - statements[2].revenue) / statements[2].revenue
        if revenue_growth_latest is not None and revenue_growth_prior is not None:
            growth_trend = "accelerating" if revenue_growth_latest > revenue_growth_prior else "decelerating"

        net_income_latest = statements[0].net_income if statements else None
        is_profitable = None if net_income_latest is None else net_income_latest > 0

        cash_flows = sorted(
            financials.cash_flow_statements, key=lambda s: s.key.fiscal_year, reverse=True
        )
        balance_sheets = sorted(
            financials.balance_sheets, key=lambda s: s.key.fiscal_year, reverse=True
        )
        cash_runway_months = None
        if cash_flows and balance_sheets:
            ocf = cash_flows[0].operating_cash_flow
            cash = balance_sheets[0].cash_and_equivalents
            if ocf is not None and ocf < 0 and cash is not None:
                monthly_burn = abs(ocf) / 12
                cash_runway_months = cash / monthly_burn if monthly_burn > 0 else None

        market_cap = None
        try:
            market_cap = self._compute_valuation.execute(ticker).market_cap
        except Exception:
            # Valuation can fail for reasons unrelated to this
            # assessment (e.g. no live quote) — a missing market cap
            # shouldn't block the rest of the assessment, it's just
            # one more honestly-null field.
            pass

        risk_flags: list[str] = []
        if is_profitable is False:
            risk_flags.append("Currently unprofitable")
        if cash_runway_months is not None and cash_runway_months < 12:
            risk_flags.append(f"Burning cash with under 12 months of runway (~{cash_runway_months:.0f} months)")
        if growth_trend == "decelerating":
            risk_flags.append("Revenue growth is decelerating, not accelerating")
        if years_available < 3:
            risk_flags.append(f"Limited operating history — only {years_available} year(s) of financials available")
        if market_cap is not None and market_cap < _SMALL_CAP_THRESHOLD:
            risk_flags.append("Small market cap — thin liquidity and high volatility should be expected")

        return SpeculativeGrowthAssessment(
            ticker=ticker,
            as_of=datetime.now(timezone.utc),
            market_cap=market_cap,
            revenue_growth_latest_yoy=revenue_growth_latest,
            revenue_growth_prior_yoy=revenue_growth_prior,
            growth_trend=growth_trend,
            is_profitable=is_profitable,
            net_income_latest=net_income_latest,
            cash_runway_months=cash_runway_months,
            years_of_data_available=years_available,
            risk_flags=risk_flags,
        )
