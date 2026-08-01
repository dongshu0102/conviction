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


# ---- Earnings alerts ----

from datetime import date, timedelta
from src.domain.entities.earnings import EarningsEvent
from src.domain.entities.monitoring import Alert, AlertType


class _EarningsMonitoringProvider(FakeDataProvider):
    def __init__(self, *args, events=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._events = events or []

    def get_earnings_calendar(self, from_date, to_date):
        return self._events


def _quote(ticker: str, price: float) -> MarketQuote:
    return MarketQuote(ticker=ticker, price=price, market_cap=1.0,
                         as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))


def test_earnings_within_window_fires_alert() -> None:
    company_repo, watchlist_repo = _setup_with_aapl_on_watchlist()
    snapshot_repo = FakePriceSnapshotRepository()
    alert_repo = FakeAlertRepository()
    soon = date.today() + timedelta(days=2)
    provider = _EarningsMonitoringProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={"AAPL": _quote("AAPL", 100.0)},
        events=[EarningsEvent(ticker="AAPL", report_date=soon, eps_estimated=1.5,
                                eps_actual=None, revenue_estimated=None, revenue_actual=None)],
    )
    use_case = RunMonitoringCheckUseCase(watchlist_repo, snapshot_repo, alert_repo, provider)

    alerts = use_case.execute("alice")

    earnings_alerts = [a for a in alerts if a.alert_type == AlertType.EARNINGS_UPCOMING]
    assert len(earnings_alerts) == 1
    assert earnings_alerts[0].ticker == "AAPL"
    assert earnings_alerts[0].change_pct is None  # not a price-move alert
    assert "1.50" in earnings_alerts[0].message


def test_earnings_alert_does_not_refire_within_window() -> None:
    """Simulates the cron running every 15 minutes — the second run,
    moments after the first, must NOT create a duplicate alert."""
    company_repo, watchlist_repo = _setup_with_aapl_on_watchlist()
    snapshot_repo = FakePriceSnapshotRepository()
    alert_repo = FakeAlertRepository()
    soon = date.today() + timedelta(days=1)
    provider = _EarningsMonitoringProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={"AAPL": _quote("AAPL", 100.0)},
        events=[EarningsEvent(ticker="AAPL", report_date=soon, eps_estimated=None,
                                eps_actual=None, revenue_estimated=None, revenue_actual=None)],
    )
    use_case = RunMonitoringCheckUseCase(watchlist_repo, snapshot_repo, alert_repo, provider)

    first_run = use_case.execute("alice")
    second_run = use_case.execute("alice")

    assert len([a for a in first_run if a.alert_type == AlertType.EARNINGS_UPCOMING]) == 1
    assert len([a for a in second_run if a.alert_type == AlertType.EARNINGS_UPCOMING]) == 0


def test_earnings_outside_window_does_not_fire() -> None:
    company_repo, watchlist_repo = _setup_with_aapl_on_watchlist()
    snapshot_repo = FakePriceSnapshotRepository()
    alert_repo = FakeAlertRepository()
    far_off = date.today() + timedelta(days=30)
    provider = _EarningsMonitoringProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={"AAPL": _quote("AAPL", 100.0)},
        events=[EarningsEvent(ticker="AAPL", report_date=far_off, eps_estimated=None,
                                eps_actual=None, revenue_estimated=None, revenue_actual=None)],
    )
    use_case = RunMonitoringCheckUseCase(watchlist_repo, snapshot_repo, alert_repo, provider)

    alerts = use_case.execute("alice")
    assert [a for a in alerts if a.alert_type == AlertType.EARNINGS_UPCOMING] == []


def test_provider_without_earnings_support_degrades_silently() -> None:
    """Default FakeDataProvider has no get_earnings_calendar override —
    monitoring must proceed normally (price-move checks unaffected),
    not crash."""
    company_repo, watchlist_repo = _setup_with_aapl_on_watchlist()
    snapshot_repo = FakePriceSnapshotRepository()
    alert_repo = FakeAlertRepository()
    provider = FakeDataProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={"AAPL": _quote("AAPL", 100.0)},
    )
    use_case = RunMonitoringCheckUseCase(watchlist_repo, snapshot_repo, alert_repo, provider)

    alerts = use_case.execute("alice")  # must not raise
    assert alerts == []
