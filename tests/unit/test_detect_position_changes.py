from datetime import date

from src.application.use_cases.detect_position_changes import (
    DetectPositionChangesError,
    DetectPositionChangesUseCase,
)
from src.domain.entities.institutional_holding import InstitutionalHolding
from tests.unit.fakes import FakeInstitutionalHoldingRepository


def _holding(
    filer_name, issuer_name, cusip, shares, value, period,
    accession="0001-26-000001", filer_cik="0001067983",
) -> InstitutionalHolding:
    return InstitutionalHolding(
        accession_number=accession, filer_cik=filer_cik, filer_name=filer_name,
        period_of_report=period, issuer_name=issuer_name, title_of_class="COM",
        cusip=cusip, value_usd=value, shares_or_principal_amount=shares, share_type="SH",
        put_call=None, investment_discretion="SOLE", voting_authority_sole=shares,
        voting_authority_shared=0, voting_authority_none=0,
    )


def test_execute_raises_when_fewer_than_two_quarters_are_ingested() -> None:
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([_holding("Berkshire Hathaway Inc", "APPLE INC", "037833100", 1000, 250_000, date(2026, 3, 31))])
    use_case = DetectPositionChangesUseCase(repo)

    try:
        use_case.execute("Berkshire")
        assert False, "expected DetectPositionChangesError"
    except DetectPositionChangesError:
        pass


def test_execute_raises_when_no_filer_matches() -> None:
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("Berkshire Hathaway Inc", "APPLE INC", "037833100", 1000, 250_000, date(2025, 12, 31)),
        _holding("Berkshire Hathaway Inc", "APPLE INC", "037833100", 1000, 250_000, date(2026, 3, 31)),
    ])
    use_case = DetectPositionChangesUseCase(repo)

    try:
        use_case.execute("Totally Nonexistent Fund")
        assert False, "expected DetectPositionChangesError"
    except DetectPositionChangesError:
        pass


def test_execute_uses_the_two_most_recent_periods() -> None:
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("Berkshire Hathaway Inc", "APPLE INC", "037833100", 1000, 250_000, date(2025, 9, 30)),
        _holding("Berkshire Hathaway Inc", "APPLE INC", "037833100", 2000, 500_000, date(2025, 12, 31)),
        _holding("Berkshire Hathaway Inc", "APPLE INC", "037833100", 3000, 750_000, date(2026, 3, 31)),
    ])
    use_case = DetectPositionChangesUseCase(repo)

    result = use_case.execute("Berkshire")

    assert result.current_period == date(2026, 3, 31)
    assert result.prior_period == date(2025, 12, 31)
    # The 2025-09-30 period should never be consulted at all.
    assert len(result.changes) == 1
    assert result.changes[0].prior_shares == 2000
    assert result.changes[0].current_shares == 3000


def test_execute_correctly_aggregates_multi_line_item_splits_before_diffing() -> None:
    """Regression guard for a real, confirmed 13F pattern: a single
    filing can split the same security across multiple line items
    (different voting-authority categories). Comparing an unaggregated
    line item across quarters would compare an arbitrary fragment of
    the true position, not the real total."""
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        # Prior quarter: 2 line items for the same security, same filing.
        _holding("Berkshire Hathaway Inc", "APPLE INC", "037833100", 100_000, 25_000_000, date(2025, 12, 31), accession="A1"),
        _holding("Berkshire Hathaway Inc", "APPLE INC", "037833100", 50_000, 12_500_000, date(2025, 12, 31), accession="A1"),
        # Current quarter: 3 line items, same security, different split.
        _holding("Berkshire Hathaway Inc", "APPLE INC", "037833100", 80_000, 20_000_000, date(2026, 3, 31), accession="A2"),
        _holding("Berkshire Hathaway Inc", "APPLE INC", "037833100", 40_000, 10_000_000, date(2026, 3, 31), accession="A2"),
        _holding("Berkshire Hathaway Inc", "APPLE INC", "037833100", 30_000, 7_500_000, date(2026, 3, 31), accession="A2"),
    ])
    use_case = DetectPositionChangesUseCase(repo)

    result = use_case.execute("Berkshire")

    # Prior total: 100k + 50k = 150k. Current total: 80k + 40k + 30k = 150k.
    # Same TRUE total despite different line-item splits -- must be no change.
    assert result.changes == ()


def test_execute_detects_a_real_new_position() -> None:
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("Berkshire Hathaway Inc", "APPLE INC", "037833100", 1000, 250_000, date(2025, 12, 31)),
        _holding("Berkshire Hathaway Inc", "APPLE INC", "037833100", 1000, 250_000, date(2026, 3, 31)),
        _holding("Berkshire Hathaway Inc", "CHEVRON CORP", "166764100", 500, 75_000, date(2026, 3, 31)),
    ])
    use_case = DetectPositionChangesUseCase(repo)

    result = use_case.execute("Berkshire")

    new_changes = [c for c in result.changes if c.change_type == "new"]
    assert len(new_changes) == 1
    assert new_changes[0].issuer_name == "CHEVRON CORP"


def test_execute_flags_when_the_filer_has_no_prior_period_data_at_all() -> None:
    """Regression guard for a real, confirmed scenario found in
    production: a filer (a newly-registered manager, high SEC CIK)
    with data ONLY in the current quarter, zero rows in the prior one.
    Every position correctly renders as "new" either way, but that's
    a fundamentally different, less alarming story than an established
    manager buying their entire book in one quarter -- callers need
    this flag to tell the two apart honestly."""
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        # An unrelated, existing filer so >=2 periods genuinely exist.
        _holding("Some Other Fund", "MICROSOFT CORP", "594918104", 1000, 500_000, date(2025, 12, 31), filer_cik="0001111111"),
        _holding("Some Other Fund", "MICROSOFT CORP", "594918104", 1000, 500_000, date(2026, 3, 31), filer_cik="0001111111"),
        # The newly-registered filer: current quarter only, a genuinely different CIK.
        _holding("Vanguard Capital Management LLC", "APPLE INC", "037833100", 5000, 1_250_000, date(2026, 3, 31), filer_cik="0002100119"),
        _holding("Vanguard Capital Management LLC", "MICROSOFT CORP", "594918104", 3000, 1_500_000, date(2026, 3, 31), filer_cik="0002100119"),
    ])
    use_case = DetectPositionChangesUseCase(repo)

    result = use_case.execute("Vanguard Capital Management")

    assert result.filer_had_no_prior_period_data is True
    assert len(result.changes) == 2
    assert all(c.change_type == "new" for c in result.changes)


def test_execute_does_not_flag_a_filer_with_genuine_prior_period_data() -> None:
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("Berkshire Hathaway Inc", "APPLE INC", "037833100", 1000, 250_000, date(2025, 12, 31)),
        _holding("Berkshire Hathaway Inc", "APPLE INC", "037833100", 1000, 250_000, date(2026, 3, 31)),
    ])
    use_case = DetectPositionChangesUseCase(repo)

    result = use_case.execute("Berkshire")

    assert result.filer_had_no_prior_period_data is False


def test_execute_resolves_filer_by_total_value_not_a_single_largest_row() -> None:
    """The same real, confirmed production bug fixed in
    GetInstitutionalPortfolioUseCase and GetInstitutionalHoldersUseCase,
    guarded here too since this use case resolves filers independently."""
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        # Prior period, needed so at least 2 quarters exist at all.
        _holding("Vanguard Capital Management LLC", "OLD POSITION", "037833100", 1000, 100_000_000, date(2025, 12, 31)),
        # Current period -- the real target: several smaller positions, large total.
        _holding("Vanguard Capital Management LLC", "POSITION A", "037833100", 1000, 500_000_000, date(2026, 3, 31)),
        _holding("Vanguard Capital Management LLC", "POSITION B", "594918104", 1000, 500_000_000, date(2026, 3, 31)),
        # An unrelated decoy filer with one huge single row that would
        # win a naive "largest single row" sort, despite a smaller own total.
        _holding("Vanguard Decoy Advisors LLC", "POSITION X", "025816109", 1000, 900_000_000, date(2026, 3, 31), filer_cik="0009999999"),
    ])
    use_case = DetectPositionChangesUseCase(repo)

    result = use_case.execute("Vanguard")

    assert result.filer_name == "Vanguard Capital Management LLC"
