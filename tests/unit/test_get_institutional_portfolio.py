from datetime import date

from src.application.use_cases.get_institutional_portfolio import (
    GetInstitutionalPortfolioError,
    GetInstitutionalPortfolioUseCase,
)
from src.domain.entities.institutional_holding import InstitutionalHolding
from tests.unit.fakes import FakeInstitutionalHoldingRepository


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
