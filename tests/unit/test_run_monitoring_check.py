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


# ---- Smart watchlist monitoring tests ----

from src.domain.entities.monitoring import AlertType
from src.domain.entities.watchlist import WatchlistItem


def _watch(watchlist_repo, ticker: str, **kwargs) -> None:
    watchlist_repo.add(
        WatchlistItem(
            user_id="alice", ticker=ticker,
            added_at=datetime(2026, 1, 1, tzinfo=timezone.utc), **kwargs,
        )
    )


def _provider_for(company_repo, ticker: str, price: float):
    return FakeDataProvider(
        company=company_repo.get_by_ticker(ticker),
        quotes_by_ticker={
            ticker: MarketQuote(
                ticker=ticker, price=price, market_cap=1.0,
                as_of=datetime(2026, 1, 2, tzinfo=timezone.utc),
            )
        },
    )


def test_per_ticker_threshold_overrides_global_default() -> None:
    company_repo, _ = _setup_with_aapl_on_watchlist()
    watchlist_repo = FakeWatchlistRepository()
    # 3% custom threshold, global default is 5%
    _watch(watchlist_repo, "AAPL", alert_threshold_pct=0.03)

    snapshot_repo = FakePriceSnapshotRepository()
    snapshot_repo.save(PriceSnapshot(ticker="AAPL", price=100.0, captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    alert_repo = FakeAlertRepository()
    # +4% move: below the 5% global default, above the 3% override
    use_case = RunMonitoringCheckUseCase(
        watchlist_repo, snapshot_repo, alert_repo, _provider_for(company_repo, "AAPL", 104.0)
    )

    alerts = use_case.execute("alice")

    assert len(alerts) == 1
    assert alerts[0].alert_type == AlertType.PRICE_MOVE


def test_target_crossing_fires_once_then_stays_silent() -> None:
    company_repo, _ = _setup_with_aapl_on_watchlist()
    watchlist_repo = FakeWatchlistRepository()
    _watch(watchlist_repo, "AAPL", target_price=95.0, alert_threshold_pct=1.0)  # huge threshold: isolate target alerts

    snapshot_repo = FakePriceSnapshotRepository()
    snapshot_repo.save(PriceSnapshot(ticker="AAPL", price=100.0, captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    alert_repo = FakeAlertRepository()

    # Check 1: 100 -> 94 crosses the 95 target -> TARGET_REACHED fires
    use_case = RunMonitoringCheckUseCase(
        watchlist_repo, snapshot_repo, alert_repo, _provider_for(company_repo, "AAPL", 94.0)
    )
    alerts = use_case.execute("alice")
    assert [a.alert_type for a in alerts] == [AlertType.TARGET_REACHED]
    assert "95.00" in alerts[0].message

    # Check 2: price still below target (94 -> 93) -> NO re-alert
    use_case2 = RunMonitoringCheckUseCase(
        watchlist_repo, snapshot_repo, alert_repo, _provider_for(company_repo, "AAPL", 93.0)
    )
    assert use_case2.execute("alice") == []


def test_no_target_alert_on_first_ever_check() -> None:
    company_repo, _ = _setup_with_aapl_on_watchlist()
    watchlist_repo = FakeWatchlistRepository()
    _watch(watchlist_repo, "AAPL", target_price=95.0)

    # No prior snapshot at all — baseline establishment, no crossing detectable
    use_case = RunMonitoringCheckUseCase(
        watchlist_repo, FakePriceSnapshotRepository(), FakeAlertRepository(),
        _provider_for(company_repo, "AAPL", 90.0),
    )
    assert use_case.execute("alice") == []


def test_same_ticker_on_two_lists_evaluates_both_targets_against_same_prior() -> None:
    company_repo, _ = _setup_with_aapl_on_watchlist()
    watchlist_repo = FakeWatchlistRepository()
    # Two lists, two different targets; only one is crossed by 100 -> 92
    _watch(watchlist_repo, "AAPL", list_name="Aggressive", target_price=95.0, alert_threshold_pct=1.0)
    _watch(watchlist_repo, "AAPL", list_name="Patient", target_price=85.0, alert_threshold_pct=1.0)

    snapshot_repo = FakePriceSnapshotRepository()
    snapshot_repo.save(PriceSnapshot(ticker="AAPL", price=100.0, captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))

    use_case = RunMonitoringCheckUseCase(
        watchlist_repo, snapshot_repo, FakeAlertRepository(),
        _provider_for(company_repo, "AAPL", 92.0),
    )
    alerts = use_case.execute("alice")

    assert len(alerts) == 1  # Aggressive's 95 crossed; Patient's 85 not
    assert alerts[0].alert_type == AlertType.TARGET_REACHED
    assert "Aggressive" in alerts[0].message
