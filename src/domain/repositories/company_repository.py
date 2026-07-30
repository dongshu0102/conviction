"""Persistence contract for Company entities.

Defined in the domain layer, implemented in infrastructure. Use cases
depend on this abstraction only — never on SQLAlchemy, Postgres, or any
other concrete technology. This is what lets us change databases, or add
a caching layer, without touching a single use case.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.company import Company


class CompanyRepository(ABC):
    @abstractmethod
    def save(self, company: Company) -> None:
        """Insert or update (upsert by ticker)."""

    @abstractmethod
    def get_by_ticker(self, ticker: str) -> Company | None: ...

    @abstractmethod
    def list_all(self, active_only: bool = True) -> list[Company]: ...
