from __future__ import annotations

from datetime import date, datetime, timezone

from src.application.interfaces.chat_agent import ChatAgent, ChatResult
from src.application.use_cases.chat_with_agent import ChatWithAgentUseCase
from src.application.use_cases.compute_financial_analysis import (
    ComputeFinancialAnalysisUseCase,
)
from src.application.use_cases.compute_portfolio_risk import ComputePortfolioRiskUseCase
from src.application.use_cases.compute_portfolio_valuation import (
    ComputePortfolioValuationUseCase,
)
from src.application.use_cases.compute_valuation import ComputeValuationUseCase
from src.application.use_cases.get_company_financials import GetCompanyFinancialsUseCase
from src.application.use_cases.manage_portfolio import (
    AddHoldingUseCase,
    CreatePortfolioUseCase,
    DeletePortfolioUseCase,
    GetPortfolioUseCase,
    ListPortfoliosUseCase,
)
from src.application.use_cases.manage_watchlist import (
    AddToWatchlistUseCase,
    GetWatchlistUseCase,
    RemoveFromWatchlistUseCase,
)
from src.application.use_cases.screen_stocks import ScreenStocksUseCase
from src.application.use_cases.suggest_rebalancing import SuggestRebalancingUseCase
from src.domain.entities.company import Company, Sector
from src.domain.entities.market_quote import MarketQuote
from tests.unit.fakes import (
    FakeCompanyRepository,
    FakeDataProvider,
    FakeFinancialStatementRepository,
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


def _build_use_case(scripted_calls, company_repo=None, portfolio_repo=None, watchlist_repo=None, provider=None):
    company_repo = company_repo or _company_repo()
    portfolio_repo = portfolio_repo or FakePortfolioRepository()
    watchlist_repo = watchlist_repo or FakeWatchlistRepository()
    statement_repo = FakeFinancialStatementRepository()
    provider = provider or FakeDataProvider(company=Company(ticker="X", name="X", sector=Sector.TECHNOLOGY, industry="X", exchange="X", country="US"))
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

    assert fake_agent.dispatch_results[0] == {"tickers": [{"ticker": "AAPL", "notes": None}]}


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
