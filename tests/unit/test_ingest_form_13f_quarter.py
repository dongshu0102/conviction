from datetime import date, datetime, timedelta, timezone

from src.application.use_cases.ingest_form_13f_quarter import (
    IngestForm13FQuarterError,
    IngestForm13FQuarterUseCase,
)
from src.domain.entities.institutional_holding import InstitutionalHolding
from tests.unit.fakes import (
    FakeInstitutionalHoldingRepository,
    FakeSecForm13FDownloader,
)


def _holding(accession="0001067983-26-000123", cusip="037833100") -> InstitutionalHolding:
    return InstitutionalHolding(
        accession_number=accession, filer_cik="0001067983", filer_name="BERKSHIRE HATHAWAY INC",
        period_of_report=date(2026, 6, 30), issuer_name="APPLE INC", title_of_class="COM",
        cusip=cusip, value_usd=151_000_000, shares_or_principal_amount=905_000, share_type="SH",
        put_call=None, investment_discretion="SOLE", voting_authority_sole=905_000,
        voting_authority_shared=0, voting_authority_none=0,
    )


def _sample_files():
    submission_tsv = (
        "ACCESSION_NUMBER\tCIK\tSUBMISSIONTYPE\tFILING_DATE\tPERIODOFREPORT\n"
        "0001067983-26-000123\t0001067983\t13F-HR\t14-AUG-2026\t30-JUN-2026\n"
    )
    coverpage_tsv = (
        "ACCESSION_NUMBER\tFILINGMANAGER_NAME\n"
        "0001067983-26-000123\tBERKSHIRE HATHAWAY INC\n"
    )
    infotable_tsv = (
        "ACCESSION_NUMBER\tNAMEOFISSUER\tTITLEOFCLASS\tCUSIP\tVALUE\tSSHPRNAMT\tSSHPRNAMTTYPE\n"
        "0001067983-26-000123\tAPPLE INC\tCOM\t037833100\t150000\t900000\tSH\n"
    )
    return {"SUBMISSION.tsv": submission_tsv, "COVERPAGE.tsv": coverpage_tsv, "INFOTABLE.tsv": infotable_tsv}


def _use_case(downloader=None, repo=None):
    return IngestForm13FQuarterUseCase(
        downloader or FakeSecForm13FDownloader(),
        repo or FakeInstitutionalHoldingRepository(),
    )


def test_execute_parses_downloads_and_saves_holdings() -> None:
    downloader = FakeSecForm13FDownloader(files_by_period={"2026q2": _sample_files()})
    repo = FakeInstitutionalHoldingRepository()
    use_case = _use_case(downloader=downloader, repo=repo)

    result = use_case.execute("2026q2", date(2026, 6, 30))

    assert result.submissions_parsed == 1
    assert result.submissions_kept == 1
    assert result.holdings_inserted == 1
    assert repo.bulk_save_calls == [1]


def test_execute_wraps_a_real_download_failure_in_the_use_cases_own_error() -> None:
    downloader = FakeSecForm13FDownloader(raise_for_periods={"2026q2"})
    use_case = _use_case(downloader=downloader)

    try:
        use_case.execute("2026q2", date(2026, 6, 30))
        assert False, "expected IngestForm13FQuarterError"
    except IngestForm13FQuarterError:
        pass


def test_execute_filters_out_holdings_for_a_different_period_than_requested() -> None:
    """Regression guard for a real, plausible case: SEC's own archive
    boundaries don't always align to a clean quarter, so a stray
    filing for an adjacent period must not leak into the requested
    period's data."""
    submission_tsv = (
        "ACCESSION_NUMBER\tCIK\tSUBMISSIONTYPE\tFILING_DATE\tPERIODOFREPORT\n"
        "0001067983-26-000123\t0001067983\t13F-HR\t14-AUG-2026\t30-JUN-2026\n"
        "0009999999-26-000999\t0009999999\t13F-HR\t14-MAY-2026\t31-MAR-2026\n"
    )
    coverpage_tsv = (
        "ACCESSION_NUMBER\tFILINGMANAGER_NAME\n"
        "0001067983-26-000123\tBERKSHIRE HATHAWAY INC\n"
        "0009999999-26-000999\tSOME OTHER FUND\n"
    )
    infotable_tsv = (
        "ACCESSION_NUMBER\tNAMEOFISSUER\tTITLEOFCLASS\tCUSIP\tVALUE\tSSHPRNAMT\tSSHPRNAMTTYPE\n"
        "0001067983-26-000123\tAPPLE INC\tCOM\t037833100\t150000\t900000\tSH\n"
        "0009999999-26-000999\tMICROSOFT CORP\tCOM\t594918104\t80000\t200000\tSH\n"
    )
    files = {"SUBMISSION.tsv": submission_tsv, "COVERPAGE.tsv": coverpage_tsv, "INFOTABLE.tsv": infotable_tsv}
    downloader = FakeSecForm13FDownloader(files_by_period={"2026q2-window": files})
    use_case = _use_case(downloader=downloader)

    result = use_case.execute("2026q2-window", date(2026, 6, 30))

    assert result.holdings_inserted == 1  # only the Jun 30 filing, not the Mar 31 stray


# --- Resumability -----------------------------------------------------------


def test_execute_inserts_everything_on_a_completely_fresh_run() -> None:
    downloader = FakeSecForm13FDownloader(files_by_period={"2026q2": _sample_files()})
    repo = FakeInstitutionalHoldingRepository()
    use_case = _use_case(downloader=downloader, repo=repo)

    result = use_case.execute("2026q2", date(2026, 6, 30))

    assert result.holdings_already_present == 0
    assert result.holdings_inserted == 1
    assert result.holdings_deleted == 0  # never deletes by default


def test_execute_resumes_by_skipping_an_already_present_accession_number() -> None:
    """The core resumability behavior: a real, confirmed production
    issue showed a single quarter's bulk insert can be interrupted
    partway through by a dropped connection -- re-running must skip
    what's already stored, not re-insert duplicates or wipe progress."""
    downloader = FakeSecForm13FDownloader(files_by_period={"2026q2": _sample_files()})
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([_holding(accession="0001067983-26-000123")])  # simulates a prior, partial run

    use_case = _use_case(downloader=downloader, repo=repo)
    result = use_case.execute("2026q2", date(2026, 6, 30))

    assert result.holdings_already_present == 1
    assert result.holdings_inserted == 0  # nothing new to insert, already there
    assert result.holdings_deleted == 0


def test_execute_inserts_only_the_remaining_holdings_when_some_are_already_present() -> None:
    submission_tsv = (
        "ACCESSION_NUMBER\tCIK\tSUBMISSIONTYPE\tFILING_DATE\tPERIODOFREPORT\n"
        "0001-26-000001\t0001067983\t13F-HR\t14-AUG-2026\t30-JUN-2026\n"
        "0002-26-000002\t0009999999\t13F-HR\t14-AUG-2026\t30-JUN-2026\n"
    )
    coverpage_tsv = (
        "ACCESSION_NUMBER\tFILINGMANAGER_NAME\n"
        "0001-26-000001\tBERKSHIRE HATHAWAY INC\n"
        "0002-26-000002\tSOME OTHER FUND\n"
    )
    infotable_tsv = (
        "ACCESSION_NUMBER\tNAMEOFISSUER\tTITLEOFCLASS\tCUSIP\tVALUE\tSSHPRNAMT\tSSHPRNAMTTYPE\n"
        "0001-26-000001\tAPPLE INC\tCOM\t037833100\t150000\t900000\tSH\n"
        "0002-26-000002\tMICROSOFT CORP\tCOM\t594918104\t80000\t200000\tSH\n"
    )
    files = {"SUBMISSION.tsv": submission_tsv, "COVERPAGE.tsv": coverpage_tsv, "INFOTABLE.tsv": infotable_tsv}
    downloader = FakeSecForm13FDownloader(files_by_period={"2026q2": files})
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([_holding(accession="0001-26-000001")])  # only the first filing already landed

    use_case = _use_case(downloader=downloader, repo=repo)
    result = use_case.execute("2026q2", date(2026, 6, 30))

    assert result.holdings_already_present == 1
    assert result.holdings_inserted == 1  # only the second filing's holding


def test_execute_does_not_delete_anything_by_default() -> None:
    downloader = FakeSecForm13FDownloader(files_by_period={"2026q2": _sample_files()})
    repo = FakeInstitutionalHoldingRepository()
    use_case = _use_case(downloader=downloader, repo=repo)

    use_case.execute("2026q2", date(2026, 6, 30))

    assert repo.delete_period_calls == []


def test_execute_deletes_first_when_force_full_reingest_is_true() -> None:
    downloader = FakeSecForm13FDownloader(files_by_period={"2026q2": _sample_files()})
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([_holding(accession="0001067983-26-000123")])

    use_case = _use_case(downloader=downloader, repo=repo)
    result = use_case.execute("2026q2", date(2026, 6, 30), force_full_reingest=True)

    assert repo.delete_period_calls == [date(2026, 6, 30)]
    assert result.holdings_deleted == 1
    assert result.holdings_already_present == 0  # everything was deleted, so nothing to skip
    assert result.holdings_inserted == 1  # re-inserted fresh
