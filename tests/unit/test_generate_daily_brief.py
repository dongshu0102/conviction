from __future__ import annotations

from datetime import datetime, timezone

from src.application.use_cases.compute_financial_analysis import (
    ComputeFinancialAnalysisUseCase,
)
from src.application.use_cases.compute_portfolio_risk import ComputePortfolioRiskUseCase
from src.application.use_cases.compute_portfolio_valuation import (
    ComputePortfolioValuationUseCase,
)
from src.application.use_cases.generate_daily_brief import GenerateDailyBriefUseCase
from src.application.use_cases.get_company_financials import GetCompanyFinancialsUseCase
from src.application.use_cases.manage_portfolio import AddHoldingUseCase, CreatePortfolioUseCase
from src.application.use_cases.manage_watchlist import AddToWatchlistUseCase
from src.domain.entities.company import Company, Sector
from src.domain.entities.market_quote import MarketQuote
from src.domain.entities.monitoring import PriceSnapshot
from tests.unit.fakes import (
    FakeAlertRepository,
    FakeBriefGenerator,
    FakeCompanyRepository,
    FakeDataProvider,
    FakeFinancialStatementRepository,
    FakePortfolioRepository,
    FakePriceSnapshotRepository,
    FakeWatchlistRepository,
)


def _company_repo(*tickers: str) -> FakeCompanyRepository:
    repo = FakeCompanyRepository()
    for ticker in tickers:
        repo.save(
            Company(
                ticker=ticker, name=f"{ticker} Inc.", sector=Sector.TECHNOLOGY,
                industry="X", exchange="NASDAQ", country="US",
            )
        )
    return repo


def _build_use_case(company_repo, watchlist_repo, portfolio_repo, snapshot_repo,
                     alert_repo, provider, brief_generator):
    statement_repo = FakeFinancialStatementRepository()
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)
    compute_valuation = ComputePortfolioValuationUseCase(portfolio_repo, provider)
    compute_risk = ComputePortfolioRiskUseCase(compute_valuation, compute_analysis, company_repo)

    return GenerateDailyBriefUseCase(
        watchlist_repo, snapshot_repo, alert_repo, portfolio_repo, provider,
        compute_valuation, compute_risk, brief_generator,
    )


def test_first_time_watchlist_ticker_has_no_prior_price() -> None:
    company_repo = _company_repo("AAPL")
    watchlist_repo = FakeWatchlistRepository()
    AddToWatchlistUseCase(watchlist_repo, company_repo).execute("alice", "AAPL")
    snapshot_repo = FakePriceSnapshotRepository()  # no baseline stored
    provider = FakeDataProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={"AAPL": MarketQuote(ticker="AAPL", price=150.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))},
    )
    brief_generator = FakeBriefGenerator()
    use_case = _build_use_case(
        company_repo, watchlist_repo, FakePortfolioRepository(), snapshot_repo,
        FakeAlertRepository(), provider, brief_generator,
    )

    brief = use_case.execute("alice")

    assert len(brief.watchlist_moves) == 1
    assert brief.watchlist_moves[0].current_price == 150.0
    assert brief.watchlist_moves[0].prior_price is None
    assert brief.watchlist_moves[0].change_pct is None


def test_generator_receives_exact_grounded_data() -> None:
    company_repo = _company_repo("AAPL")
    watchlist_repo = FakeWatchlistRepository()
    AddToWatchlistUseCase(watchlist_repo, company_repo).execute("alice", "AAPL")
    snapshot_repo = FakePriceSnapshotRepository()
    snapshot_repo.save(PriceSnapshot(ticker="AAPL", price=100.0, captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    provider = FakeDataProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={"AAPL": MarketQuote(ticker="AAPL", price=110.0, market_cap=1.0, as_of=datetime(2026, 1, 2, tzinfo=timezone.utc))},
    )
    brief_generator = FakeBriefGenerator(narrative="AAPL is up.")
    use_case = _build_use_case(
        company_repo, watchlist_repo, FakePortfolioRepository(), snapshot_repo,
        FakeAlertRepository(), provider, brief_generator,
    )

    brief = use_case.execute("alice")

    # Exact 10% move computed correctly and passed to the generator
    assert brief_generator.received_watchlist_moves[0].change_pct == 0.1
    assert brief.narrative == "AAPL is up."
    assert brief.model_used == "fake-model"


def test_unread_alert_count_is_included_and_grounded() -> None:
    from datetime import date
    from src.domain.entities.monitoring import Alert, AlertType

    company_repo = _company_repo()
    alert_repo = FakeAlertRepository()
    alert_repo.save(Alert(
        user_id="alice", ticker="AAPL", alert_type=AlertType.PRICE_MOVE,
        message="test", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc), change_pct=0.1,
    ))
    alert_repo.save(Alert(
        user_id="alice", ticker="MSFT", alert_type=AlertType.PRICE_MOVE,
        message="test2", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc), change_pct=-0.05,
    ))
    brief_generator = FakeBriefGenerator()
    use_case = _build_use_case(
        company_repo, FakeWatchlistRepository(), FakePortfolioRepository(),
        FakePriceSnapshotRepository(), alert_repo,
        FakeDataProvider(company=Company(ticker="X", name="X", sector=Sector.TECHNOLOGY, industry="X", exchange="X", country="US")),
        brief_generator,
    )

    brief = use_case.execute("alice")

    assert brief.unread_alert_count == 2
    assert brief_generator.received_alert_count == 2


def test_empty_portfolio_is_excluded_from_summaries() -> None:
    company_repo = _company_repo("AAPL")
    portfolio_repo = FakePortfolioRepository()
    CreatePortfolioUseCase(portfolio_repo).execute("alice", "Empty Portfolio")
    # No holdings added — portfolio exists but is empty
    brief_generator = FakeBriefGenerator()
    use_case = _build_use_case(
        company_repo, FakeWatchlistRepository(), portfolio_repo,
        FakePriceSnapshotRepository(), FakeAlertRepository(),
        FakeDataProvider(company=company_repo.get_by_ticker("AAPL")),
        brief_generator,
    )

    brief = use_case.execute("alice")

    assert brief.portfolio_summaries == []
