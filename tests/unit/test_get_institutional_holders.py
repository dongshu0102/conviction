from datetime import date

from src.application.use_cases.get_institutional_holders import (
    GetInstitutionalHoldersError,
    GetInstitutionalHoldersUseCase,
)
from src.application.use_cases.resolve_cusip_ticker import ResolveCusipTickerUseCase
from src.domain.entities.cusip_ticker_mapping import CusipTickerMapping
from src.domain.entities.institutional_holding import InstitutionalHolding
from src.domain.services.cusip_ticker_resolution import CusipSearchResult
from tests.unit.fakes import (
    FakeCusipSearchProvider,
    FakeCusipTickerMapRepository,
    FakeFreshnessFallbackProvider,
    FakeInstitutionalHoldingRepository,
)


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


def test_execute_resolves_by_total_value_not_a_single_largest_row() -> None:
    """Regression guard for a real, confirmed production bug: searching
    "Circle" resolved to "ADVISORS INNER CIRCLE FD III" (an unrelated
    mutual fund with only 2 holders but one very large individual
    position) instead of the real Circle Internet Group (3 holders,
    smaller individual positions, but a much larger TOTAL across all
    of them) -- confirmed directly against real production data.
    Ordering by a single row's value can never substitute for ordering
    by each candidate's own summed total."""
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        # The real target: many smaller holders, large total ($1.4B).
        _holding("FUND A", "CIRCLE INTERNET GROUP INC", 500_000_000, cusip="172573107"),
        _holding("FUND B", "CIRCLE INTERNET GROUP INC", 500_000_000, cusip="172573107"),
        _holding("FUND C", "CIRCLE INTERNET GROUP INC", 400_000_000, cusip="172573107"),
        # The unrelated decoy: fewer holders, but one huge single row
        # ($900M) that would win a naive "largest single row" sort,
        # despite its own total ($950M) being smaller than the real
        # target's total ($1.4B).
        _holding("DECOY FUND A", "ADVISORS INNER CIRCLE FD III", 900_000_000, cusip="00775Y322"),
        _holding("DECOY FUND B", "ADVISORS INNER CIRCLE FD III", 50_000_000, cusip="00775Y322"),
    ])
    use_case = GetInstitutionalHoldersUseCase(repo)

    result = use_case.execute("Circle", limit=200)

    assert result.issuer_name == "CIRCLE INTERNET GROUP INC"
    assert len(result.holders) == 3
    assert {h.filer_name for h in result.holders} == {"FUND A", "FUND B", "FUND C"}


def test_execute_picks_the_most_common_name_variant_for_display() -> None:
    """The resolved issuer_name shown to the user should be the most
    commonly-used real variant, not an arbitrary or rare one, given the
    same real security's name is recorded inconsistently across
    different filers (confirmed directly: Roblox alone had 20+ raw
    text variants for the same real CUSIP in production data)."""
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("FUND A", "ROBLOX CORP", 100_000_000, cusip="771049103"),
        _holding("FUND B", "ROBLOX CORP", 100_000_000, cusip="771049103"),
        _holding("FUND C", "ROBLOX CORP", 100_000_000, cusip="771049103"),
        _holding("FUND D", "Roblox Corp -Class A", 100_000_000, cusip="771049103"),
    ])
    use_case = GetInstitutionalHoldersUseCase(repo)

    result = use_case.execute("Roblox")

    assert result.issuer_name == "ROBLOX CORP"


def test_execute_uses_local_data_when_it_is_already_as_fresh_as_expected() -> None:
    """as_of is deliberately fixed/injected here, not real 'today' --
    this test must stay correct regardless of when it actually runs."""
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([_holding("BERKSHIRE HATHAWAY INC", "APPLE INC", 500_000_000, period=date(2026, 3, 31))])
    provider = FakeFreshnessFallbackProvider()
    ticker_repo = FakeCusipTickerMapRepository()
    ticker_resolver = ResolveCusipTickerUseCase(ticker_repo, FakeCusipSearchProvider())
    use_case = GetInstitutionalHoldersUseCase(repo, provider, ticker_resolver)

    result = use_case.execute("Apple", as_of=date(2026, 8, 13))

    assert result.source == "sec_bulk"
    assert provider.symbol_calls == [], "FMP should never be called when local data is already fresh enough"


def test_execute_falls_back_to_fmp_when_local_data_is_stale_and_fmp_has_fresher_data() -> None:
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([_holding("SOME FUND", "ROBLOX CORP", 500_000_000, period=date(2026, 3, 31), cusip="771049103")])

    fresher_holder = InstitutionalHolding(
        accession_number="", filer_cik="0000315066", filer_name="FMR LLC",
        period_of_report=date(2026, 6, 30), issuer_name="ROBLOX CORP", title_of_class="CL A",
        cusip="771049103", value_usd=4_335_375_505, shares_or_principal_amount=79_723_713,
        share_type="SH", put_call=None, investment_discretion="DFND",
        voting_authority_sole=0, voting_authority_shared=0, voting_authority_none=0,
    )
    provider = FakeFreshnessFallbackProvider(
        holders_by_symbol_quarter={("RBLX", 2026, 2): [fresher_holder]},
    )
    ticker_repo = FakeCusipTickerMapRepository()
    ticker_search = FakeCusipSearchProvider(results_by_cusip={
        "771049103": [CusipSearchResult(symbol="RBLX", company_name="Roblox Corporation", market_cap=1)],
    })
    ticker_resolver = ResolveCusipTickerUseCase(ticker_repo, ticker_search)
    use_case = GetInstitutionalHoldersUseCase(repo, provider, ticker_resolver)

    result = use_case.execute("Roblox", as_of=date(2026, 8, 14))

    assert result.source == "fmp_live"
    assert result.period_of_report == date(2026, 6, 30)
    assert len(result.holders) == 1
    assert result.holders[0].filer_name == "FMR LLC"
    assert provider.symbol_calls == [("RBLX", 2026, 2, 20)]


def test_execute_falls_back_to_local_data_when_no_us_ticker_can_be_resolved() -> None:
    """A real, honest degradation -- some CUSIPs genuinely have no
    resolvable US ticker (see cusip_ticker_resolution's own docstring),
    so this must fall back rather than crash or show nothing."""
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([_holding("SOME FUND", "FOREIGN CO", 500_000_000, period=date(2026, 3, 31), cusip="999999999")])
    provider = FakeFreshnessFallbackProvider()
    ticker_repo = FakeCusipTickerMapRepository()
    ticker_search = FakeCusipSearchProvider(results_by_cusip={
        "999999999": [CusipSearchResult(symbol="XYZ.DE", company_name="Foreign Co", market_cap=1)],
    })
    ticker_resolver = ResolveCusipTickerUseCase(ticker_repo, ticker_search)
    use_case = GetInstitutionalHoldersUseCase(repo, provider, ticker_resolver)

    result = use_case.execute("Foreign", as_of=date(2026, 8, 14))

    assert result.source == "sec_bulk"
    assert provider.symbol_calls == [], "should never call FMP's symbol endpoint with no resolvable ticker"


def test_execute_falls_back_to_local_data_when_ticker_resolution_errors() -> None:
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([_holding("SOME FUND", "ROBLOX CORP", 500_000_000, period=date(2026, 3, 31), cusip="771049103")])
    provider = FakeFreshnessFallbackProvider()
    ticker_repo = FakeCusipTickerMapRepository()

    class RaisingSearchProvider:
        def search_cusip(self, cusip):
            raise ConnectionError("network is down")

    ticker_resolver = ResolveCusipTickerUseCase(ticker_repo, RaisingSearchProvider())
    use_case = GetInstitutionalHoldersUseCase(repo, provider, ticker_resolver)

    result = use_case.execute("Roblox", as_of=date(2026, 8, 14))

    assert result.source == "sec_bulk"


def test_execute_with_no_provider_or_resolver_configured_uses_local_data_even_when_stale() -> None:
    """Matches every existing caller of this use case before tonight."""
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([_holding("SOME FUND", "APPLE INC", 500_000_000, period=date(2026, 3, 31))])
    use_case = GetInstitutionalHoldersUseCase(repo)

    result = use_case.execute("Apple", as_of=date(2026, 8, 14))

    assert result.source == "sec_bulk"
