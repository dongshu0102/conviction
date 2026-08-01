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
    FakePriceSnapshotRepository,
    FakeCompanyRepository,
    FakeDataProvider,
    FakeFinancialStatementRepository,
    FakeOptionsDataProvider,
    FakePortfolioRepository,
    FakeResearchReportRepository,
    FakeWatchlistRepository,
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


def _build_use_case(scripted_calls, company_repo=None, portfolio_repo=None, watchlist_repo=None, provider=None, options_provider=None):
    company_repo = company_repo or _company_repo()
    portfolio_repo = portfolio_repo or FakePortfolioRepository()
    watchlist_repo = watchlist_repo or FakeWatchlistRepository()
    statement_repo = FakeFinancialStatementRepository()
    provider = provider or FakeDataProvider(company=Company(ticker="X", name="X", sector=Sector.TECHNOLOGY, industry="X", exchange="X", country="US"))
    options_provider = options_provider or FakeOptionsDataProvider()
    research_repo = FakeResearchReportRepository()

    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    compute_valuation = ComputePortfolioValuationUseCase(portfolio_repo, provider)
    compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)
    compute_risk = ComputePortfolioRiskUseCase(compute_valuation, compute_analysis, company_repo)
    compute_company_valuation = ComputeValuationUseCase(get_financials, provider)

    fake_agent = FakeChatAgent(scripted_calls)
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
