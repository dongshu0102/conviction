from datetime import date

from src.application.use_cases.ingest_form_13f_quarter import (
    IngestForm13FQuarterError,
    IngestForm13FQuarterUseCase,
)
from tests.unit.fakes import (
    FakeInstitutionalHoldingRepository,
    FakeSecForm13FDownloader,
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


def test_execute_parses_downloads_and_saves_holdings() -> None:
    downloader = FakeSecForm13FDownloader(files_by_period={"2026q2": _sample_files()})
    repo = FakeInstitutionalHoldingRepository()
    use_case = IngestForm13FQuarterUseCase(downloader, repo)

    result = use_case.execute("2026q2", date(2026, 6, 30))

    assert result.submissions_parsed == 1
    assert result.submissions_kept == 1
    assert result.holdings_inserted == 1
    assert repo.bulk_save_calls == [1]


def test_execute_deletes_existing_period_data_before_saving_when_replace_existing() -> None:
    downloader = FakeSecForm13FDownloader(files_by_period={"2026q2": _sample_files()})
    repo = FakeInstitutionalHoldingRepository()
    use_case = IngestForm13FQuarterUseCase(downloader, repo)

    use_case.execute("2026q2", date(2026, 6, 30), replace_existing=True)

    assert repo.delete_period_calls == [date(2026, 6, 30)]


def test_execute_skips_delete_when_replace_existing_is_false() -> None:
    downloader = FakeSecForm13FDownloader(files_by_period={"2026q2": _sample_files()})
    repo = FakeInstitutionalHoldingRepository()
    use_case = IngestForm13FQuarterUseCase(downloader, repo)

    use_case.execute("2026q2", date(2026, 6, 30), replace_existing=False)

    assert repo.delete_period_calls == []


def test_execute_wraps_a_real_download_failure_in_the_use_cases_own_error() -> None:
    downloader = FakeSecForm13FDownloader(raise_for_periods={"2026q2"})
    repo = FakeInstitutionalHoldingRepository()
    use_case = IngestForm13FQuarterUseCase(downloader, repo)

    try:
        use_case.execute("2026q2", date(2026, 6, 30))
        assert False, "expected IngestForm13FQuarterError"
    except IngestForm13FQuarterError:
        pass


def test_execute_filters_out_holdings_for_a_different_period_than_requested() -> None:
    """Regression guard for a real, plausible case: SEC's own archive
    boundaries don't always align to a clean quarter (e.g. a 3-month
    window spanning a boundary), so a stray filing for an adjacent
    period must not leak into the requested period's data."""
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
    repo = FakeInstitutionalHoldingRepository()
    use_case = IngestForm13FQuarterUseCase(downloader, repo)

    result = use_case.execute("2026q2-window", date(2026, 6, 30))

    assert result.holdings_inserted == 1  # only the Jun 30 filing, not the Mar 31 stray
