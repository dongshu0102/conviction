from __future__ import annotations

from datetime import datetime, timezone

from src.application.use_cases.compute_portfolio_valuation import (
    ComputePortfolioValuationUseCase,
)
from src.application.use_cases.manage_portfolio import AddHoldingUseCase, CreatePortfolioUseCase
from src.application.use_cases.suggest_rebalancing import SuggestRebalancingUseCase
from src.domain.entities.company import Company, Sector
from src.domain.entities.market_quote import MarketQuote
from tests.unit.fakes import FakeCompanyRepository, FakeDataProvider, FakePortfolioRepository


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


def test_no_suggestions_when_well_diversified() -> None:
    """Two equal-weight positions (50/50) — nothing exceeds the 30% default
    threshold's implication of over-concentration... wait, 50% DOES exceed
    30%, so let's use three equal positions (33% each) to genuinely test
    the "nothing to suggest" case at the default threshold boundary."""
    company_repo = _company_repo("AAPL", "MSFT", "GOOGL")
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Diversified")
    add_holding = AddHoldingUseCase(portfolio_repo, company_repo)
    add_holding.execute(portfolio.portfolio_id, "AAPL", shares=10, cost_basis_per_share=100)
    add_holding.execute(portfolio.portfolio_id, "MSFT", shares=10, cost_basis_per_share=100)
    add_holding.execute(portfolio.portfolio_id, "GOOGL", shares=10, cost_basis_per_share=100)

    provider = FakeDataProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={
            "AAPL": MarketQuote(ticker="AAPL", price=100.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
            "MSFT": MarketQuote(ticker="MSFT", price=100.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
            "GOOGL": MarketQuote(ticker="GOOGL", price=100.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        },
    )
    compute_valuation = ComputePortfolioValuationUseCase(portfolio_repo, provider)
    use_case = SuggestRebalancingUseCase(compute_valuation)

    plan = use_case.execute(portfolio.portfolio_id, target_max_weight=0.40)

    # Each position is exactly 33.3% — under the 40% threshold, so no
    # suggestions should be generated.
    assert plan.suggestions == []


def test_suggests_exact_trim_for_concentrated_position() -> None:
    """One position dominates (80% of portfolio) — verify the EXACT
    computed share count and proceeds, hand-calculated:
    total_value = 8000 (AAPL) + 2000 (MSFT) = 10000
    target_max_weight = 0.30 -> target_value = 3000
    excess_value = 8000 - 3000 = 5000
    shares_to_trim = 5000 / 100 (AAPL price) = 50 shares
    estimated_proceeds = 50 * 100 = 5000
    """
    company_repo = _company_repo("AAPL", "MSFT")
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Concentrated")
    add_holding = AddHoldingUseCase(portfolio_repo, company_repo)
    add_holding.execute(portfolio.portfolio_id, "AAPL", shares=80, cost_basis_per_share=50)
    add_holding.execute(portfolio.portfolio_id, "MSFT", shares=20, cost_basis_per_share=50)

    provider = FakeDataProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={
            "AAPL": MarketQuote(ticker="AAPL", price=100.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
            "MSFT": MarketQuote(ticker="MSFT", price=100.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        },
    )
    compute_valuation = ComputePortfolioValuationUseCase(portfolio_repo, provider)
    use_case = SuggestRebalancingUseCase(compute_valuation)

    plan = use_case.execute(portfolio.portfolio_id, target_max_weight=0.30)

    assert len(plan.suggestions) == 1
    suggestion = plan.suggestions[0]
    assert suggestion.ticker == "AAPL"
    assert abs(suggestion.current_weight - 0.8) < 1e-9
    assert suggestion.target_weight == 0.30
    assert abs(suggestion.shares_to_trim - 50.0) < 1e-9
    assert abs(suggestion.estimated_proceeds - 5000.0) < 1e-9
    # MSFT at 20% is under the threshold — no suggestion for it
    assert not any(s.ticker == "MSFT" for s in plan.suggestions)


def test_default_target_weight_is_thirty_percent() -> None:
    company_repo = _company_repo("AAPL")
    portfolio_repo = FakePortfolioRepository()
    portfolio = CreatePortfolioUseCase(portfolio_repo).execute("alice", "Single Holding")
    AddHoldingUseCase(portfolio_repo, company_repo).execute(
        portfolio.portfolio_id, "AAPL", shares=10, cost_basis_per_share=100
    )
    provider = FakeDataProvider(
        company=company_repo.get_by_ticker("AAPL"),
        quotes_by_ticker={"AAPL": MarketQuote(ticker="AAPL", price=100.0, market_cap=1.0, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))},
    )
    compute_valuation = ComputePortfolioValuationUseCase(portfolio_repo, provider)
    use_case = SuggestRebalancingUseCase(compute_valuation)

    plan = use_case.execute(portfolio.portfolio_id)  # no target_max_weight passed

    assert plan.target_max_weight == 0.30
    # 100% weight, single holding — definitely triggers a suggestion
    assert len(plan.suggestions) == 1
