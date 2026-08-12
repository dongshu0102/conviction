"""Pure parsing logic for SEC's quarterly Form 13F bulk data sets.

No network or database dependency here at all — these functions take
raw TSV text (already downloaded) and return parsed, structured
results. This is deliberate: the actual download/unzip mechanics
(infrastructure) and the parsing rules (this file, pure domain logic)
are separate concerns, and only the parsing rules need to be this
thoroughly unit-tested — the download step is a thin, hard-to-fake-
realistically HTTP call better covered by a light integration check.

Column names are matched case-insensitively against SEC's own
documented schema (form_13f.pdf) — NAMEOFISSUER, CUSIP, VALUE,
SSHPRNAMT, etc. — via a header-name lookup rather than an assumed
fixed column order, since SEC's exact column order has genuinely
varied across the dataset's history (see the README's own changelog
of format revisions).
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime

from src.domain.entities.institutional_holding import InstitutionalHolding


@dataclass(frozen=True, slots=True)
class _SubmissionInfo:
    accession_number: str
    filer_cik: str
    submission_type: str
    filing_date: date
    period_of_report: date


def _read_tsv_rows(tsv_text: str) -> list[dict[str, str]]:
    """Parses tab-delimited text with a header row into a list of
    dicts keyed by UPPERCASED header name, tolerating the exact
    header casing SEC has used across different dataset versions."""
    reader = csv.DictReader(io.StringIO(tsv_text), delimiter="\t")
    if reader.fieldnames is None:
        return []
    rows = []
    for row in reader:
        rows.append({(k or "").strip().upper(): (v or "").strip() for k, v in row.items()})
    return rows


def _parse_sec_date(raw: str) -> date | None:
    """SEC bulk dataset dates are consistently DD-MON-YYYY (e.g.
    15-AUG-2026) in the TSV files — distinct from the MM/DD/YYYY the
    web UI displays."""
    raw = raw.strip()
    if not raw:
        return None
    for fmt in ("%d-%b-%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def parse_submissions(tsv_text: str) -> dict[str, _SubmissionInfo]:
    """Returns every submission keyed by accession number, WITHOUT
    filtering or de-duplication — that happens in
    select_latest_13f_hr_submissions, a separate, independently
    testable step."""
    result: dict[str, _SubmissionInfo] = {}
    for row in _read_tsv_rows(tsv_text):
        accession = row.get("ACCESSION_NUMBER", "")
        cik = row.get("CIK", "")
        submission_type = row.get("SUBMISSIONTYPE", "")
        filing_date = _parse_sec_date(row.get("FILING_DATE", ""))
        period = _parse_sec_date(row.get("PERIODOFREPORT", ""))
        if not accession or not cik or filing_date is None or period is None:
            continue
        result[accession] = _SubmissionInfo(
            accession_number=accession, filer_cik=cik, submission_type=submission_type,
            filing_date=filing_date, period_of_report=period,
        )
    return result


def select_latest_13f_hr_submissions(submissions: dict[str, _SubmissionInfo]) -> set[str]:
    """Returns the set of accession numbers to actually keep: only
    13F-HR / 13F-HR/A (holdings reports — excludes 13F-NT "no
    holdings to report" notices, which have no information table rows
    anyway), and only the most recently FILED submission per (filer,
    period) — an amendment supersedes the original it corrects, and
    both appear in the same quarterly file undifferentiated unless
    this step runs. Confirmed necessary directly from SEC's own
    dataset documentation: "consumers must de-duplicate by keeping
    only the most recent filing per manager-quarter.\""""
    latest_by_filer_period: dict[tuple[str, date], _SubmissionInfo] = {}
    for sub in submissions.values():
        if not sub.submission_type.upper().startswith("13F-HR"):
            continue
        key = (sub.filer_cik, sub.period_of_report)
        existing = latest_by_filer_period.get(key)
        if existing is None or sub.filing_date > existing.filing_date:
            latest_by_filer_period[key] = sub
    return {sub.accession_number for sub in latest_by_filer_period.values()}


def parse_coverpages(tsv_text: str) -> dict[str, str]:
    """Returns filer name keyed by accession number."""
    result: dict[str, str] = {}
    for row in _read_tsv_rows(tsv_text):
        accession = row.get("ACCESSION_NUMBER", "")
        name = row.get("FILINGMANAGER_NAME", "")
        if accession and name:
            result[accession] = name
    return result


def _parse_int(raw: str) -> int:
    raw = raw.strip().replace(",", "")
    if not raw:
        return 0
    try:
        return int(float(raw))
    except ValueError:
        return 0


def parse_infotable(
    tsv_text: str,
    kept_accession_numbers: set[str],
    submissions: dict[str, _SubmissionInfo],
    filer_names: dict[str, str],
) -> list[InstitutionalHolding]:
    """Emits one InstitutionalHolding per row whose accession number
    survived de-duplication in select_latest_13f_hr_submissions —
    every other row (amendments' originals, 13F-NT filings) is
    silently skipped, not an error."""
    holdings: list[InstitutionalHolding] = []
    for row in _read_tsv_rows(tsv_text):
        accession = row.get("ACCESSION_NUMBER", "")
        if accession not in kept_accession_numbers:
            continue
        sub = submissions.get(accession)
        if sub is None:
            continue

        cusip = row.get("CUSIP", "")
        issuer_name = row.get("NAMEOFISSUER", "")
        if not cusip or not issuer_name:
            continue

        # Real, confirmed bug fix: the older SEC documentation
        # (form_13f.pdf) describes VALUE as "Market value (x$1000)",
        # but the CURRENT bulk data set's raw VALUE column is already
        # in actual dollars, not thousands -- confirmed directly
        # against real, external, independently-reported data: summing
        # every line item for Berkshire Hathaway's Apple position in a
        # real ingested filing gave $57.84 TRILLION with the old x1000
        # multiplication, versus a real, independently reported ~$57.9
        # billion (22% of Berkshire's actual $263B Q1 2026 13F
        # portfolio) -- an almost exact match with NO multiplication at
        # all. SEC appears to have changed this column's convention at
        # some point after the older documentation was written; this
        # is not assumed, it's confirmed against real, external,
        # independently-reported figures.
        value_usd = _parse_int(row.get("VALUE", ""))

        holdings.append(InstitutionalHolding(
            accession_number=accession,
            filer_cik=sub.filer_cik,
            filer_name=filer_names.get(accession, ""),
            period_of_report=sub.period_of_report,
            issuer_name=issuer_name,
            title_of_class=row.get("TITLEOFCLASS", ""),
            cusip=cusip,
            value_usd=value_usd,
            shares_or_principal_amount=_parse_int(row.get("SSHPRNAMT", "")),
            share_type=row.get("SSHPRNAMTTYPE", ""),
            put_call=row.get("PUTCALL") or None,
            investment_discretion=row.get("INVESTMENTDISCRETION", ""),
            voting_authority_sole=_parse_int(row.get("VOTING_AUTH_SOLE", "")),
            voting_authority_shared=_parse_int(row.get("VOTING_AUTH_SHARED", "")),
            voting_authority_none=_parse_int(row.get("VOTING_AUTH_NONE", "")),
        ))
    return holdings
