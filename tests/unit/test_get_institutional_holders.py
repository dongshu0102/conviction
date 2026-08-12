from datetime import date

from src.application.use_cases.get_institutional_holders import (
    GetInstitutionalHoldersError,
    GetInstitutionalHoldersUseCase,
)
from src.domain.entities.institutional_holding import InstitutionalHolding
from tests.unit.fakes import FakeInstitutionalHoldingRepository


def _holding(
    filer_name, issuer_name, value_usd, period=date(2026, 3, 31),
    cusip="037833100",
) -> InstitutionalHolding:
    return InstitutionalHolding(
        accession_number="0001-26-000001", filer_cik="0001067983", filer_name=filer_name,
        period_of_report=period, issuer_name=issuer_name, title_of_class="COM",
        cusip=cusip, value_usd=value_usd, shares_or_principal_amount=1000, share_type="SH",
        put_call=None, investment_discretion="SOLE", voting_authority_sole=1000,
        voting_authority_shared=0, voting_authority_none=0,
    )


def test_execute_raises_a_clear_error_when_nothing_has_been_ingested() -> None:
    use_case = GetInstitutionalHoldersUseCase(FakeInstitutionalHoldingRepository())

    try:
        use_case.execute("Apple")
        assert False, "expected GetInstitutionalHoldersError"
    except GetInstitutionalHoldersError:
        pass


def test_execute_finds_holders_by_a_partial_case_insensitive_issuer_name() -> None:
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("BERKSHIRE HATHAWAY INC", "APPLE INC", 500_000_000, cusip="037833100"),
        _holding("VANGUARD GROUP INC", "Apple, Inc.", 900_000_000, cusip="037833100"),
        _holding("SOME FUND", "MICROSOFT CORP", 300_000_000, cusip="594918104"),
    ])
    use_case = GetInstitutionalHoldersUseCase(repo)

    result = use_case.execute("apple")

    assert len(result.holders) == 2
    assert all("apple" in h.issuer_name.lower() for h in result.holders)


def test_execute_sorts_holders_by_value_descending() -> None:
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("SMALL FUND", "APPLE INC", 100_000_000),
        _holding("BIG FUND", "APPLE INC", 900_000_000),
        _holding("MID FUND", "APPLE INC", 500_000_000),
    ])
    use_case = GetInstitutionalHoldersUseCase(repo)

    result = use_case.execute("Apple")

    values = [h.value_usd for h in result.holders]
    assert values == sorted(values, reverse=True)


def test_execute_uses_the_latest_period_automatically() -> None:
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("OLD FUND", "APPLE INC", 100_000_000, period=date(2025, 12, 31)),
        _holding("NEW FUND", "APPLE INC", 200_000_000, period=date(2026, 3, 31)),
    ])
    use_case = GetInstitutionalHoldersUseCase(repo)

    result = use_case.execute("Apple")

    assert result.period_of_report == date(2026, 3, 31)
    assert len(result.holders) == 1
    assert result.holders[0].filer_name == "NEW FUND"


def test_execute_never_blends_holders_from_multiple_different_securities() -> None:
    """Regression guard for a real, confirmed production bug, the
    sibling of the one already found and fixed in
    GetInstitutionalPortfolioUseCase: searching "American" returned a
    single "who holds X" response silently blending together holders
    of three genuinely different, unrelated securities that all
    happen to share the "American" name prefix (American Electric
    Power, American Express, and American Tower -- confirmed directly
    against real production data). Every holder returned must be
    holding exactly ONE resolved security, never several."""
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("BIG FUND", "AMERICAN EXPRESS CO", 45_000_000_000, cusip="025816109"),
        _holding("SMALL FUND", "AMERICAN EXPRESS CO", 5_000_000_000, cusip="025816109"),
        # Genuinely different, unrelated securities that also match
        # the "american" substring.
        _holding("SOME FUND", "AMERICAN ELEC PWR CO INC", 3_000_000_000, cusip="025537101"),
        _holding("OTHER FUND", "AMERICAN TOWER CORP", 2_000_000_000, cusip="03027X100"),
    ])
    use_case = GetInstitutionalHoldersUseCase(repo)

    result = use_case.execute("American", limit=200)

    issuer_names = {h.issuer_name for h in result.holders}
    assert len(issuer_names) == 1, f"expected exactly one issuer, got: {issuer_names}"
    assert issuer_names == {"AMERICAN EXPRESS CO"}
    assert result.issuer_name == "AMERICAN EXPRESS CO"
