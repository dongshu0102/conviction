from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from src.domain.entities.institutional_holding import InstitutionalHolding


class InstitutionalHoldingRepository(ABC):
    @abstractmethod
    def bulk_save(self, holdings: list[InstitutionalHolding]) -> int:
        """Inserts every holding, returns the count actually inserted.
        Callers are expected to have already filtered out holdings for
        accession numbers returned by get_existing_accession_numbers —
        this does not deduplicate against existing rows itself."""

    @abstractmethod
    def delete_period(self, period_of_report: date) -> int:
        """Deletes every row for the given quarter, returns the count
        deleted. Only used for an explicit full re-ingest — normal
        re-runs after an interruption resume via
        get_existing_accession_numbers instead of deleting anything."""

    @abstractmethod
    def get_existing_accession_numbers(self, period_of_report: date) -> set[str]:
        """Every accession_number already stored for this quarter —
        lets a re-run after an interrupted ingestion skip
        already-inserted filings and resume from where it left off,
        rather than re-downloading correctly but then discarding
        real, already-committed progress."""

    @abstractmethod
    def get_by_cusip(self, cusip: str, period_of_report: date) -> list[InstitutionalHolding]:
        """Every filer's reported position in one security for one
        quarter — "who holds this stock.\""""

    @abstractmethod
    def get_by_filer(self, filer_cik: str, period_of_report: date) -> list[InstitutionalHolding]:
        """One filer's full reported portfolio for one quarter —
        "what does this fund hold.\""""
