from datetime import date

from src.application.use_cases.detect_position_changes import (
    DetectPositionChangesError,
    DetectPositionChangesUseCase,
)
from src.domain.entities.institutional_holding import InstitutionalHolding
from tests.unit.fakes import FakeFreshnessFallbackProvider, FakeInstitutionalHoldingRepository


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


def test_execute_uses_purely_local_data_when_it_is_already_as_fresh_as_expected() -> None:
    """as_of is deliberately fixed/injected here, not real 'today' --
    this test must stay correct regardless of when it actually runs."""
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("Berkshire Hathaway Inc", "OLD POSITION", "037833100", 1000, 100_000_000, date(2025, 12, 31)),
        _holding("Berkshire Hathaway Inc", "NEW POSITION", "037833100", 1000, 200_000_000, date(2026, 3, 31)),
    ])
    provider = FakeFreshnessFallbackProvider()
    use_case = DetectPositionChangesUseCase(repo, provider)

    result = use_case.execute("Berkshire", as_of=date(2026, 8, 13))

    assert result.source == "sec_bulk"
    assert result.current_period == date(2026, 3, 31)
    assert result.prior_period == date(2025, 12, 31)
    assert provider.calls == [], "FMP should never be called when local data is already fresh enough"


def test_execute_falls_back_to_fmp_for_the_current_period_but_keeps_local_prior_period() -> None:
    """The core, distinguishing behavior of this fallback: only the
    CURRENT period ever comes from FMP -- the prior period always
    comes from local data, since FMP's per-filer endpoint has no
    history, only whichever single quarter is requested."""
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("Berkshire Hathaway Inc", "OLD POSITION", "037833100", 1000, 100_000_000, date(2025, 12, 31)),
        _holding("Berkshire Hathaway Inc", "STILL HELD Q1", "037833100", 1000, 200_000_000, date(2026, 3, 31)),
    ])
    fresher_holding = InstitutionalHolding(
        accession_number="", filer_cik="0001067983", filer_name="Berkshire Hathaway Inc",
        period_of_report=date(2026, 6, 30), issuer_name="CHEVRON CORPORATION", title_of_class="COM",
        cusip="166764100", value_usd=13_986_141_890, shares_or_principal_amount=84_375_856,
        share_type="SH", put_call=None, investment_discretion="SOLE",
        voting_authority_sole=0, voting_authority_shared=0, voting_authority_none=0,
    )
    provider = FakeFreshnessFallbackProvider(
        holdings_by_cik_quarter={("0001067983", 2026, 2): [fresher_holding]},
    )
    use_case = DetectPositionChangesUseCase(repo, provider)

    result = use_case.execute("Berkshire", as_of=date(2026, 8, 14))

    assert result.source == "fmp_live"
    assert result.current_period == date(2026, 6, 30)
    assert result.prior_period == date(2026, 3, 31), "prior period must come from local data, not FMP"
    assert provider.calls == [("0001067983", 2026, 2, "Berkshire Hathaway Inc")]
    # The Q1 position, genuinely not present in the fresher FMP quarter, should show as closed.
    change_types = {c.cusip: c.change_type for c in result.changes}
    assert change_types["037833100"] == "closed"
    assert change_types["166764100"] == "new"


def test_execute_aggregates_multi_line_item_fmp_holdings_before_comparing() -> None:
    """Real, confirmed scenario: a single filing can legitimately split
    the same security across multiple line items. If the fallback
    compared raw, un-aggregated FMP rows, this would look like several
    separate, tiny positions instead of one true, larger one."""
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("Berkshire Hathaway Inc", "APPLE INC", "037833100", 100_000, 10_000_000, date(2026, 3, 31)),
    ])
    fresher_split_rows = [
        InstitutionalHolding(
            accession_number="", filer_cik="0001067983", filer_name="Berkshire Hathaway Inc",
            period_of_report=date(2026, 6, 30), issuer_name="APPLE INC", title_of_class="COM",
            cusip="037833100", value_usd=8_000_000, shares_or_principal_amount=80_000,
            share_type="SH", put_call=None, investment_discretion="SOLE",
            voting_authority_sole=0, voting_authority_shared=0, voting_authority_none=0,
        ),
        InstitutionalHolding(
            accession_number="", filer_cik="0001067983", filer_name="Berkshire Hathaway Inc",
            period_of_report=date(2026, 6, 30), issuer_name="APPLE INC", title_of_class="COM",
            cusip="037833100", value_usd=4_000_000, shares_or_principal_amount=40_000,
            share_type="SH", put_call=None, investment_discretion="SOLE",
            voting_authority_sole=0, voting_authority_shared=0, voting_authority_none=0,
        ),
    ]
    provider = FakeFreshnessFallbackProvider(
        holdings_by_cik_quarter={("0001067983", 2026, 2): fresher_split_rows},
    )
    use_case = DetectPositionChangesUseCase(repo, provider)

    result = use_case.execute("Berkshire", as_of=date(2026, 8, 14))

    assert len(result.changes) == 1  # the two split rows must be aggregated into one comparison
    change = result.changes[0]
    assert change.cusip == "037833100"
    assert change.current_shares == 120_000  # 80,000 + 40,000, correctly summed
    assert change.current_value_usd == 12_000_000  # 8M + 4M, correctly summed


def test_execute_falls_back_to_purely_local_comparison_when_fmp_has_nothing_for_this_filer_yet() -> None:
    """A real, honest degradation -- the local pipeline is stale, but
    this specific filer genuinely hasn't filed for the fresher quarter
    on FMP either yet. Must fall back to the purely-local comparison,
    not silently show nothing."""
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("Berkshire Hathaway Inc", "OLD POSITION", "037833100", 1000, 100_000_000, date(2025, 12, 31)),
        _holding("Berkshire Hathaway Inc", "NEW POSITION", "037833100", 1000, 200_000_000, date(2026, 3, 31)),
    ])
    provider = FakeFreshnessFallbackProvider(holdings_by_cik_quarter={})  # empty for everyone
    use_case = DetectPositionChangesUseCase(repo, provider)

    result = use_case.execute("Berkshire", as_of=date(2026, 8, 14))

    assert result.source == "sec_bulk"
    assert result.current_period == date(2026, 3, 31)
    assert result.prior_period == date(2025, 12, 31)


def test_execute_falls_back_to_purely_local_comparison_when_fmp_raises_an_error() -> None:
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("Berkshire Hathaway Inc", "OLD POSITION", "037833100", 1000, 100_000_000, date(2025, 12, 31)),
        _holding("Berkshire Hathaway Inc", "NEW POSITION", "037833100", 1000, 200_000_000, date(2026, 3, 31)),
    ])
    provider = FakeFreshnessFallbackProvider(raise_error=ConnectionError("network is down"))
    use_case = DetectPositionChangesUseCase(repo, provider)

    result = use_case.execute("Berkshire", as_of=date(2026, 8, 14))

    assert result.source == "sec_bulk"


def test_execute_succeeds_via_fmp_fallback_with_only_a_single_local_period_ingested() -> None:
    """A genuine improvement, not just parity: the original, purely
    local logic required 2 already-ingested quarters and would have
    raised an error with only 1. With the fallback, a single local
    quarter is enough to serve as the prior period, with FMP supplying
    the fresher current period live."""
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("Berkshire Hathaway Inc", "ONLY POSITION", "037833100", 1000, 100_000_000, date(2026, 3, 31)),
    ])
    fresher_holding = InstitutionalHolding(
        accession_number="", filer_cik="0001067983", filer_name="Berkshire Hathaway Inc",
        period_of_report=date(2026, 6, 30), issuer_name="CHEVRON CORPORATION", title_of_class="COM",
        cusip="166764100", value_usd=1_000_000, shares_or_principal_amount=1000,
        share_type="SH", put_call=None, investment_discretion="SOLE",
        voting_authority_sole=0, voting_authority_shared=0, voting_authority_none=0,
    )
    provider = FakeFreshnessFallbackProvider(
        holdings_by_cik_quarter={("0001067983", 2026, 2): [fresher_holding]},
    )
    use_case = DetectPositionChangesUseCase(repo, provider)

    result = use_case.execute("Berkshire", as_of=date(2026, 8, 14))

    assert result.source == "fmp_live"
    assert result.prior_period == date(2026, 3, 31)
    assert result.current_period == date(2026, 6, 30)


def test_execute_raises_with_only_a_single_local_period_and_no_fmp_fallback_available() -> None:
    """Matches the original behavior exactly when no provider is
    configured at all -- the same real error as before the fallback
    ever existed."""
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("Berkshire Hathaway Inc", "ONLY POSITION", "037833100", 1000, 100_000_000, date(2026, 3, 31)),
    ])
    use_case = DetectPositionChangesUseCase(repo)  # no provider at all

    try:
        use_case.execute("Berkshire", as_of=date(2026, 8, 14))
        assert False, "expected DetectPositionChangesError"
    except DetectPositionChangesError as exc:
        assert "at least 2" in str(exc)


def test_execute_with_no_provider_configured_uses_purely_local_data_even_when_stale() -> None:
    """Matches every existing caller of this use case before tonight."""
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("Berkshire Hathaway Inc", "OLD POSITION", "037833100", 1000, 100_000_000, date(2025, 12, 31)),
        _holding("Berkshire Hathaway Inc", "NEW POSITION", "037833100", 1000, 200_000_000, date(2026, 3, 31)),
    ])
    use_case = DetectPositionChangesUseCase(repo)  # no provider passed at all

    result = use_case.execute("Berkshire", as_of=date(2026, 8, 14))

    assert result.source == "sec_bulk"
