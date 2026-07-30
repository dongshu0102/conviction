from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.research_report import CompanyResearchReport


class ResearchReportRepository(ABC):
    @abstractmethod
    def save(self, report: CompanyResearchReport) -> None:
        """Append-only: each generation is stored, not upserted, so
        history of research over time is preserved rather than
        overwritten — useful once monitoring (Phase 4) needs to diff
        today's view of a company against last quarter's."""

    @abstractmethod
    def get_latest(self, ticker: str) -> CompanyResearchReport | None: ...

    @abstractmethod
    def list_history(self, ticker: str, limit: int = 10) -> list[CompanyResearchReport]: ...
