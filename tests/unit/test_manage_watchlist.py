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


# ---- Smart watchlist tests (named lists, baselines, updates) ----

from datetime import datetime, timezone
from types import SimpleNamespace

from src.application.use_cases.manage_watchlist import (
    ListWatchlistNamesUseCase,
    UpdateWatchlistItemUseCase,
    WatchlistItemNotFoundError,
)
from src.domain.entities.market_quote import MarketQuote


class _StubValuation:
    """Duck-typed stand-in for ComputeValuationUseCase."""

    def __init__(self, pe: float | None = None, fail: bool = False) -> None:
        self._pe = pe
        self._fail = fail

    def execute(self, ticker: str):
        if self._fail:
            raise RuntimeError("valuation unavailable")
        return SimpleNamespace(price_to_earnings=self._pe)


class _FailingQuoteProvider:
    def get_quote(self, ticker: str):
        raise RuntimeError("quote service down")


def _quote(ticker: str, price: float) -> MarketQuote:
    return MarketQuote(
        ticker=ticker, price=price, market_cap=1e12, as_of=datetime.now(timezone.utc)
    )


def test_add_captures_price_and_pe_baselines_when_providers_wired() -> None:
    from src.domain.entities.company import Company, Sector
    from tests.unit.fakes import FakeDataProvider

    watchlist_repo = FakeWatchlistRepository()
    company_repo = _company_repo_with_aapl()
    company = company_repo.get_by_ticker("AAPL")
    provider = FakeDataProvider(company, quotes_by_ticker={"AAPL": _quote("AAPL", 150.0)})

    add = AddToWatchlistUseCase(
        watchlist_repo, company_repo, data_provider=provider,
        valuation_use_case=_StubValuation(pe=25.0),
    )
    item = add.execute("alice", "AAPL", notes="cheap AI play")

    assert item.added_price == 150.0
    assert item.added_pe == 25.0


def test_baseline_capture_failure_never_blocks_adding() -> None:
    watchlist_repo = FakeWatchlistRepository()
    add = AddToWatchlistUseCase(
        watchlist_repo, _company_repo_with_aapl(),
        data_provider=_FailingQuoteProvider(),
        valuation_use_case=_StubValuation(fail=True),
    )
    item = add.execute("alice", "AAPL")

    assert item.added_price is None
    assert item.added_pe is None
    assert watchlist_repo.contains("alice", "AAPL")


def test_same_ticker_can_live_on_two_named_lists() -> None:
    watchlist_repo = FakeWatchlistRepository()
    add = AddToWatchlistUseCase(watchlist_repo, _company_repo_with_aapl())

    add.execute("alice", "AAPL", list_name="Default")
    add.execute("alice", "AAPL", list_name="Tech Watch")

    assert len(GetWatchlistUseCase(watchlist_repo).execute("alice")) == 2
    assert len(GetWatchlistUseCase(watchlist_repo).execute("alice", "Tech Watch")) == 1

    # remove from one list only
    removed = RemoveFromWatchlistUseCase(watchlist_repo).execute("alice", "AAPL", "Tech Watch")
    assert removed is True
    remaining = GetWatchlistUseCase(watchlist_repo).execute("alice")
    assert len(remaining) == 1 and remaining[0].list_name == "Default"

    # list_name=None removes from ALL lists (backward-compat semantics)
    add.execute("alice", "AAPL", list_name="Tech Watch")
    assert RemoveFromWatchlistUseCase(watchlist_repo).execute("alice", "AAPL") is True
    assert GetWatchlistUseCase(watchlist_repo).execute("alice") == []


def test_update_sets_target_without_clobbering_baselines() -> None:
    from src.domain.entities.company import Company, Sector
    from tests.unit.fakes import FakeDataProvider

    watchlist_repo = FakeWatchlistRepository()
    company_repo = _company_repo_with_aapl()
    provider = FakeDataProvider(
        company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={"AAPL": _quote("AAPL", 150.0)},
    )
    add = AddToWatchlistUseCase(
        watchlist_repo, company_repo, data_provider=provider,
        valuation_use_case=_StubValuation(pe=25.0),
    )
    original = add.execute("alice", "AAPL", notes="thesis")

    updated = UpdateWatchlistItemUseCase(watchlist_repo).execute(
        "alice", "AAPL", target_price=120.0, alert_threshold_pct=0.03
    )

    assert updated.target_price == 120.0
    assert updated.alert_threshold_pct == 0.03
    assert updated.added_price == 150.0  # baseline preserved
    assert updated.added_pe == 25.0  # baseline preserved
    assert updated.added_at == original.added_at  # history preserved
    assert updated.notes == "thesis"  # untouched field preserved


def test_update_missing_item_raises() -> None:
    try:
        UpdateWatchlistItemUseCase(FakeWatchlistRepository()).execute(
            "alice", "AAPL", target_price=100.0
        )
        raise AssertionError("expected WatchlistItemNotFoundError")
    except WatchlistItemNotFoundError:
        pass


def test_list_watchlist_names_with_counts() -> None:
    watchlist_repo = FakeWatchlistRepository()
    company_repo = _company_repo_with_aapl()
    from src.domain.entities.company import Company, Sector
    company_repo.save(
        Company(ticker="MSFT", name="Microsoft", sector=Sector.TECHNOLOGY,
                industry="Software", exchange="NASDAQ", country="US")
    )
    add = AddToWatchlistUseCase(watchlist_repo, company_repo)
    add.execute("alice", "AAPL", list_name="Tech Watch")
    add.execute("alice", "MSFT", list_name="Tech Watch")
    add.execute("alice", "AAPL", list_name="Default")

    counts = ListWatchlistNamesUseCase(watchlist_repo).execute("alice")
    assert counts == {"Tech Watch": 2, "Default": 1}
