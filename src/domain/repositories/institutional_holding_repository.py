from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from src.domain.entities.institutional_holding import InstitutionalHolding


class InstitutionalHoldingRepository(ABC):
    @abstractmethod
    def bulk_save(self, holdings: list[InstitutionalHolding]) -> int:
        """Inserts every holding, returns the count actually inserted.
        Callers are expected to delete_period first when re-running an
        ingestion for a period already loaded — this does not
        deduplicate against existing rows itself."""

    @abstractmethod
    def delete_period(self, period_of_report: date) -> int:
        """Deletes every row for the given quarter, returns the count
        deleted. Makes re-running the ingestion for an already-loaded
        period idempotent rather than accumulating duplicate rows."""

    @abstractmethod
    def get_by_cusip(self, cusip: str, period_of_report: date) -> list[InstitutionalHolding]:
        """Every filer's reported position in one security for one
        quarter — "who holds this stock.\""""

    @abstractmethod
    def get_by_filer(self, filer_cik: str, period_of_report: date) -> list[InstitutionalHolding]:
        """One filer's full reported portfolio for one quarter —
        "what does this fund hold.\""""
