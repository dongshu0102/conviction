from __future__ import annotations

from src.application.use_cases.manage_watchlist import (
    AddToWatchlistUseCase,
    GetWatchlistUseCase,
    RemoveFromWatchlistUseCase,
    TickerNotIngestedError,
)
from src.domain.entities.company import Company, Sector
from tests.unit.fakes import FakeCompanyRepository, FakeWatchlistRepository


def _company_repo_with_aapl() -> FakeCompanyRepository:
    repo = FakeCompanyRepository()
    repo.save(
        Company(
            ticker="AAPL", name="Apple Inc.", sector=Sector.TECHNOLOGY,
            industry="Consumer Electronics", exchange="NASDAQ", country="US",
        )
    )
    return repo


def test_cannot_add_ticker_that_has_never_been_ingested() -> None:
    add_use_case = AddToWatchlistUseCase(FakeWatchlistRepository(), FakeCompanyRepository())
    try:
        add_use_case.execute("alice", "NOTINGESTED")
        raise AssertionError("expected TickerNotIngestedError")
    except TickerNotIngestedError:
        pass


def test_add_and_list_roundtrip() -> None:
    watchlist_repo = FakeWatchlistRepository()
    company_repo = _company_repo_with_aapl()
    add_use_case = AddToWatchlistUseCase(watchlist_repo, company_repo)
    list_use_case = GetWatchlistUseCase(watchlist_repo)

    add_use_case.execute("alice", "aapl", notes="long-term hold")

    items = list_use_case.execute("alice")
    assert len(items) == 1
    assert items[0].ticker == "AAPL"  # normalized
    assert items[0].notes == "long-term hold"


def test_adding_same_ticker_twice_does_not_duplicate() -> None:
    watchlist_repo = FakeWatchlistRepository()
    company_repo = _company_repo_with_aapl()
    add_use_case = AddToWatchlistUseCase(watchlist_repo, company_repo)
    list_use_case = GetWatchlistUseCase(watchlist_repo)

    add_use_case.execute("alice", "AAPL", notes="first note")
    add_use_case.execute("alice", "AAPL", notes="updated note")

    items = list_use_case.execute("alice")
    assert len(items) == 1
    assert items[0].notes == "updated note"


def test_watchlists_are_isolated_per_user() -> None:
    watchlist_repo = FakeWatchlistRepository()
    company_repo = _company_repo_with_aapl()
    add_use_case = AddToWatchlistUseCase(watchlist_repo, company_repo)
    list_use_case = GetWatchlistUseCase(watchlist_repo)

    add_use_case.execute("alice", "AAPL")

    assert len(list_use_case.execute("alice")) == 1
    assert len(list_use_case.execute("bob")) == 0


def test_remove_returns_true_when_item_existed_false_otherwise() -> None:
    watchlist_repo = FakeWatchlistRepository()
    company_repo = _company_repo_with_aapl()
    add_use_case = AddToWatchlistUseCase(watchlist_repo, company_repo)
    remove_use_case = RemoveFromWatchlistUseCase(watchlist_repo)

    add_use_case.execute("alice", "AAPL")

    assert remove_use_case.execute("alice", "AAPL") is True
    assert remove_use_case.execute("alice", "AAPL") is False  # already removed
