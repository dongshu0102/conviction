from __future__ import annotations

from src.application.use_cases.manage_universe_theme import (
    AddTickerToThemeUseCase,
    CreateUniverseThemeUseCase,
    DeleteUniverseThemeUseCase,
    GetThemeTickersUseCase,
    GetThemesForTickerUseCase,
    ListUniverseThemesUseCase,
    RemoveTickerFromThemeUseCase,
    ThemeNotFoundError,
    TickerNotIngestedForThemeError,
)
from src.domain.entities.company import Company, Sector
from tests.unit.fakes import FakeCompanyRepository, FakeUniverseThemeRepository


def _company_repo(*tickers: str) -> FakeCompanyRepository:
    repo = FakeCompanyRepository()
    for t in tickers:
        repo.save(Company(ticker=t, name=t, sector=Sector.TECHNOLOGY,
                            industry="X", exchange="NASDAQ", country="US"))
    return repo


def test_create_is_idempotent() -> None:
    theme_repo = FakeUniverseThemeRepository()
    use_case = CreateUniverseThemeUseCase(theme_repo)
    use_case.execute("AI Infrastructure", "GPUs, data centers, power")
    use_case.execute("AI Infrastructure", "a different description")  # no-op, first wins

    theme = theme_repo.get("AI Infrastructure")
    assert theme.description == "GPUs, data centers, power"


def test_add_ticker_requires_theme_to_exist() -> None:
    theme_repo = FakeUniverseThemeRepository()
    company_repo = _company_repo("NVDA")
    use_case = AddTickerToThemeUseCase(theme_repo, company_repo)
    try:
        use_case.execute("Nonexistent Theme", "NVDA")
        raise AssertionError("expected ThemeNotFoundError")
    except ThemeNotFoundError:
        pass


def test_add_ticker_requires_ticker_to_be_ingested() -> None:
    theme_repo = FakeUniverseThemeRepository()
    CreateUniverseThemeUseCase(theme_repo).execute("AI Infrastructure")
    company_repo = FakeCompanyRepository()  # empty — NVDA never ingested
    use_case = AddTickerToThemeUseCase(theme_repo, company_repo)
    try:
        use_case.execute("AI Infrastructure", "NVDA")
        raise AssertionError("expected TickerNotIngestedForThemeError")
    except TickerNotIngestedForThemeError:
        pass


def test_ticker_can_belong_to_multiple_themes() -> None:
    theme_repo = FakeUniverseThemeRepository()
    company_repo = _company_repo("NVDA")
    CreateUniverseThemeUseCase(theme_repo).execute("AI Infrastructure")
    CreateUniverseThemeUseCase(theme_repo).execute("Semiconductors")
    add = AddTickerToThemeUseCase(theme_repo, company_repo)
    add.execute("AI Infrastructure", "nvda")
    add.execute("Semiconductors", "NVDA")

    assert GetThemeTickersUseCase(theme_repo).execute("AI Infrastructure") == ["NVDA"]
    assert GetThemeTickersUseCase(theme_repo).execute("Semiconductors") == ["NVDA"]
    assert set(GetThemesForTickerUseCase(theme_repo).execute("NVDA")) == {
        "AI Infrastructure", "Semiconductors"
    }


def test_remove_from_one_theme_does_not_affect_others() -> None:
    theme_repo = FakeUniverseThemeRepository()
    company_repo = _company_repo("NVDA")
    CreateUniverseThemeUseCase(theme_repo).execute("AI Infrastructure")
    CreateUniverseThemeUseCase(theme_repo).execute("Semiconductors")
    add = AddTickerToThemeUseCase(theme_repo, company_repo)
    add.execute("AI Infrastructure", "NVDA")
    add.execute("Semiconductors", "NVDA")

    removed = RemoveTickerFromThemeUseCase(theme_repo).execute("AI Infrastructure", "NVDA")
    assert removed is True
    assert GetThemeTickersUseCase(theme_repo).execute("AI Infrastructure") == []
    assert GetThemeTickersUseCase(theme_repo).execute("Semiconductors") == ["NVDA"]


def test_remove_nonexistent_membership_returns_false() -> None:
    theme_repo = FakeUniverseThemeRepository()
    CreateUniverseThemeUseCase(theme_repo).execute("China")
    assert RemoveTickerFromThemeUseCase(theme_repo).execute("China", "BABA") is False


def test_get_tickers_requires_theme_to_exist() -> None:
    theme_repo = FakeUniverseThemeRepository()
    try:
        GetThemeTickersUseCase(theme_repo).execute("Nonexistent")
        raise AssertionError("expected ThemeNotFoundError")
    except ThemeNotFoundError:
        pass


def test_empty_theme_is_a_legitimate_state() -> None:
    """Unlike watchlist named lists, an empty theme is representable and
    valid — themes are typically created first, then populated."""
    theme_repo = FakeUniverseThemeRepository()
    CreateUniverseThemeUseCase(theme_repo).execute("Not Yet Populated")
    assert GetThemeTickersUseCase(theme_repo).execute("Not Yet Populated") == []
    summaries = ListUniverseThemesUseCase(theme_repo).execute()
    assert summaries[0].member_count == 0


def test_list_reports_accurate_member_counts() -> None:
    theme_repo = FakeUniverseThemeRepository()
    company_repo = _company_repo("NVDA", "AMD", "BABA")
    CreateUniverseThemeUseCase(theme_repo).execute("AI Infrastructure")
    CreateUniverseThemeUseCase(theme_repo).execute("China")
    add = AddTickerToThemeUseCase(theme_repo, company_repo)
    add.execute("AI Infrastructure", "NVDA")
    add.execute("AI Infrastructure", "AMD")
    add.execute("China", "BABA")

    counts = {s.theme.name: s.member_count for s in ListUniverseThemesUseCase(theme_repo).execute()}
    assert counts == {"AI Infrastructure": 2, "China": 1}


def test_delete_removes_the_theme() -> None:
    theme_repo = FakeUniverseThemeRepository()
    CreateUniverseThemeUseCase(theme_repo).execute("AI Infrastructure")

    DeleteUniverseThemeUseCase(theme_repo).execute("AI Infrastructure")

    assert theme_repo.get("AI Infrastructure") is None


def test_delete_requires_the_theme_to_exist() -> None:
    theme_repo = FakeUniverseThemeRepository()
    try:
        DeleteUniverseThemeUseCase(theme_repo).execute("Nonexistent")
        raise AssertionError("expected ThemeNotFoundError")
    except ThemeNotFoundError:
        pass


def test_delete_also_removes_its_memberships() -> None:
    """The real property that matters: a deleted theme shouldn't leave
    orphaned membership rows behind — those would silently corrupt
    member_count and every downstream ranking for whatever OTHER
    theme (if any) happened to reuse the same name later."""
    theme_repo = FakeUniverseThemeRepository()
    company_repo = _company_repo("NVDA", "AMD")
    CreateUniverseThemeUseCase(theme_repo).execute("AI Infrastructure")
    add = AddTickerToThemeUseCase(theme_repo, company_repo)
    add.execute("AI Infrastructure", "NVDA")
    add.execute("AI Infrastructure", "AMD")

    DeleteUniverseThemeUseCase(theme_repo).execute("AI Infrastructure")

    assert theme_repo.get_tickers("AI Infrastructure") == []


def test_delete_does_not_affect_other_themes() -> None:
    theme_repo = FakeUniverseThemeRepository()
    company_repo = _company_repo("NVDA", "BABA")
    CreateUniverseThemeUseCase(theme_repo).execute("AI Infrastructure")
    CreateUniverseThemeUseCase(theme_repo).execute("China")
    add = AddTickerToThemeUseCase(theme_repo, company_repo)
    add.execute("AI Infrastructure", "NVDA")
    add.execute("China", "BABA")

    DeleteUniverseThemeUseCase(theme_repo).execute("AI Infrastructure")

    assert theme_repo.get("China") is not None
    assert theme_repo.get_tickers("China") == ["BABA"]
