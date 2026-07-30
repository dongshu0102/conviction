from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from src.domain.entities.company import Company  # noqa: F401 (type hint clarity in reads)
from src.domain.entities.portfolio import Portfolio, PortfolioHolding
from src.domain.repositories.company_repository import CompanyRepository
from src.domain.repositories.portfolio_repository import PortfolioRepository


class PortfolioNotFoundError(Exception):
    def __init__(self, portfolio_id: str) -> None:
        self.portfolio_id = portfolio_id
        super().__init__(f"No portfolio found with id '{portfolio_id}'")


class TickerNotIngestedError(Exception):
    def __init__(self, ticker: str) -> None:
        self.ticker = ticker
        super().__init__(
            f"'{ticker}' has not been ingested yet — ingest it first via "
            f"POST /companies/{ticker}/ingest before adding it to a portfolio."
        )


class CreatePortfolioUseCase:
    def __init__(self, portfolio_repo: PortfolioRepository) -> None:
        self._portfolio_repo = portfolio_repo

    def execute(self, user_id: str, name: str) -> Portfolio:
        portfolio = Portfolio(
            portfolio_id=str(uuid.uuid4()),
            user_id=user_id,
            name=name,
            created_at=datetime.now(timezone.utc),
        )
        self._portfolio_repo.create(portfolio)
        return portfolio


class ListPortfoliosUseCase:
    def __init__(self, portfolio_repo: PortfolioRepository) -> None:
        self._portfolio_repo = portfolio_repo

    def execute(self, user_id: str) -> list[Portfolio]:
        return self._portfolio_repo.list_for_user(user_id)


class GetPortfolioUseCase:
    def __init__(self, portfolio_repo: PortfolioRepository) -> None:
        self._portfolio_repo = portfolio_repo

    def execute(self, portfolio_id: str) -> Portfolio:
        portfolio = self._portfolio_repo.get_by_id(portfolio_id)
        if portfolio is None:
            raise PortfolioNotFoundError(portfolio_id)
        return portfolio


class DeletePortfolioUseCase:
    def __init__(self, portfolio_repo: PortfolioRepository) -> None:
        self._portfolio_repo = portfolio_repo

    def execute(self, portfolio_id: str) -> bool:
        return self._portfolio_repo.delete(portfolio_id)


class AddHoldingUseCase:
    def __init__(
        self, portfolio_repo: PortfolioRepository, company_repo: CompanyRepository
    ) -> None:
        self._portfolio_repo = portfolio_repo
        self._company_repo = company_repo

    def execute(
        self,
        portfolio_id: str,
        ticker: str,
        shares: float,
        cost_basis_per_share: float,
        acquired_at: date | None = None,
    ) -> PortfolioHolding:
        if self._portfolio_repo.get_by_id(portfolio_id) is None:
            raise PortfolioNotFoundError(portfolio_id)

        ticker = ticker.strip().upper()
        if self._company_repo.get_by_ticker(ticker) is None:
            raise TickerNotIngestedError(ticker)

        holding = PortfolioHolding(
            ticker=ticker,
            shares=shares,
            cost_basis_per_share=cost_basis_per_share,
            acquired_at=acquired_at,
        )
        self._portfolio_repo.upsert_holding(portfolio_id, holding)
        return holding


class RemoveHoldingUseCase:
    def __init__(self, portfolio_repo: PortfolioRepository) -> None:
        self._portfolio_repo = portfolio_repo

    def execute(self, portfolio_id: str, ticker: str) -> bool:
        return self._portfolio_repo.remove_holding(portfolio_id, ticker.strip().upper())
