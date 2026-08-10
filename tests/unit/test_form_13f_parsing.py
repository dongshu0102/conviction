from datetime import date

from src.domain.services.form_13f_parsing import (
    parse_coverpages,
    parse_infotable,
    parse_submissions,
    select_latest_13f_hr_submissions,
)


def _sample_dataset():
    """Realistic dataset: an original 13F-HR later corrected by an
    amendment for the same filer/period, plus a 13F-NT (no holdings)
    submission that must be excluded entirely — the shape of every
    real quarterly file, not a simplified edge case."""
    submission_tsv = (
        "ACCESSION_NUMBER\tCIK\tSUBMISSIONTYPE\tFILING_DATE\tPERIODOFREPORT\n"
        "0001067983-26-000123\t0001067983\t13F-HR\t14-AUG-2026\t30-JUN-2026\n"
        "0001067983-26-000456\t0001067983\t13F-HR/A\t20-AUG-2026\t30-JUN-2026\n"
        "0000936753-26-000789\t0000936753\t13F-NT\t14-AUG-2026\t30-JUN-2026\n"
    )
    coverpage_tsv = (
        "ACCESSION_NUMBER\tFILINGMANAGER_NAME\n"
        "0001067983-26-000123\tBERKSHIRE HATHAWAY INC\n"
        "0001067983-26-000456\tBERKSHIRE HATHAWAY INC\n"
        "0000936753-26-000789\tSOME FUND WITH NO HOLDINGS\n"
    )
    infotable_tsv = (
        "ACCESSION_NUMBER\tNAMEOFISSUER\tTITLEOFCLASS\tCUSIP\tVALUE\tSSHPRNAMT\tSSHPRNAMTTYPE\t"
        "PUTCALL\tINVESTMENTDISCRETION\tVOTING_AUTH_SOLE\tVOTING_AUTH_SHARED\tVOTING_AUTH_NONE\n"
        "0001067983-26-000123\tAPPLE INC\tCOM\t037833100\t150000\t900000\tSH\t\tSOLE\t900000\t0\t0\n"
        "0001067983-26-000456\tAPPLE INC\tCOM\t037833100\t151000\t905000\tSH\t\tSOLE\t905000\t0\t0\n"
    )
    return submission_tsv, coverpage_tsv, infotable_tsv


def test_parse_submissions_reads_every_row_unfiltered() -> None:
    submission_tsv, _, _ = _sample_dataset()
    submissions = parse_submissions(submission_tsv)
    assert len(submissions) == 3
    assert submissions["0001067983-26-000456"].submission_type == "13F-HR/A"
    assert submissions["0001067983-26-000456"].filing_date == date(2026, 8, 20)
    assert submissions["0001067983-26-000456"].period_of_report == date(2026, 6, 30)


def test_select_latest_keeps_only_the_amendment_not_the_original() -> None:
    submission_tsv, _, _ = _sample_dataset()
    submissions = parse_submissions(submission_tsv)
    kept = select_latest_13f_hr_submissions(submissions)
    assert kept == {"0001067983-26-000456"}


def test_select_latest_excludes_13f_nt_no_holdings_notices() -> None:
    submission_tsv, _, _ = _sample_dataset()
    submissions = parse_submissions(submission_tsv)
    kept = select_latest_13f_hr_submissions(submissions)
    assert "0000936753-26-000789" not in kept


def test_parse_coverpages_maps_accession_to_filer_name() -> None:
    _, coverpage_tsv, _ = _sample_dataset()
    names = parse_coverpages(coverpage_tsv)
    assert names["0001067983-26-000123"] == "BERKSHIRE HATHAWAY INC"


def test_parse_infotable_emits_only_kept_accession_rows() -> None:
    submission_tsv, coverpage_tsv, infotable_tsv = _sample_dataset()
    submissions = parse_submissions(submission_tsv)
    kept = select_latest_13f_hr_submissions(submissions)
    filer_names = parse_coverpages(coverpage_tsv)

    holdings = parse_infotable(infotable_tsv, kept, submissions, filer_names)

    assert len(holdings) == 1
    assert holdings[0].accession_number == "0001067983-26-000456"


def test_parse_infotable_converts_value_from_thousands_to_real_dollars() -> None:
    """Regression guard for a real, easy-to-get-wrong detail: SEC's own
    schema documents VALUE as "Market value (x$1000)" -- confirmed
    directly from form_13f.pdf, not assumed."""
    submission_tsv, coverpage_tsv, infotable_tsv = _sample_dataset()
    submissions = parse_submissions(submission_tsv)
    kept = select_latest_13f_hr_submissions(submissions)
    filer_names = parse_coverpages(coverpage_tsv)

    holdings = parse_infotable(infotable_tsv, kept, submissions, filer_names)

    assert holdings[0].value_usd == 151_000_000


def test_parse_infotable_fills_in_filer_name_and_period_from_the_join() -> None:
    submission_tsv, coverpage_tsv, infotable_tsv = _sample_dataset()
    submissions = parse_submissions(submission_tsv)
    kept = select_latest_13f_hr_submissions(submissions)
    filer_names = parse_coverpages(coverpage_tsv)

    holdings = parse_infotable(infotable_tsv, kept, submissions, filer_names)

    h = holdings[0]
    assert h.filer_name == "BERKSHIRE HATHAWAY INC"
    assert h.filer_cik == "0001067983"
    assert h.period_of_report == date(2026, 6, 30)


def test_parse_infotable_skips_rows_missing_cusip_or_issuer_name() -> None:
    """A real, plausible malformed-row case -- must be skipped, not
    crash the whole batch."""
    submission_tsv, coverpage_tsv, _ = _sample_dataset()
    submissions = parse_submissions(submission_tsv)
    kept = select_latest_13f_hr_submissions(submissions)
    filer_names = parse_coverpages(coverpage_tsv)

    broken_infotable = (
        "ACCESSION_NUMBER\tNAMEOFISSUER\tTITLEOFCLASS\tCUSIP\tVALUE\tSSHPRNAMT\tSSHPRNAMTTYPE\n"
        "0001067983-26-000456\t\tCOM\t\t151000\t905000\tSH\n"
    )
    holdings = parse_infotable(broken_infotable, kept, submissions, filer_names)
    assert holdings == []


def test_parse_infotable_handles_a_put_call_options_row() -> None:
    submission_tsv, coverpage_tsv, _ = _sample_dataset()
    submissions = parse_submissions(submission_tsv)
    kept = select_latest_13f_hr_submissions(submissions)
    filer_names = parse_coverpages(coverpage_tsv)

    options_infotable = (
        "ACCESSION_NUMBER\tNAMEOFISSUER\tTITLEOFCLASS\tCUSIP\tVALUE\tSSHPRNAMT\tSSHPRNAMTTYPE\tPUTCALL\n"
        "0001067983-26-000456\tTESLA INC\tCOM\t88160R101\t5000\t10000\tSH\tCall\n"
    )
    holdings = parse_infotable(options_infotable, kept, submissions, filer_names)
    assert len(holdings) == 1
    assert holdings[0].put_call == "Call"


def test_parse_submissions_returns_empty_dict_for_empty_input() -> None:
    assert parse_submissions("") == {}


def test_select_latest_returns_empty_set_for_empty_input() -> None:
    assert select_latest_13f_hr_submissions({}) == set()
