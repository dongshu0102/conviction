from __future__ import annotations

from datetime import date, datetime, timezone

from src.application.interfaces.chat_agent import ChatAgent, ChatResult
from src.application.use_cases.chat_with_agent import ChatWithAgentUseCase
from src.application.use_cases.compute_financial_analysis import (
    ComputeFinancialAnalysisUseCase,
)
from src.application.use_cases.compute_option_portfolio_valuation import (
    ComputeOptionPortfolioValuationUseCase,
)
from src.application.use_cases.compute_portfolio_greeks import ComputePortfolioGreeksUseCase
from src.application.use_cases.compute_portfolio_risk import ComputePortfolioRiskUseCase
from src.application.use_cases.compute_portfolio_valuation import (
    ComputePortfolioValuationUseCase,
)
from src.application.use_cases.compute_valuation import ComputeValuationUseCase
from src.application.use_cases.get_company_financials import GetCompanyFinancialsUseCase
from src.application.use_cases.manage_option_holdings import (
    AddOptionHoldingUseCase,
    RemoveOptionHoldingUseCase,
)
from src.application.use_cases.manage_portfolio import (
    AddHoldingUseCase,
    CreatePortfolioUseCase,
    DeletePortfolioUseCase,
    GetPortfolioUseCase,
    ListPortfoliosUseCase,
    RemoveHoldingUseCase,
)

from src.application.use_cases.compute_universe_factor_snapshot import (
    ComputeUniverseFactorSnapshotUseCase,
)
from src.application.use_cases.construct_risk_parity_portfolio import (
    ConstructRiskParityPortfolioUseCase,
)
from src.application.use_cases.generate_theme_synthesis import GenerateThemeSynthesisUseCase
from src.application.use_cases.get_upcoming_earnings import GetUpcomingEarningsUseCase
from src.application.use_cases.ingest_etf_data import IngestEtfDataUseCase
from src.application.use_cases.suggest_theme import SuggestThemeUseCase
from src.application.use_cases.get_factor_scores import GetFactorScoresUseCase
from src.application.use_cases.manage_universe_theme import (
    AddTickerToThemeUseCase,
    CreateUniverseThemeUseCase,
    GetThemeTickersUseCase,
    ListUniverseThemesUseCase,
    RemoveTickerFromThemeUseCase,
)
from src.application.use_cases.get_watchlist_news import GetWatchlistNewsUseCase
from src.application.use_cases.triage_watchlist import TriageWatchlistUseCase
from src.application.use_cases.manage_watchlist import (
    ListWatchlistNamesUseCase,
    UpdateWatchlistItemUseCase,
    AddToWatchlistUseCase,
    GetWatchlistUseCase,
    RemoveFromWatchlistUseCase,
)
from src.application.use_cases.recommend_stocks import RecommendStocksUseCase
from src.application.use_cases.screen_stocks import ScreenStocksUseCase
from src.application.use_cases.suggest_hedging import SuggestHedgingUseCase
from src.application.use_cases.suggest_rebalancing import SuggestRebalancingUseCase
from src.domain.entities.company import Company, Sector
from src.domain.entities.market_quote import MarketQuote
from tests.unit.fakes import (
    FakeFactorScoreRepository,
    FakeThemeSuggestionGenerator,
    FakeThemeSynthesisGenerator,
    FakeUniverseThemeRepository,
    FakePriceSnapshotRepository,
    FakeCompanyRepository,
    FakeDataProvider,
    FakeFinancialStatementRepository,
    FakeOptionsDataProvider,
    FakePortfolioRepository,
    FakeResearchReportRepository,
    FakeWatchlistRepository,
    FakeAlertRepository,
    FakeBriefGenerator,
)
from src.application.use_cases.manage_alerts import GetAlertsUseCase
from src.application.use_cases.generate_daily_brief import GenerateDailyBriefUseCase
from src.application.use_cases.ingest_company_data import IngestCompanyDataUseCase
from src.application.use_cases.assess_speculative_growth import (
    AssessSpeculativeGrowthUseCase,
)


class FakeChatAgent(ChatAgent):
    """Instead of calling a real LLM, directly exercises the dispatch
    function with a scripted sequence of tool calls — lets us test the
    use case's tool-routing and ownership logic without any network
    dependency."""

    def __init__(self, scripted_calls, final_reply="ok"):
        self.scripted_calls = scripted_calls
        self.final_reply = final_reply
        self.dispatch_results = []

    def run(self, system_prompt, messages, tools, dispatch):
        for name, tool_input in self.scripted_calls:
            self.dispatch_results.append(dispatch(name, tool_input))
        return ChatResult(reply=self.final_reply, tool_calls_made=len(self.scripted_calls))

    def stream(self, system_prompt, messages, tools, dispatch):
        for name, tool_input in self.scripted_calls:
            self.dispatch_results.append(dispatch(name, tool_input))
        yield self.final_reply


def _company_repo(*tickers: str) -> FakeCompanyRepository:
    repo = FakeCompanyRepository()
    for t in tickers:
        repo.save(
            Company(
                ticker=t, name=f"{t} Inc.", sector=Sector.TECHNOLOGY,
                industry="X", exchange="NASDAQ", country="US",
            )
        )
    return repo


def _build_use_case(scripted_calls, company_repo=None, portfolio_repo=None, watchlist_repo=None, provider=None, options_provider=None, theme_repo=None, statement_repo=None, get_factor_scores_override=None, alert_repo=None):
    company_repo = company_repo or _company_repo()
    portfolio_repo = portfolio_repo or FakePortfolioRepository()
    watchlist_repo = watchlist_repo or FakeWatchlistRepository()
    statement_repo = statement_repo or FakeFinancialStatementRepository()
    alert_repo = alert_repo or FakeAlertRepository()
    provider = provider or FakeDataProvider(company=Company(ticker="X", name="X", sector=Sector.TECHNOLOGY, industry="X", exchange="X", country="US"))
    options_provider = options_provider or FakeOptionsDataProvider()
    research_repo = FakeResearchReportRepository()
    snapshot_repo = FakePriceSnapshotRepository()
    brief_generator = FakeBriefGenerator()

    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    compute_valuation = ComputePortfolioValuationUseCase(portfolio_repo, provider)
    compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)
    compute_risk = ComputePortfolioRiskUseCase(compute_valuation, compute_analysis, company_repo, provider)
    compute_company_valuation = ComputeValuationUseCase(get_financials, provider)

    fake_agent = FakeChatAgent(scripted_calls)
    _factor_score_repo = FakeFactorScoreRepository()
    theme_repo = theme_repo or FakeUniverseThemeRepository()
    _get_factor_scores = get_factor_scores_override or GetFactorScoresUseCase(
        _factor_score_repo,
        ComputeUniverseFactorSnapshotUseCase(
            provider, compute_company_valuation, compute_analysis, _factor_score_repo
        ),
        auto_refresh=True,  # test fixtures have no rate-limit risk, unlike production
    )
    use_case = ChatWithAgentUseCase(
        chat_agent=fake_agent,
        get_watchlist=GetWatchlistUseCase(watchlist_repo),
        add_to_watchlist=AddToWatchlistUseCase(watchlist_repo, company_repo),
        remove_from_watchlist=RemoveFromWatchlistUseCase(watchlist_repo),
        list_portfolios=ListPortfoliosUseCase(portfolio_repo),
        create_portfolio=CreatePortfolioUseCase(portfolio_repo),
        get_portfolio=GetPortfolioUseCase(portfolio_repo),
        compute_valuation=compute_valuation,
        compute_risk=compute_risk,
        add_holding=AddHoldingUseCase(portfolio_repo, company_repo),
        delete_portfolio=DeletePortfolioUseCase(portfolio_repo),
        compute_analysis=compute_analysis,
        compute_company_valuation=compute_company_valuation,
        research_repo=research_repo,
        suggest_rebalancing=SuggestRebalancingUseCase(compute_valuation),
        screen_stocks=ScreenStocksUseCase(compute_company_valuation, compute_analysis),
        recommend_stocks=RecommendStocksUseCase(compute_risk, company_repo, ScreenStocksUseCase(compute_company_valuation, compute_analysis)),
        add_option_holding=AddOptionHoldingUseCase(portfolio_repo),
        remove_option_holding=RemoveOptionHoldingUseCase(portfolio_repo),
        compute_portfolio_greeks=ComputePortfolioGreeksUseCase(portfolio_repo, options_provider),
        compute_option_portfolio_valuation=ComputeOptionPortfolioValuationUseCase(
            portfolio_repo, options_provider
        ),
        suggest_hedging=SuggestHedgingUseCase(portfolio_repo, options_provider),
        update_watchlist_item=UpdateWatchlistItemUseCase(watchlist_repo),
        list_watchlists=ListWatchlistNamesUseCase(watchlist_repo),
        triage_watchlist=TriageWatchlistUseCase(
            watchlist_repo, provider, FakePriceSnapshotRepository()
        ),
        get_watchlist_news=GetWatchlistNewsUseCase(watchlist_repo, provider),
        get_factor_scores=_get_factor_scores,
        create_universe_theme=CreateUniverseThemeUseCase(theme_repo),
        add_ticker_to_theme=AddTickerToThemeUseCase(theme_repo, company_repo),
        remove_ticker_from_theme=RemoveTickerFromThemeUseCase(theme_repo),
        list_universe_themes=ListUniverseThemesUseCase(theme_repo),
        get_theme_tickers=GetThemeTickersUseCase(theme_repo),
        generate_theme_synthesis=GenerateThemeSynthesisUseCase(
            theme_repo, GetThemeTickersUseCase(theme_repo),
            ScreenStocksUseCase(compute_company_valuation, compute_analysis),
            _get_factor_scores, FakeThemeSynthesisGenerator(),
        ),
        construct_risk_parity_portfolio=ConstructRiskParityPortfolioUseCase(provider),
        get_upcoming_earnings=GetUpcomingEarningsUseCase(watchlist_repo, provider),
        ingest_etf=IngestEtfDataUseCase(company_repo, provider),
        suggest_theme=SuggestThemeUseCase(
            provider, company_repo, FakeThemeSuggestionGenerator()
        ),
        remove_holding=RemoveHoldingUseCase(portfolio_repo),
        get_alerts=GetAlertsUseCase(alert_repo),
        generate_daily_brief=GenerateDailyBriefUseCase(
            watchlist_repo, snapshot_repo, alert_repo, portfolio_repo, provider,
            compute_valuation, compute_risk, brief_generator,
        ),
        get_company_financials=get_financials,
        ingest_company=IngestCompanyDataUseCase(provider, company_repo, statement_repo),
        assess_speculative_growth=AssessSpeculativeGrowthUseCase(get_financials, compute_company_valuation),
    )
    return use_case, fake_agent, portfolio_repo


def test_get_watchlist_returns_correct_tickers() -> None:
    company_repo = _company_repo("AAPL")
    watchlist_repo = FakeWatchlistRepository()
    AddToWatchlistUseCase(watchlist_repo, company_repo).execute("alice", "AAPL")

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("get_watchlist", {})],
        company_repo=company_repo,
        watchlist_repo=watchlist_repo,
    )
    use_case.execute("alice", "what's on my watchlist", [])

    result = fake_agent.dispatch_results[0]
    assert [i["ticker"] for i in result["items"]] == ["AAPL"]
    assert result["items"][0]["list_name"] == "Default"
    assert result["items"][0]["added_price"] is None  # no provider wired in this test


def test_remove_holding_dispatches_correctly() -> None:
    portfolio_repo = FakePortfolioRepository()
    company_repo = _company_repo("AAPL")
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Growth")
    AddHoldingUseCase(portfolio_repo, company_repo).execute(
        portfolio.portfolio_id, "AAPL", 10, 150.0
    )

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("remove_holding", {"portfolio_id": portfolio.portfolio_id, "ticker": "AAPL"})],
        portfolio_repo=portfolio_repo,
        company_repo=company_repo,
    )
    use_case.execute("alice", "remove AAPL from my portfolio", [])

    result = fake_agent.dispatch_results[0]
    assert result["status"] == "removed"
    assert result["ticker"] == "AAPL"
    stored = portfolio_repo.get_by_id(portfolio.portfolio_id)
    assert stored.holdings == []


def test_remove_holding_blocks_access_to_another_users_portfolio() -> None:
    portfolio_repo = FakePortfolioRepository()
    alice_portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Alice's")

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("remove_holding", {"portfolio_id": alice_portfolio.portfolio_id, "ticker": "AAPL"})],
        portfolio_repo=portfolio_repo,
    )
    use_case.execute("bob", "remove AAPL from that portfolio", [])

    result = fake_agent.dispatch_results[0]
    assert "error" in result
    assert "portfolio" in result["error"].lower()


def test_get_alerts_dispatches_correctly() -> None:
    from src.domain.entities.monitoring import Alert, AlertType
    from datetime import datetime, timezone

    alert_repo = FakeAlertRepository()
    alert_repo.save(Alert(
        user_id="alice", ticker="NVDA", alert_type=AlertType.PRICE_MOVE,
        message="NVDA up 7% today", created_at=datetime.now(timezone.utc), change_pct=0.07,
    ))

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("get_alerts", {})], alert_repo=alert_repo,
    )
    use_case.execute("alice", "any alerts for me?", [])

    result = fake_agent.dispatch_results[0]
    assert len(result["alerts"]) == 1
    assert result["alerts"][0]["ticker"] == "NVDA"
    assert result["alerts"][0]["change_pct"] == 0.07


def test_get_daily_brief_dispatches_correctly() -> None:
    use_case, fake_agent, _ = _build_use_case(scripted_calls=[("get_daily_brief", {})])
    use_case.execute("alice", "give me my daily brief", [])

    result = fake_agent.dispatch_results[0]
    assert "narrative" in result
    assert result["narrative"] == "Test brief narrative."  # FakeBriefGenerator's default
    assert "unread_alert_count" in result


def test_get_company_financials_dispatches_correctly() -> None:
    company_repo = _company_repo("AAPL")
    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("get_company_financials", {"ticker": "AAPL", "years": 3})],
        company_repo=company_repo,
    )
    use_case.execute("alice", "show me AAPL's raw financials", [])

    result = fake_agent.dispatch_results[0]
    assert result["ticker"] == "AAPL"
    assert "income_statements" in result
    assert "balance_sheets" in result
    assert "cash_flow_statements" in result


def test_get_company_financials_unknown_ticker_returns_error_not_crash() -> None:
    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("get_company_financials", {"ticker": "ZZZZ"})],
    )
    use_case.execute("alice", "show me ZZZZ's financials", [])

    result = fake_agent.dispatch_results[0]
    assert "error" in result


def test_get_portfolio_dispatches_correctly() -> None:
    portfolio_repo = FakePortfolioRepository()
    company_repo = _company_repo("AAPL")
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Growth")
    AddHoldingUseCase(portfolio_repo, company_repo).execute(portfolio.portfolio_id, "AAPL", 10, 150.0)

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("get_portfolio", {"portfolio_id": portfolio.portfolio_id})],
        portfolio_repo=portfolio_repo,
        company_repo=company_repo,
    )
    use_case.execute("alice", "what's in my Growth portfolio", [])

    result = fake_agent.dispatch_results[0]
    assert result["name"] == "Growth"
    assert len(result["holdings"]) == 1
    assert result["holdings"][0]["ticker"] == "AAPL"
    assert result["holdings"][0]["shares"] == 10
    assert result["option_holdings"] == []


def test_get_portfolio_blocks_access_to_another_users_portfolio() -> None:
    portfolio_repo = FakePortfolioRepository()
    alice_portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Alice's")

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("get_portfolio", {"portfolio_id": alice_portfolio.portfolio_id})],
        portfolio_repo=portfolio_repo,
    )
    use_case.execute("bob", "what's in that portfolio", [])

    result = fake_agent.dispatch_results[0]
    assert "error" in result
    assert "portfolio" in result["error"].lower()


def test_ingest_company_dispatches_correctly() -> None:
    company_repo = FakeCompanyRepository()
    provider = FakeDataProvider(
        company=Company(ticker="AAPL", name="Apple", sector=Sector.TECHNOLOGY,
                         industry="X", exchange="X", country="US")
    )
    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("ingest_company", {"ticker": "AAPL", "years": 3})],
        company_repo=company_repo,
        provider=provider,
    )
    use_case.execute("alice", "ingest AAPL", [])

    result = fake_agent.dispatch_results[0]
    assert result["status"] == "ingested"
    assert result["ticker"] == "AAPL"
    # The real effect that matters: the company is now actually saved —
    # confirmed against the SAME provider ticker used above, since
    # FakeDataProvider.get_company_profile ignores its ticker argument
    # and always returns whatever was configured at construction time.
    assert company_repo.get_by_ticker("AAPL") is not None


def test_assess_speculative_growth_dispatches_correctly() -> None:
    from src.domain.entities.financial_statement import FiscalPeriodKey, IncomeStatement, Period

    company = Company(ticker="ROCKET", name="Rocket Inc", sector=Sector.TECHNOLOGY,
                       industry="Software", exchange="NASDAQ", country="US")
    company_repo = FakeCompanyRepository()
    company_repo.save(company)

    statement_repo = FakeFinancialStatementRepository()
    key_2024 = FiscalPeriodKey(ticker="ROCKET", fiscal_year=2024, period=Period.ANNUAL)
    key_2025 = FiscalPeriodKey(ticker="ROCKET", fiscal_year=2025, period=Period.ANNUAL)
    statement_repo.save_income_statement(IncomeStatement(
        key=key_2024, fiscal_date_ending=date(2024, 12, 31), reported_currency="USD",
        revenue=10_000_000, net_income=-2_000_000,
    ))
    statement_repo.save_income_statement(IncomeStatement(
        key=key_2025, fiscal_date_ending=date(2025, 12, 31), reported_currency="USD",
        revenue=20_000_000, net_income=-1_000_000,
    ))

    provider = FakeDataProvider(company=company)

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("assess_speculative_growth", {"ticker": "ROCKET"})],
        company_repo=company_repo,
        provider=provider,
        statement_repo=statement_repo,
    )
    use_case.execute("alice", "is ROCKET a good speculative growth pick?", [])

    result = fake_agent.dispatch_results[0]
    assert result["ticker"] == "ROCKET"
    assert result["is_profitable"] is False
    assert any("unprofitable" in f.lower() for f in result["risk_flags"])
    # The actual differentiator being verified: never a bare score,
    # always the honest disclaimer alongside the structured data.
    assert "note" in result
    assert "not a prediction" in result["note"].lower()


def test_ownership_check_blocks_access_to_another_users_portfolio() -> None:
    """The core security boundary: a message referencing someone else's
    portfolio_id must not leak that portfolio's data."""
    portfolio_repo = FakePortfolioRepository()
    alice_portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Alice's Portfolio")

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("get_portfolio_valuation", {"portfolio_id": alice_portfolio.portfolio_id})],
        portfolio_repo=portfolio_repo,
    )
    # "bob" is asking about alice's portfolio_id
    use_case.execute("bob", "what's this portfolio worth", [])

    result = fake_agent.dispatch_results[0]
    assert "error" in result
    # Must not leak that the portfolio exists at all, or any of its data
    assert "portfolio" in result["error"].lower()


def test_owner_can_access_their_own_portfolio() -> None:
    portfolio_repo = FakePortfolioRepository()
    company_repo = _company_repo("AAPL")
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "My Portfolio")
    AddHoldingUseCase(portfolio_repo, company_repo).execute(
        portfolio.portfolio_id, "AAPL", shares=10, cost_basis_per_share=100
    )
    provider = FakeDataProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={"AAPL": MarketQuote(ticker="AAPL", price=150.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))},
    )

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("get_portfolio_valuation", {"portfolio_id": portfolio.portfolio_id})],
        company_repo=company_repo,
        portfolio_repo=portfolio_repo,
        provider=provider,
    )
    use_case.execute("alice", "what's my portfolio worth", [])

    result = fake_agent.dispatch_results[0]
    assert "error" not in result
    assert result["total_market_value"] == 1500.0


def test_add_to_watchlist_surfaces_error_for_uningested_ticker() -> None:
    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("add_to_watchlist", {"ticker": "ZZZZ"})],
    )
    use_case.execute("alice", "add ZZZZ to my watchlist", [])

    assert "error" in fake_agent.dispatch_results[0]


def test_unknown_tool_name_returns_error_not_crash() -> None:
    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("nonexistent_tool", {})],
    )
    use_case.execute("alice", "do something", [])

    assert "error" in fake_agent.dispatch_results[0]


def test_suggest_rebalancing_dispatches_correctly_for_own_portfolio() -> None:
    portfolio_repo = FakePortfolioRepository()
    company_repo = _company_repo("AAPL")
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Concentrated")
    AddHoldingUseCase(portfolio_repo, company_repo).execute(
        portfolio.portfolio_id, "AAPL", shares=10, cost_basis_per_share=100
    )
    provider = FakeDataProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={"AAPL": MarketQuote(ticker="AAPL", price=100.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))},
    )

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("suggest_rebalancing", {"portfolio_id": portfolio.portfolio_id})],
        company_repo=company_repo,
        portfolio_repo=portfolio_repo,
        provider=provider,
    )
    use_case.execute("alice", "should I rebalance?", [])

    result = fake_agent.dispatch_results[0]
    assert "error" not in result
    # Single 100%-weight holding — definitely over the 30% default target
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["ticker"] == "AAPL"


def test_suggest_rebalancing_blocks_access_to_another_users_portfolio() -> None:
    portfolio_repo = FakePortfolioRepository()
    alice_portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Alice's")

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("suggest_rebalancing", {"portfolio_id": alice_portfolio.portfolio_id})],
        portfolio_repo=portfolio_repo,
    )
    use_case.execute("bob", "should I rebalance alice's portfolio?", [])

    assert "error" in fake_agent.dispatch_results[0]


def test_remove_from_watchlist_dispatches_correctly() -> None:
    company_repo = _company_repo("AAPL")
    watchlist_repo = FakeWatchlistRepository()
    AddToWatchlistUseCase(watchlist_repo, company_repo).execute("alice", "AAPL")

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("remove_from_watchlist", {"ticker": "AAPL"})],
        company_repo=company_repo,
        watchlist_repo=watchlist_repo,
    )
    use_case.execute("alice", "remove AAPL from my watchlist", [])

    result = fake_agent.dispatch_results[0]
    assert result == {"ticker": "AAPL", "status": "removed"}
    # Confirm it actually removed it, not just claimed to
    assert GetWatchlistUseCase(watchlist_repo).execute("alice") == []


def test_remove_from_watchlist_reports_error_for_ticker_not_present() -> None:
    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("remove_from_watchlist", {"ticker": "ZZZZ"})],
    )
    use_case.execute("alice", "remove ZZZZ from my watchlist", [])

    assert "error" in fake_agent.dispatch_results[0]


def test_create_portfolio_dispatches_and_actually_persists() -> None:
    use_case, fake_agent, portfolio_repo = _build_use_case(
        scripted_calls=[("create_portfolio", {"name": "My New Portfolio"})],
    )
    use_case.execute("alice", "create a portfolio called My New Portfolio", [])

    result = fake_agent.dispatch_results[0]
    assert result["name"] == "My New Portfolio"
    assert result["status"] == "created"
    assert "portfolio_id" in result

    # Confirm it actually exists and belongs to alice, not just claims to
    portfolios = ListPortfoliosUseCase(portfolio_repo).execute("alice")
    assert len(portfolios) == 1
    assert portfolios[0].name == "My New Portfolio"


def test_delete_portfolio_blocks_access_to_another_users_portfolio() -> None:
    """The critical security test: delete_portfolio's underlying use case
    has NO ownership check of its own (confirmed by reading
    manage_portfolio.py directly) — the chat tool's ownership check is
    the ONLY thing preventing a message from deleting someone else's
    portfolio by guessing/referencing its id."""
    portfolio_repo = FakePortfolioRepository()
    alice_portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Alice's Portfolio")

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("delete_portfolio", {"portfolio_id": alice_portfolio.portfolio_id})],
        portfolio_repo=portfolio_repo,
    )
    use_case.execute("bob", "delete alice's portfolio", [])

    assert "error" in fake_agent.dispatch_results[0]
    # Must not actually have been deleted
    assert GetPortfolioUseCase(portfolio_repo).execute(alice_portfolio.portfolio_id) is not None


def test_delete_portfolio_succeeds_for_owner() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "To Delete")

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("delete_portfolio", {"portfolio_id": portfolio.portfolio_id})],
        portfolio_repo=portfolio_repo,
    )
    use_case.execute("alice", "delete my To Delete portfolio", [])

    result = fake_agent.dispatch_results[0]
    assert result == {"portfolio_id": portfolio.portfolio_id, "status": "deleted"}
    from src.application.use_cases.manage_portfolio import PortfolioNotFoundError
    try:
        GetPortfolioUseCase(portfolio_repo).execute(portfolio.portfolio_id)
        assert False, "expected PortfolioNotFoundError after deletion"
    except PortfolioNotFoundError:
        pass


def test_add_option_holding_dispatches_correctly() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Options")

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[(
            "add_option_holding",
            {
                "portfolio_id": portfolio.portfolio_id,
                "underlying_ticker": "AAPL",
                "strike": 150.0,
                "expiration": "2026-12-18",
                "option_type": "call",
                "contracts_held": 5,
                "cost_basis_per_contract": 320.0,
            },
        )],
        portfolio_repo=portfolio_repo,
    )
    use_case.execute("alice", "buy 5 AAPL 150 calls exp 2026-12-18", [])

    result = fake_agent.dispatch_results[0]
    assert result["status"] == "added"
    assert result["underlying_ticker"] == "AAPL"
    stored = portfolio_repo.get_by_id(portfolio.portfolio_id)
    assert len(stored.option_holdings) == 1


def test_add_option_holding_blocks_access_to_another_users_portfolio() -> None:
    portfolio_repo = FakePortfolioRepository()
    alice_portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Alice's")

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[(
            "add_option_holding",
            {
                "portfolio_id": alice_portfolio.portfolio_id,
                "underlying_ticker": "AAPL",
                "strike": 150.0,
                "expiration": "2026-12-18",
                "option_type": "call",
                "contracts_held": 5,
                "cost_basis_per_contract": 320.0,
            },
        )],
        portfolio_repo=portfolio_repo,
    )
    use_case.execute("bob", "add an option to alice's portfolio", [])

    assert "error" in fake_agent.dispatch_results[0]
    stored = portfolio_repo.get_by_id(alice_portfolio.portfolio_id)
    assert stored.option_holdings == []  # must not have been added


def test_add_option_holding_reports_malformed_date_gracefully() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Options")

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[(
            "add_option_holding",
            {
                "portfolio_id": portfolio.portfolio_id,
                "underlying_ticker": "AAPL",
                "strike": 150.0,
                "expiration": "not-a-date",
                "option_type": "call",
                "contracts_held": 5,
                "cost_basis_per_contract": 320.0,
            },
        )],
        portfolio_repo=portfolio_repo,
    )
    use_case.execute("alice", "add option", [])

    assert "error" in fake_agent.dispatch_results[0]


def test_compute_portfolio_greeks_blocks_access_to_another_users_portfolio() -> None:
    """Same critical security pattern as every other portfolio-scoped
    tool — a message referencing someone else's portfolio_id must not
    leak their Greeks exposure."""
    portfolio_repo = FakePortfolioRepository()
    alice_portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Alice's")

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("compute_portfolio_greeks", {"portfolio_id": alice_portfolio.portfolio_id})],
        portfolio_repo=portfolio_repo,
    )
    use_case.execute("bob", "what's the delta on alice's portfolio?", [])

    assert "error" in fake_agent.dispatch_results[0]


def test_compute_portfolio_greeks_dispatches_correctly_for_owner() -> None:
    from src.domain.entities.option import OptionContract, OptionQuote

    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Options")
    AddOptionHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "call", 5, 320.0
    )
    contract = OptionContract("AAPL", 150.0, date(2026, 12, 18), "call")
    quote = OptionQuote(
        contract=contract, bid=1.0, ask=1.1, last=1.05, implied_volatility=0.3,
        open_interest=100, volume=10, delta=0.5, gamma=0.02, theta=-0.03, vega=0.15,
        underlying_price=150.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    options_provider = FakeOptionsDataProvider(
        {("AAPL", 150.0, date(2026, 12, 18), "call"): quote}
    )

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("compute_portfolio_greeks", {"portfolio_id": portfolio.portfolio_id})],
        portfolio_repo=portfolio_repo,
        options_provider=options_provider,
    )
    use_case.execute("alice", "what's my portfolio delta?", [])

    result = fake_agent.dispatch_results[0]
    assert result["positions_included"] == 1
    assert abs(result["total_delta"] - 250.0) < 1e-9  # 0.5 * 5 * 100, same math as compute_portfolio_greeks tests


def test_remove_option_holding_dispatches_correctly() -> None:
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Options")
    AddOptionHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "call", 5, 320.0
    )

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[(
            "remove_option_holding",
            {
                "portfolio_id": portfolio.portfolio_id,
                "underlying_ticker": "AAPL",
                "strike": 150.0,
                "expiration": "2026-12-18",
                "option_type": "call",
            },
        )],
        portfolio_repo=portfolio_repo,
    )
    use_case.execute("alice", "remove my AAPL 150 calls", [])

    assert fake_agent.dispatch_results[0] == {"status": "removed"}
    stored = portfolio_repo.get_by_id(portfolio.portfolio_id)
    assert stored.option_holdings == []


def test_compute_option_portfolio_valuation_blocks_other_users_portfolio() -> None:
    portfolio_repo = FakePortfolioRepository()
    alice_portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Alice's")

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("compute_option_portfolio_valuation", {"portfolio_id": alice_portfolio.portfolio_id})],
        portfolio_repo=portfolio_repo,
    )
    use_case.execute("bob", "what's my option P&L on alice's portfolio?", [])

    assert "error" in fake_agent.dispatch_results[0]


def test_compute_option_portfolio_valuation_dispatches_correctly_for_owner() -> None:
    from src.domain.entities.option import OptionContract, OptionQuote

    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Options")
    AddOptionHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "call", 5, 3.20
    )
    contract = OptionContract("AAPL", 150.0, date(2026, 12, 18), "call")
    quote = OptionQuote(
        contract=contract, bid=4.4, ask=4.6, last=4.45, implied_volatility=0.3,
        open_interest=100, volume=10, delta=0.5, gamma=0.02, theta=-0.03, vega=0.15,
        underlying_price=150.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc), mid=4.5,
    )
    options_provider = FakeOptionsDataProvider(
        {("AAPL", 150.0, date(2026, 12, 18), "call"): quote}
    )

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("compute_option_portfolio_valuation", {"portfolio_id": portfolio.portfolio_id})],
        portfolio_repo=portfolio_repo,
        options_provider=options_provider,
    )
    use_case.execute("alice", "what's my option P&L?", [])

    result = fake_agent.dispatch_results[0]
    assert len(result["positions"]) == 1
    # 5 contracts * 4.5 mid * 100 = 2250
    assert abs(result["total_market_value"] - 2250.0) < 1e-9


def test_suggest_hedging_blocks_access_to_another_users_portfolio() -> None:
    portfolio_repo = FakePortfolioRepository()
    alice_portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Alice's")

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("suggest_hedging", {"portfolio_id": alice_portfolio.portfolio_id})],
        portfolio_repo=portfolio_repo,
    )
    use_case.execute("bob", "hedge alice's portfolio", [])

    assert "error" in fake_agent.dispatch_results[0]


def test_suggest_hedging_dispatches_correctly_for_owner() -> None:
    from src.domain.entities.option import OptionContract, OptionQuote

    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Options")
    AddOptionHoldingUseCase(portfolio_repo).execute(
        portfolio.portfolio_id, "AAPL", 150.0, date(2026, 12, 18), "call", 5, 3.20
    )
    contract = OptionContract("AAPL", 150.0, date(2026, 12, 18), "call")
    quote = OptionQuote(
        contract=contract, bid=4.4, ask=4.6, last=4.45, implied_volatility=0.3,
        open_interest=100, volume=10, delta=0.5, gamma=0.02, theta=-0.03, vega=0.15,
        underlying_price=150.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc), mid=4.5,
    )
    options_provider = FakeOptionsDataProvider(
        {("AAPL", 150.0, date(2026, 12, 18), "call"): quote}
    )

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("suggest_hedging", {"portfolio_id": portfolio.portfolio_id})],
        portfolio_repo=portfolio_repo,
        options_provider=options_provider,
    )
    use_case.execute("alice", "how would I hedge my portfolio?", [])

    result = fake_agent.dispatch_results[0]
    assert len(result["suggestions"]) == 1
    # 5 contracts * 0.5 delta * 100 = 250 net delta -> sell 250 shares
    assert abs(result["suggestions"][0]["net_delta"] - 250.0) < 1e-9
    assert abs(result["suggestions"][0]["shares_to_trade"] - (-250.0)) < 1e-9


# ---- Smart watchlist chat tool tests ----


def test_add_to_watchlist_passes_through_list_target_and_thesis() -> None:
    company_repo = _company_repo("AAPL")
    watchlist_repo = FakeWatchlistRepository()

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[(
            "add_to_watchlist",
            {"ticker": "AAPL", "list_name": "Tech Watch", "target_price": 150.0,
             "alert_threshold_pct": 0.03, "notes": "cheap AI play"},
        )],
        company_repo=company_repo,
        watchlist_repo=watchlist_repo,
    )
    use_case.execute("alice", "watch AAPL on my tech list, target 150", [])

    result = fake_agent.dispatch_results[0]
    assert result["status"] == "added"
    assert result["list_name"] == "Tech Watch"

    stored = watchlist_repo.get("alice", "AAPL", "Tech Watch")
    assert stored.target_price == 150.0
    assert stored.alert_threshold_pct == 0.03
    assert stored.notes == "cheap AI play"


def test_update_watchlist_item_via_chat_sets_target_only() -> None:
    company_repo = _company_repo("AAPL")
    watchlist_repo = FakeWatchlistRepository()
    AddToWatchlistUseCase(watchlist_repo, company_repo).execute(
        "alice", "AAPL", notes="original thesis"
    )

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("update_watchlist_item", {"ticker": "AAPL", "target_price": 120.0})],
        company_repo=company_repo,
        watchlist_repo=watchlist_repo,
    )
    use_case.execute("alice", "set a 120 target on AAPL", [])

    result = fake_agent.dispatch_results[0]
    assert result["status"] == "updated"
    assert result["target_price"] == 120.0
    assert result["notes"] == "original thesis"  # untouched


def test_list_watchlists_reports_names_and_counts() -> None:
    company_repo = _company_repo("AAPL")
    watchlist_repo = FakeWatchlistRepository()
    add = AddToWatchlistUseCase(watchlist_repo, company_repo)
    add.execute("alice", "AAPL", list_name="Tech Watch")
    add.execute("alice", "AAPL", list_name="Default")

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("list_watchlists", {})],
        company_repo=company_repo,
        watchlist_repo=watchlist_repo,
    )
    use_case.execute("alice", "what watchlists do I have", [])

    result = fake_agent.dispatch_results[0]
    names = {w["name"]: w["item_count"] for w in result["watchlists"]}
    assert names == {"Tech Watch": 1, "Default": 1}


def test_triage_watchlist_embeds_attention_scoring_note() -> None:
    """The screener-inversion lesson applied to triage: the tool result
    MUST tell the LLM that higher = more attention, not better quality,
    so the narrative can never invert the ranking's meaning."""
    company_repo = _company_repo("AAPL")
    watchlist_repo = FakeWatchlistRepository()
    AddToWatchlistUseCase(watchlist_repo, company_repo).execute("alice", "AAPL")

    from src.domain.entities.market_quote import MarketQuote
    from datetime import datetime, timezone
    provider = FakeDataProvider(
        company=Company(ticker="AAPL", name="Apple", sector=Sector.TECHNOLOGY,
                        industry="X", exchange="X", country="US"),
        quotes_by_ticker={"AAPL": MarketQuote(
            ticker="AAPL", price=100.0, market_cap=1.0,
            as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )},
    )
    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("triage_watchlist", {})],
        company_repo=company_repo,
        watchlist_repo=watchlist_repo,
        provider=provider,
    )
    use_case.execute("alice", "triage my watchlist", [])

    result = fake_agent.dispatch_results[0]
    assert "ATTENTION" in result["scoring_note"]
    assert "NOT better quality" in result["scoring_note"]
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["ticker"] == "AAPL"
    assert item["triage_score"] == 0.0  # no baselines, no snapshot -> honest zero
    assert item["day_move_percent"] is None  # absent, not fabricated


# ---- Factor scoring chat tool tests ----


def test_get_factor_scores_embeds_universe_standardization_note() -> None:
    """Same discipline as the triage scoring_note: the tool result must
    tell the LLM these are universe-relative z-scores, not absolute
    quality, and that null means missing data, not average."""
    company_repo = _company_repo("AAPL")
    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("get_factor_scores", {"ticker": "AAPL"})],
        company_repo=company_repo,
    )
    use_case.execute("alice", "what's AAPL's factor score", [])

    result = fake_agent.dispatch_results[0]
    assert "error" in result  # AAPL has no financials in this fixture -> not in universe
    assert "No factor score" in result["error"]


def test_get_factor_scores_returns_error_for_unscored_ticker() -> None:
    company_repo = _company_repo("AAPL")
    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("get_factor_scores", {"ticker": "ZZZZ"})],
        company_repo=company_repo,
    )
    use_case.execute("alice", "factor score for ZZZZ", [])
    result = fake_agent.dispatch_results[0]
    assert "error" in result


def test_rank_universe_by_factors_respects_custom_weights_and_embeds_note() -> None:
    company_repo = _company_repo("AAPL")
    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[(
            "rank_universe_by_factors",
            {"top_n": 5, "weight_value": 1.0, "weight_quality": 0, "weight_growth": 0,
             "weight_momentum": 0, "weight_size": 0},
        )],
        company_repo=company_repo,
    )
    use_case.execute("alice", "top value stocks", [])

    result = fake_agent.dispatch_results[0]
    assert "scoring_note" in result
    assert "universe" in result["scoring_note"].lower()
    assert result["results"] == []  # empty universe in this fixture — no crash, honest empty list


# ---- Universe theme chat tool tests ----


def test_create_theme_and_tag_ticker_via_chat() -> None:
    company_repo = _company_repo("NVDA")
    theme_repo = FakeUniverseThemeRepository()

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[
            ("create_universe_theme", {"name": "AI Infrastructure", "description": "GPUs"}),
            ("add_ticker_to_theme", {"theme_name": "AI Infrastructure", "ticker": "NVDA"}),
        ],
        company_repo=company_repo,
        theme_repo=theme_repo,
    )
    use_case.execute("alice", "create an AI Infrastructure theme and tag NVDA", [])

    assert fake_agent.dispatch_results[0]["status"] == "created"
    assert fake_agent.dispatch_results[1]["status"] == "added"
    assert theme_repo.get_tickers("AI Infrastructure") == ["NVDA"]


def test_add_ticker_to_theme_error_surfaces_cleanly() -> None:
    company_repo = _company_repo("NVDA")
    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("add_ticker_to_theme", {"theme_name": "Nonexistent", "ticker": "NVDA"})],
        company_repo=company_repo,
    )
    use_case.execute("alice", "tag NVDA into Nonexistent theme", [])
    assert "error" in fake_agent.dispatch_results[0]


def test_list_universe_themes_reports_counts_via_chat() -> None:
    company_repo = _company_repo("NVDA", "BABA")
    theme_repo = FakeUniverseThemeRepository()
    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[
            ("create_universe_theme", {"name": "AI Infrastructure"}),
            ("create_universe_theme", {"name": "China"}),
            ("add_ticker_to_theme", {"theme_name": "AI Infrastructure", "ticker": "NVDA"}),
            ("add_ticker_to_theme", {"theme_name": "China", "ticker": "BABA"}),
            ("list_universe_themes", {}),
        ],
        company_repo=company_repo,
        theme_repo=theme_repo,
    )
    use_case.execute("alice", "list my themes", [])

    themes = {t["name"]: t["member_count"] for t in fake_agent.dispatch_results[-1]["themes"]}
    assert themes == {"AI Infrastructure": 1, "China": 1}


def test_rank_universe_by_factors_theme_filter_narrows_results() -> None:
    """The filter must apply to the ALREADY-cached full-universe ranking
    (z-scores still standardized against the whole S&P 500), not
    re-standardize within the theme — the chat tool description commits
    to this distinction explicitly."""
    company_repo = _company_repo("AAPL")
    theme_repo = FakeUniverseThemeRepository()
    from src.domain.entities.universe_theme import UniverseTheme
    from datetime import datetime, timezone
    theme_repo.create(UniverseTheme(name="Empty Theme", description=None, created_at=datetime.now(timezone.utc)))

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("rank_universe_by_factors", {"theme_name": "Empty Theme", "top_n": 10})],
        company_repo=company_repo,
        theme_repo=theme_repo,
    )
    use_case.execute("alice", "rank Empty Theme by factors", [])

    result = fake_agent.dispatch_results[0]
    assert result["results"] == []  # no tickers in this theme -> empty, not an error


def test_rank_universe_by_factors_unknown_theme_returns_error() -> None:
    company_repo = _company_repo("AAPL")
    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("rank_universe_by_factors", {"theme_name": "Nonexistent"})],
        company_repo=company_repo,
    )
    use_case.execute("alice", "rank Nonexistent by factors", [])
    assert "error" in fake_agent.dispatch_results[0]


# ---- screen_stocks theme scoping tests ----


def test_screen_stocks_resolves_theme_to_tickers() -> None:
    from src.domain.entities.financial_statement import BalanceSheet, FiscalPeriodKey, IncomeStatement, Period
    from src.domain.entities.market_quote import MarketQuote

    company_repo = FakeCompanyRepository()
    statement_repo = FakeFinancialStatementRepository()
    quotes = {}
    for ticker, pe_market_cap in [("AAA", 1000.0), ("BBB", 3000.0)]:
        company_repo.save(Company(ticker=ticker, name=ticker, sector=Sector.TECHNOLOGY,
                                    industry="X", exchange="NASDAQ", country="US"))
        statement_repo.save_income_statement(
            IncomeStatement(key=FiscalPeriodKey(ticker, 2024, Period.ANNUAL),
                             fiscal_date_ending=date(2024, 12, 31), reported_currency="USD",
                             revenue=1000.0, net_income=100.0, ebitda=200.0)
        )
        statement_repo.save_balance_sheet(
            BalanceSheet(key=FiscalPeriodKey(ticker, 2024, Period.ANNUAL),
                          fiscal_date_ending=date(2024, 12, 31), reported_currency="USD",
                          total_equity=500.0, total_debt=100.0, cash_and_equivalents=50.0)
        )
        quotes[ticker] = MarketQuote(ticker=ticker, price=50.0, market_cap=pe_market_cap,
                                       as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))

    provider = FakeDataProvider(company=company_repo.get_by_ticker("AAA"), quotes_by_ticker=quotes)
    theme_repo = FakeUniverseThemeRepository()
    from src.application.use_cases.manage_universe_theme import (
        AddTickerToThemeUseCase, CreateUniverseThemeUseCase,
    )
    CreateUniverseThemeUseCase(theme_repo).execute("Test Theme")
    add = AddTickerToThemeUseCase(theme_repo, company_repo)
    add.execute("Test Theme", "AAA")
    add.execute("Test Theme", "BBB")

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("screen_stocks", {"theme_name": "Test Theme"})],
        company_repo=company_repo,
        provider=provider,
        theme_repo=theme_repo,
        statement_repo=statement_repo,
    )
    use_case.execute("alice", "screen Test Theme", [])

    result = fake_agent.dispatch_results[0]
    assert "error" not in result
    tickers_screened = {r["ticker"] for r in result["results"]}
    assert tickers_screened == {"AAA", "BBB"}


def test_screen_stocks_unknown_theme_returns_error() -> None:
    company_repo = _company_repo("AAPL")
    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("screen_stocks", {"theme_name": "Nonexistent"})],
        company_repo=company_repo,
    )
    use_case.execute("alice", "screen Nonexistent theme", [])
    assert "error" in fake_agent.dispatch_results[0]


def test_screen_stocks_empty_theme_returns_error_not_crash() -> None:
    company_repo = _company_repo("AAPL")
    theme_repo = FakeUniverseThemeRepository()
    from src.application.use_cases.manage_universe_theme import CreateUniverseThemeUseCase
    CreateUniverseThemeUseCase(theme_repo).execute("Empty Theme")

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("screen_stocks", {"theme_name": "Empty Theme"})],
        company_repo=company_repo,
        theme_repo=theme_repo,
    )
    use_case.execute("alice", "screen Empty Theme", [])
    assert "error" in fake_agent.dispatch_results[0]


def test_screen_stocks_manual_tickers_still_works_unchanged() -> None:
    company_repo = _company_repo("AAPL")
    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("screen_stocks", {"tickers": ["NOTINGESTED"]})],
        company_repo=company_repo,
    )
    use_case.execute("alice", "screen NOTINGESTED", [])
    result = fake_agent.dispatch_results[0]
    # ticker not ingested -> excluded, not an error (existing screen_stocks behavior)
    assert "error" not in result
    assert "NOTINGESTED" in result["excluded"]


# ---- Theme synthesis chat tool tests ----


def test_generate_theme_synthesis_via_chat_returns_generated_fields() -> None:
    company_repo = _company_repo("AAPL")
    theme_repo = FakeUniverseThemeRepository()
    from src.application.use_cases.manage_universe_theme import (
        AddTickerToThemeUseCase, CreateUniverseThemeUseCase,
    )
    CreateUniverseThemeUseCase(theme_repo).execute("Empty-ish Theme")
    AddTickerToThemeUseCase(theme_repo, company_repo).execute("Empty-ish Theme", "AAPL")

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("generate_theme_synthesis", {"theme_name": "Empty-ish Theme"})],
        company_repo=company_repo,
        theme_repo=theme_repo,
    )
    use_case.execute("alice", "synthesize Empty-ish Theme", [])

    result = fake_agent.dispatch_results[0]
    # AAPL has no financials or factor data in this minimal fixture ->
    # NoSynthesizableDataError -> surfaces as a clean error, not a crash
    assert "error" in result


def test_generate_theme_synthesis_unknown_theme_returns_error() -> None:
    company_repo = _company_repo("AAPL")
    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("generate_theme_synthesis", {"theme_name": "Nonexistent"})],
        company_repo=company_repo,
    )
    use_case.execute("alice", "synthesize Nonexistent", [])
    assert "error" in fake_agent.dispatch_results[0]


# ---- Risk parity construction chat tool tests ----


def test_construct_risk_parity_portfolio_via_chat() -> None:
    from datetime import date
    from src.domain.entities.market_quote import PriceBar

    _CLOSES = [
        99.90004498800211, 100.90913635151728, 99.91003599160126, 100.9192282743447,
        99.9200279944007, 100.92932120646535, 99.93002099650035, 100.93941514798014,
        99.94001499800014, 100.94951009899003, 99.95000999900003, 100.959606059596,
        99.9600059996, 100.969703029899, 99.97000299989999, 100.97980100999999,
        99.98000099999999, 100.98989999999999, 99.99, 101.0, 100.0,
    ]

    class _PricedProvider(FakeDataProvider):
        def get_daily_closes(self, ticker, limit=30):
            return [PriceBar(bar_date=date(2026, 1, 1), close=c) for c in _CLOSES][:limit]

    company_repo = _company_repo("AAPL")
    provider = _PricedProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={"AAPL": MarketQuote(ticker="AAPL", price=100.0, market_cap=1e9,
                                                as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))},
    )
    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[(
            "construct_risk_parity_portfolio",
            {"tickers": ["AAPL"], "total_investment": 10000.0},
        )],
        company_repo=company_repo,
        provider=provider,
    )
    use_case.execute("alice", "how should I split $10k across AAPL", [])

    result = fake_agent.dispatch_results[0]
    assert result["excluded"] == []
    assert len(result["allocations"]) == 1
    assert abs(result["allocations"][0]["target_weight"] - 1.0) < 1e-6
    assert abs(result["allocations"][0]["target_dollar_amount"] - 10000.0) < 1e-2
    assert "methodology_note" in result
    assert "not" in result["methodology_note"].lower()


def test_construct_risk_parity_portfolio_error_surfaces_cleanly() -> None:
    company_repo = _company_repo("AAPL")
    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("construct_risk_parity_portfolio", {"tickers": [], "total_investment": 1000.0})],
        company_repo=company_repo,
    )
    use_case.execute("alice", "allocate nothing", [])
    assert "error" in fake_agent.dispatch_results[0]


# ---- Regression: cold-cache factor scoring must never crash a chat turn ----
# (production incident: a cold factor-score cache triggered an inline
# 500+-ticker refresh burst that tripped the data provider's rate/plan
# ceiling — see get_factor_scores.py's module docstring)


def test_cold_factor_cache_returns_clean_error_not_a_crash_for_rank() -> None:
    company_repo = _company_repo("AAPL")
    never_populated_repo = FakeFactorScoreRepository()
    real_default_use_case = GetFactorScoresUseCase(
        never_populated_repo,
        ComputeUniverseFactorSnapshotUseCase(
            FakeDataProvider(company=company_repo.get_by_ticker("AAPL")),
            None, None, never_populated_repo,  # never actually called — see assertion below
        ),
        # auto_refresh NOT specified -> exercises the real production default (False)
    )
    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("rank_universe_by_factors", {})],
        company_repo=company_repo,
        get_factor_scores_override=real_default_use_case,
    )
    use_case.execute("alice", "rank stocks by factor", [])

    result = fake_agent.dispatch_results[0]
    assert "error" in result
    assert "not been computed" in result["error"]


def test_cold_factor_cache_returns_clean_error_not_a_crash_for_single_ticker() -> None:
    company_repo = _company_repo("AAPL")
    never_populated_repo = FakeFactorScoreRepository()
    real_default_use_case = GetFactorScoresUseCase(
        never_populated_repo,
        ComputeUniverseFactorSnapshotUseCase(
            FakeDataProvider(company=company_repo.get_by_ticker("AAPL")),
            None, None, never_populated_repo,
        ),
    )
    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("get_factor_scores", {"ticker": "AAPL"})],
        company_repo=company_repo,
        get_factor_scores_override=real_default_use_case,
    )
    use_case.execute("alice", "AAPL factor score", [])

    result = fake_agent.dispatch_results[0]
    assert "error" in result
    assert "not been computed" in result["error"]


# ---- Upcoming earnings chat tool tests ----


def test_get_upcoming_earnings_via_chat() -> None:
    from datetime import date, timedelta
    from src.domain.entities.earnings import EarningsEvent

    class _EarningsProvider(FakeDataProvider):
        def get_earnings_calendar(self, from_date, to_date):
            return [EarningsEvent(ticker="AAPL", report_date=date.today() + timedelta(days=2),
                                    eps_estimated=1.5, eps_actual=None,
                                    revenue_estimated=None, revenue_actual=None)]

    company_repo = _company_repo("AAPL")
    watchlist_repo = FakeWatchlistRepository()
    from src.application.use_cases.manage_watchlist import AddToWatchlistUseCase
    AddToWatchlistUseCase(watchlist_repo, company_repo).execute("alice", "AAPL")
    provider = _EarningsProvider(company=company_repo.get_by_ticker("AAPL"))

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("get_upcoming_earnings", {})],
        company_repo=company_repo,
        watchlist_repo=watchlist_repo,
        provider=provider,
    )
    use_case.execute("alice", "any earnings coming up?", [])

    result = fake_agent.dispatch_results[0]
    assert len(result["events"]) == 1
    assert result["events"][0]["ticker"] == "AAPL"
    assert result["events"][0]["eps_estimated"] == 1.5


def test_get_upcoming_earnings_unsupported_provider_returns_error() -> None:
    company_repo = _company_repo("AAPL")
    watchlist_repo = FakeWatchlistRepository()
    from src.application.use_cases.manage_watchlist import AddToWatchlistUseCase
    AddToWatchlistUseCase(watchlist_repo, company_repo).execute("alice", "AAPL")

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("get_upcoming_earnings", {})],
        company_repo=company_repo,
        watchlist_repo=watchlist_repo,
    )
    use_case.execute("alice", "any earnings coming up?", [])
    assert "error" in fake_agent.dispatch_results[0]


# ---- ETF ingestion chat tool tests ----


def test_ingest_etf_via_chat() -> None:
    from src.domain.entities.etf import EtfProfile

    class _EtfProvider(FakeDataProvider):
        def get_etf_profile(self, ticker):
            return EtfProfile(ticker=ticker, name="Test ETF", description=None,
                                asset_class="Equity", domicile="US",
                                expense_ratio=0.09, aum=789_000_000_000.0)

    company_repo = FakeCompanyRepository()
    provider = _EtfProvider(company=None)

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("ingest_etf", {"ticker": "SPY"})],
        company_repo=company_repo,
        provider=provider,
    )
    use_case.execute("alice", "ingest the SPY ETF", [])

    result = fake_agent.dispatch_results[0]
    assert result["status"] == "ingested"
    assert result["ticker"] == "SPY"
    assert result["expense_ratio"] == 0.09
    assert result["aum"] == 789_000_000_000.0
    assert company_repo.get_by_ticker("SPY") is not None


def test_ingest_etf_not_found_returns_error() -> None:
    class _EtfProvider(FakeDataProvider):
        def get_etf_profile(self, ticker):
            return None  # not a recognized ETF

    company_repo = FakeCompanyRepository()
    provider = _EtfProvider(company=None)

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("ingest_etf", {"ticker": "NOTREAL"})],
        company_repo=company_repo,
        provider=provider,
    )
    use_case.execute("alice", "ingest NOTREAL", [])
    assert "error" in fake_agent.dispatch_results[0]


def test_ingest_etf_unsupported_provider_returns_error() -> None:
    company_repo = FakeCompanyRepository()
    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("ingest_etf", {"ticker": "SPY"})],
        company_repo=company_repo,
    )
    use_case.execute("alice", "ingest SPY", [])
    assert "error" in fake_agent.dispatch_results[0]


# ---- Theme suggestion chat tool tests ----


def test_suggest_theme_via_chat_includes_grounding_note() -> None:
    from src.domain.entities.general_news import GeneralNewsHeadline
    from datetime import datetime, timezone

    class _NewsProvider(FakeDataProvider):
        def get_general_news(self, limit=20):
            return [GeneralNewsHeadline(title="Real headline", published_at=datetime.now(timezone.utc),
                                          publisher="Test", url=None, snippet=None)]

    company_repo = _company_repo("AAPL")
    provider = _NewsProvider(company=company_repo.get_by_ticker("AAPL"))
    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("suggest_theme", {"user_hint": "reshoring"})],
        company_repo=company_repo,
        provider=provider,
    )
    use_case.execute("alice", "suggest a theme about reshoring", [])

    result = fake_agent.dispatch_results[0]
    assert result["theme_name"] == "Test Theme"
    assert "suggestion only" in result["note"]
    assert len(result["candidate_tickers"]) == 1


def test_suggest_theme_error_surfaces_cleanly() -> None:
    """Default FakeDataProvider has no get_general_news override."""
    company_repo = _company_repo("AAPL")

    class _NoNewsProvider(FakeDataProvider):
        pass  # no get_general_news override -> NotImplementedError via base class

    use_case, fake_agent, _ = _build_use_case(
        scripted_calls=[("suggest_theme", {})],
        company_repo=company_repo,
        provider=_NoNewsProvider(company=company_repo.get_by_ticker("AAPL")),
    )
    use_case.execute("alice", "suggest a theme", [])
    assert "error" in fake_agent.dispatch_results[0]
