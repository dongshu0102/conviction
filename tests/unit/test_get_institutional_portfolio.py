from datetime import date

from src.application.use_cases.get_institutional_portfolio import (
    GetInstitutionalPortfolioError,
    GetInstitutionalPortfolioUseCase,
)
from src.domain.entities.institutional_holding import InstitutionalHolding
from tests.unit.fakes import FakeInstitutionalHoldingRepository, FakeFreshnessFallbackProvider


def _holding(
    filer_name, issuer_name, value_usd, period=date(2026, 3, 31),
    filer_cik="0001067983",
) -> InstitutionalHolding:
    return InstitutionalHolding(
        accession_number="0001-26-000001", filer_cik=filer_cik, filer_name=filer_name,
        period_of_report=period, issuer_name=issuer_name, title_of_class="COM",
        cusip="037833100", value_usd=value_usd, shares_or_principal_amount=1000, share_type="SH",
        put_call=None, investment_discretion="SOLE", voting_authority_sole=1000,
        voting_authority_shared=0, voting_authority_none=0,
    )


def test_execute_raises_a_clear_error_when_nothing_has_been_ingested() -> None:
    use_case = GetInstitutionalPortfolioUseCase(FakeInstitutionalHoldingRepository())

    try:
        use_case.execute("Berkshire")
        assert False, "expected GetInstitutionalPortfolioError"
    except GetInstitutionalPortfolioError:
        pass


def test_execute_finds_a_filers_portfolio_by_partial_case_insensitive_name() -> None:
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("Berkshire Hathaway Inc", "APPLE INC", 500_000_000, filer_cik="0001067983"),
        _holding("Berkshire Hathaway Inc", "BANK OF AMERICA CORP", 300_000_000, filer_cik="0001067983"),
        _holding("Vanguard Group Inc", "MICROSOFT CORP", 900_000_000, filer_cik="0000102909"),
    ])
    use_case = GetInstitutionalPortfolioUseCase(repo)

    result = use_case.execute("berkshire")

    assert len(result.holdings) == 2
    assert all("berkshire" in h.filer_name.lower() for h in result.holdings)


def test_execute_sorts_holdings_by_value_descending() -> None:
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("Berkshire Hathaway Inc", "SMALL POSITION", 50_000_000),
        _holding("Berkshire Hathaway Inc", "BIG POSITION", 900_000_000),
        _holding("Berkshire Hathaway Inc", "MID POSITION", 400_000_000),
    ])
    use_case = GetInstitutionalPortfolioUseCase(repo)

    result = use_case.execute("Berkshire")

    values = [h.value_usd for h in result.holdings]
    assert values == sorted(values, reverse=True)


def test_execute_uses_the_latest_period_automatically() -> None:
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("Berkshire Hathaway Inc", "OLD POSITION", 100_000_000, period=date(2025, 12, 31)),
        _holding("Berkshire Hathaway Inc", "NEW POSITION", 200_000_000, period=date(2026, 3, 31)),
    ])
    use_case = GetInstitutionalPortfolioUseCase(repo)

    result = use_case.execute("Berkshire")

    assert result.period_of_report == date(2026, 3, 31)
    assert len(result.holdings) == 1
    assert result.holdings[0].issuer_name == "NEW POSITION"


def test_execute_never_blends_holdings_from_multiple_different_filers() -> None:
    """Regression guard for a real, confirmed production bug: searching
    "Vanguard" returned a single "portfolio" silently blending together
    holdings from three genuinely different, unrelated SEC filer
    entities that all happen to share the "Vanguard" name prefix
    (Vanguard Capital Management LLC, Vanguard Portfolio Management
    LLC, and Vanguard Advisers Inc -- confirmed directly against real
    production data). Every holding returned must come from exactly
    ONE resolved filer's CIK, never several."""
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("Vanguard Capital Management LLC", "NVIDIA CORP", 268_000_000_000, filer_cik="0002100119"),
        _holding("Vanguard Capital Management LLC", "APPLE INC", 242_000_000_000, filer_cik="0002100119"),
        # A smaller, but genuinely different, unrelated filer that also
        # matches the "vanguard" substring.
        _holding("Vanguard Portfolio Management LLC", "MICROSOFT CORP", 27_000_000_000, filer_cik="0002100121"),
        _holding("Vanguard Advisers Inc", "TESLA INC", 25_000_000_000, filer_cik="0000947529"),
    ])
    use_case = GetInstitutionalPortfolioUseCase(repo)

    result = use_case.execute("Vanguard", limit=200)

    filer_names = {h.filer_name for h in result.holdings}
    assert len(filer_names) == 1, f"expected exactly one filer, got: {filer_names}"
    assert filer_names == {"Vanguard Capital Management LLC"}
    assert result.filer_name == "Vanguard Capital Management LLC"


def test_execute_uses_local_data_when_it_is_already_as_fresh_as_expected() -> None:
    """as_of is deliberately fixed/injected here, not real 'today' --
    this test must stay correct regardless of when it actually runs."""
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("Berkshire Hathaway Inc", "APPLE INC", 500_000_000, period=date(2026, 3, 31)),
    ])
    provider = FakeFreshnessFallbackProvider()
    use_case = GetInstitutionalPortfolioUseCase(repo, provider)

    # as_of the day BEFORE the Q2 2026 deadline -- Q1 2026 (what's
    # locally stored) is still the expected-latest quarter.
    result = use_case.execute("Berkshire", as_of=date(2026, 8, 13))

    assert result.source == "sec_bulk"
    assert result.period_of_report == date(2026, 3, 31)
    assert provider.calls == [], "FMP should never be called when local data is already fresh enough"


def test_execute_falls_back_to_fmp_when_local_data_is_stale_and_fmp_has_fresher_data() -> None:
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("Berkshire Hathaway Inc", "OLD STALE POSITION", 500_000_000, period=date(2026, 3, 31)),
    ])
    fresher_holding = _holding(
        "Berkshire Hathaway Inc", "CHEVRON CORPORATION", 13_986_141_890, period=date(2026, 6, 30),
    )
    provider = FakeFreshnessFallbackProvider(
        holdings_by_cik_quarter={("0001067983", 2026, 2): [fresher_holding]},
    )
    use_case = GetInstitutionalPortfolioUseCase(repo, provider)

    # as_of ON the Q2 2026 deadline itself -- Q2 now counts as expected-complete.
    result = use_case.execute("Berkshire", as_of=date(2026, 8, 14))

    assert result.source == "fmp_live"
    assert result.period_of_report == date(2026, 6, 30)
    assert len(result.holdings) == 1
    assert result.holdings[0].issuer_name == "CHEVRON CORPORATION"
    assert provider.calls == [("0001067983", 2026, 2, "Berkshire Hathaway Inc")]


def test_execute_falls_back_to_local_data_when_fmp_has_nothing_for_this_filer_yet() -> None:
    """A real, honest degradation -- the local pipeline is stale, but
    this specific filer genuinely hasn't filed for the fresher
    quarter on FMP either yet. Must not silently show nothing."""
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("Berkshire Hathaway Inc", "OLD POSITION", 500_000_000, period=date(2026, 3, 31)),
    ])
    provider = FakeFreshnessFallbackProvider(holdings_by_cik_quarter={})  # empty for everyone
    use_case = GetInstitutionalPortfolioUseCase(repo, provider)

    result = use_case.execute("Berkshire", as_of=date(2026, 8, 14))

    assert result.source == "sec_bulk"
    assert result.period_of_report == date(2026, 3, 31)
    assert result.holdings[0].issuer_name == "OLD POSITION"


def test_execute_falls_back_to_local_data_when_fmp_raises_an_error() -> None:
    """A live-data hiccup must never take down a feature the free,
    local pipeline already serves correctly on its own."""
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("Berkshire Hathaway Inc", "OLD POSITION", 500_000_000, period=date(2026, 3, 31)),
    ])
    provider = FakeFreshnessFallbackProvider(raise_error=ConnectionError("network is down"))
    use_case = GetInstitutionalPortfolioUseCase(repo, provider)

    result = use_case.execute("Berkshire", as_of=date(2026, 8, 14))

    assert result.source == "sec_bulk"
    assert result.period_of_report == date(2026, 3, 31)


def test_execute_with_no_provider_configured_uses_local_data_even_when_stale() -> None:
    """The most common real deployment case until this is fully wired
    in: provider=None entirely, matching every existing caller of this
    use case before tonight -- must behave exactly as it always has."""
    repo = FakeInstitutionalHoldingRepository()
    repo.bulk_save([
        _holding("Berkshire Hathaway Inc", "OLD POSITION", 500_000_000, period=date(2026, 3, 31)),
    ])
    use_case = GetInstitutionalPortfolioUseCase(repo)  # no provider passed at all

    result = use_case.execute("Berkshire", as_of=date(2026, 8, 14))

    assert result.source == "sec_bulk"
    assert result.period_of_report == date(2026, 3, 31)
