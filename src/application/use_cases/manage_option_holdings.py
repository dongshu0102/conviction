"""Use cases for managing option holdings within a portfolio.

Same "state, not a transaction log" principle as PortfolioHolding —
adding the same contract again updates the position rather than
appending a trade.

Deliberately does NOT validate the underlying ticker against our
ingested company universe (unlike AddHoldingUseCase for stocks) —
options exist on indices and ETFs that were never in scope for our
S&P 500 company ingestion, and requiring "ingest this as a company
first" would be a nonsensical requirement for e.g. an SPX option.
"""
from __future__ import annotations

from datetime import date, datetime

from src.application.use_cases.manage_portfolio import PortfolioNotFoundError
from src.domain.entities.option import OptionContract, OptionHolding
from src.domain.repositories.portfolio_repository import PortfolioRepository


class InvalidOptionTypeError(Exception):
    def __init__(self, option_type: str) -> None:
        super().__init__(f"option_type must be 'call' or 'put', got '{option_type}'")


def _normalize_option_type(option_type: str) -> str:
    normalized = option_type.strip().lower()
    if normalized not in ("call", "put"):
        raise InvalidOptionTypeError(option_type)
    return normalized


class AddOptionHoldingUseCase:
    def __init__(self, portfolio_repo: PortfolioRepository) -> None:
        self._portfolio_repo = portfolio_repo

    def execute(
        self,
        portfolio_id: str,
        underlying_ticker: str,
        strike: float,
        expiration: date,
        option_type: str,
        contracts_held: int,
        cost_basis_per_contract: float,
        acquired_at: datetime | None = None,
    ) -> OptionHolding:
        if self._portfolio_repo.get_by_id(portfolio_id) is None:
            raise PortfolioNotFoundError(portfolio_id)

        contract = OptionContract(
            underlying_ticker=underlying_ticker.strip().upper(),
            strike=strike,
            expiration=expiration,
            option_type=_normalize_option_type(option_type),
        )
        holding = OptionHolding(
            contract=contract,
            contracts_held=contracts_held,
            cost_basis_per_contract=cost_basis_per_contract,
            acquired_at=acquired_at,
        )
        self._portfolio_repo.upsert_option_holding(portfolio_id, holding)
        return holding


class RemoveOptionHoldingUseCase:
    def __init__(self, portfolio_repo: PortfolioRepository) -> None:
        self._portfolio_repo = portfolio_repo

    def execute(
        self,
        portfolio_id: str,
        underlying_ticker: str,
        strike: float,
        expiration: date,
        option_type: str,
    ) -> bool:
        contract = OptionContract(
            underlying_ticker=underlying_ticker.strip().upper(),
            strike=strike,
            expiration=expiration,
            option_type=_normalize_option_type(option_type),
        )
        return self._portfolio_repo.remove_option_holding(portfolio_id, contract)
