"""Use case: ingest one quarter's Form 13F bulk data set end to end.

Deliberately a single quarter per call, not "ingest everything since
2013" in one shot — each quarter is its own, independently retryable
unit of work, matching this codebase's established bulk-ingestion
philosophy (see ingest_sp500_universe.py's own partial-failure
isolation reasoning) rather than one enormous, all-or-nothing job.

Resumable by default: a real, confirmed production issue showed a
single quarter's ~3.2M-row insert can span 25-30+ minutes, and a home
network connection genuinely can't always sustain that without a
transient drop somewhere in the middle (confirmed directly from RDS's
own Postgres log: "could not receive data from client"). Rather than
wipe and restart from zero on every re-run, this checks which
accession numbers (filings) are already stored for the period and
only inserts the ones still missing — so an interrupted run resumes
from where it left off instead of discarding real, already-committed
progress.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from src.domain.repositories.institutional_holding_repository import (
    InstitutionalHoldingRepository,
)
from src.domain.services.form_13f_parsing import (
    parse_coverpages,
    parse_infotable,
    parse_submissions,
    select_latest_13f_hr_submissions,
)
from src.infrastructure.data_providers.sec_form_13f_downloader import (
    Form13FDownloadError,
    SecForm13FDownloader,
)

logger = logging.getLogger(__name__)


class IngestForm13FQuarterError(Exception):
    """A real, visible failure to ingest one quarter — never silently
    swallowed."""


@dataclass(frozen=True, slots=True)
class IngestForm13FQuarterResult:
    period_label: str
    period_of_report: date
    submissions_parsed: int
    submissions_kept: int
    holdings_deleted: int
    holdings_already_present: int
    holdings_inserted: int


class IngestForm13FQuarterUseCase:
    def __init__(
        self,
        downloader: SecForm13FDownloader,
        repository: InstitutionalHoldingRepository,
    ) -> None:
        self._downloader = downloader
        self._repository = repository

    def execute(
        self, period_label: str, period_of_report: date, force_full_reingest: bool = False,
    ) -> IngestForm13FQuarterResult:
        """period_label matches SEC's own file-naming convention (e.g.
        "2026q1"); period_of_report is the actual quarter-end date
        (e.g. date(2026, 3, 31)) used to scope the existing-data check
        and to confirm which rows this run is responsible for — the
        two are independent because SEC's own file-naming convention
        isn't always a clean single quarter (some archives span 3
        calendar months that don't align to a quarter boundary, e.g.
        "01mar2026-31may2026").

        force_full_reingest=True deletes every existing row for the
        period first and re-inserts everything from scratch — the
        rare, explicit case (e.g. SEC issues a correction) rather than
        the default, which resumes from whatever's already there."""
        logger.info("Downloading Form 13F data set for %s", period_label)
        try:
            files = self._downloader.download_quarter(period_label)
        except Form13FDownloadError as exc:
            raise IngestForm13FQuarterError(str(exc)) from exc

        submissions = parse_submissions(files["SUBMISSION.tsv"])
        kept = select_latest_13f_hr_submissions(submissions)
        filer_names = parse_coverpages(files["COVERPAGE.tsv"])
        holdings = parse_infotable(files["INFOTABLE.tsv"], kept, submissions, filer_names)

        # Only keep holdings whose period actually matches what the
        # caller asked to ingest — a real, plausible case since a
        # "3 calendar months" archive can span a boundary and include
        # a stray filing for an adjacent period.
        holdings = [h for h in holdings if h.period_of_report == period_of_report]

        logger.info(
            "%s: %d submissions parsed, %d kept after de-dup, %d holdings for %s",
            period_label, len(submissions), len(kept), len(holdings), period_of_report,
        )

        deleted = 0
        if force_full_reingest:
            deleted = self._repository.delete_period(period_of_report)
            existing_accessions: set[str] = set()
        else:
            existing_accessions = self._repository.get_existing_accession_numbers(period_of_report)

        remaining = [h for h in holdings if h.accession_number not in existing_accessions]
        already_present = len(holdings) - len(remaining)

        if already_present:
            logger.info(
                "%s: %d holdings already stored from a prior run, inserting the remaining %d",
                period_label, already_present, len(remaining),
            )

        inserted = self._repository.bulk_save(remaining)

        return IngestForm13FQuarterResult(
            period_label=period_label, period_of_report=period_of_report,
            submissions_parsed=len(submissions), submissions_kept=len(kept),
            holdings_deleted=deleted, holdings_already_present=already_present,
            holdings_inserted=inserted,
        )
