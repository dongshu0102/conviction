"""Use case: compute portfolio-level Greeks.

Position-size-weighted sum of each Greek (delta, gamma, theta, vega)
across all option holdings, using live quotes from the options
provider. Standard 100-share contract multiplier applied.

If ANY Greek is missing for a position's live quote, that WHOLE
position is excluded from the aggregate (not partially included with
a missing value treated as zero) — same "missing data means excluded,
not silently fabricated as zero" principle used throughout this
codebase (see YearlyRatios). A silently-zeroed missing Greek would
understate real portfolio risk, which is a worse failure mode than an
honestly incomplete aggregate.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.application.interfaces.options_data_provider import OptionsDataProvider
from src.application.use_cases.manage_portfolio import PortfolioNotFoundError
from src.domain.entities.option import PortfolioGreeks
from src.domain.repositories.portfolio_repository import PortfolioRepository

CONTRACT_MULTIPLIER = 100  # standard: 1 option contract = 100 shares of the underlying


class ComputePortfolioGreeksUseCase:
    def __init__(
        self, portfolio_repo: PortfolioRepository, options_provider: OptionsDataProvider
    ) -> None:
        self._portfolio_repo = portfolio_repo
        self._options_provider = options_provider

    def execute(self, portfolio_id: str) -> PortfolioGreeks:
        portfolio = self._portfolio_repo.get_by_id(portfolio_id)
        if portfolio is None:
            raise PortfolioNotFoundError(portfolio_id)

        total_delta = total_gamma = total_theta = total_vega = 0.0
        included = 0
        excluded: list[str] = []

        for holding in portfolio.option_holdings:
            quote = self._options_provider.get_option_quote(holding.contract)
            if quote is None or None in (quote.delta, quote.gamma, quote.theta, quote.vega):
                excluded.append(holding.contract.occ_symbol_fragment)
                continue

            weight = holding.contracts_held * CONTRACT_MULTIPLIER
            total_delta += quote.delta * weight
            total_gamma += quote.gamma * weight
            total_theta += quote.theta * weight
            total_vega += quote.vega * weight
            included += 1

        return PortfolioGreeks(
            portfolio_id=portfolio_id,
            as_of=datetime.now(timezone.utc),
            total_delta=total_delta,
            total_gamma=total_gamma,
            total_theta=total_theta,
            total_vega=total_vega,
            positions_included=included,
            positions_excluded=excluded,
        )
