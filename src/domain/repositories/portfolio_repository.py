from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.portfolio import Portfolio, PortfolioHolding


class PortfolioRepository(ABC):
    @abstractmethod
    def create(self, portfolio: Portfolio) -> None: ...

    @abstractmethod
    def get_by_id(self, portfolio_id: str) -> Portfolio | None:
        """Returns the portfolio with its holdings populated."""

    @abstractmethod
    def list_for_user(self, user_id: str) -> list[Portfolio]:
        """Returns portfolios WITHOUT holdings populated — a summary list.
        Call get_by_id for full holding detail on one portfolio. Avoids
        an N+1-shaped fetch when a user just wants their portfolio names.
        """

    @abstractmethod
    def delete(self, portfolio_id: str) -> bool: ...

    @abstractmethod
    def upsert_holding(self, portfolio_id: str, holding: PortfolioHolding) -> None:
        """Insert or replace the position for this ticker in this
        portfolio — see PortfolioHolding docstring on why this is
        state, not a transaction log."""

    @abstractmethod
    def remove_holding(self, portfolio_id: str, ticker: str) -> bool: ...
