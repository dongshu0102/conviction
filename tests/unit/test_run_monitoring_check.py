from __future__ import annotations

from datetime import datetime, timezone

from src.application.use_cases.manage_watchlist import AddToWatchlistUseCase
from src.application.use_cases.run_monitoring_check import RunMonitoringCheckUseCase
from src.domain.entities.company import Company, Sector
from src.domain.entities.market_quote import MarketQuote
from src.domain.entities.monitoring import PriceSnapshot
from tests.unit.fakes import (
    FakeAlertRepository,
    FakeCompanyRepository,
    FakeDataProvider,
    FakePriceSnapshotRepository,
    FakeWatchlistRepository,
)


def _setup_with_aapl_on_watchlist(user_id: str = "alice"):
    company_repo = FakeCompanyRepository()
    company_repo.save(
        Company(
            ticker="AAPL", name="Apple Inc.", sector=Sector.TECHNOLOGY,
            industry="X", exchange="NASDAQ", country="US",
        )
    )
    watchlist_repo = FakeWatchlistRepository()
    AddToWatchlistUseCase(watchlist_repo, company_repo).execute(user_id, "AAPL")
    return company_repo, watchlist_repo


def test_first_check_establishes_baseline_with_no_alert() -> None:
    company_repo, watchlist_repo = _setup_with_aapl_on_watchlist()
    snapshot_repo = FakePriceSnapshotRepository()
    alert_repo = FakeAlertRepository()
    provider = FakeDataProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={
            "AAPL": MarketQuote(ticker="AAPL", price=100.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))
        },
    )
    use_case = RunMonitoringCheckUseCase(watchlist_repo, snapshot_repo, alert_repo, provider)

    alerts = use_case.execute("alice")

    assert alerts == []  # no prior baseline -> nothing to compare against
    assert snapshot_repo.get_latest("AAPL").price == 100.0  # baseline now established


def test_move_below_threshold_generates_no_alert() -> None:
    company_repo, watchlist_repo = _setup_with_aapl_on_watchlist()
    snapshot_repo = FakePriceSnapshotRepository()
    snapshot_repo.save(PriceSnapshot(ticker="AAPL", price=100.0, captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    alert_repo = FakeAlertRepository()
    # 2% move — below the 5% default threshold
    provider = FakeDataProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={
            "AAPL": MarketQuote(ticker="AAPL", price=102.0, market_cap=1.0, as_of=datetime(2026, 1, 2, tzinfo=timezone.utc))
        },
    )
    use_case = RunMonitoringCheckUseCase(watchlist_repo, snapshot_repo, alert_repo, provider)

    alerts = use_case.execute("alice")

    assert alerts == []


def test_move_above_threshold_generates_alert_with_exact_change_pct() -> None:
    company_repo, watchlist_repo = _setup_with_aapl_on_watchlist()
    snapshot_repo = FakePriceSnapshotRepository()
    snapshot_repo.save(PriceSnapshot(ticker="AAPL", price=100.0, captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    alert_repo = FakeAlertRepository()
    # 10% move up — above the 5% default threshold
    provider = FakeDataProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={
            "AAPL": MarketQuote(ticker="AAPL", price=110.0, market_cap=1.0, as_of=datetime(2026, 1, 2, tzinfo=timezone.utc))
        },
    )
    use_case = RunMonitoringCheckUseCase(watchlist_repo, snapshot_repo, alert_repo, provider)

    alerts = use_case.execute("alice")

    assert len(alerts) == 1
    assert abs(alerts[0].change_pct - 0.10) < 1e-9
    assert alerts[0].id is not None  # repository assigned a real id
    assert "AAPL" in alerts[0].message
    # Baseline updates to the new price after the check
    assert snapshot_repo.get_latest("AAPL").price == 110.0


def test_downward_move_also_alerts() -> None:
    company_repo, watchlist_repo = _setup_with_aapl_on_watchlist()
    snapshot_repo = FakePriceSnapshotRepository()
    snapshot_repo.save(PriceSnapshot(ticker="AAPL", price=100.0, captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    alert_repo = FakeAlertRepository()
    provider = FakeDataProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={
            "AAPL": MarketQuote(ticker="AAPL", price=90.0, market_cap=1.0, as_of=datetime(2026, 1, 2, tzinfo=timezone.utc))
        },
    )
    use_case = RunMonitoringCheckUseCase(watchlist_repo, snapshot_repo, alert_repo, provider)

    alerts = use_case.execute("alice")

    assert len(alerts) == 1
    assert abs(alerts[0].change_pct - (-0.10)) < 1e-9
    assert "down" in alerts[0].message
