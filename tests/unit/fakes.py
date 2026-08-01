"""In-memory fakes for domain repositories and the data provider.

Testing use cases against these (rather than mocks-of-everything) keeps
tests fast, deterministic, and honest about the actual interface contract
— if a repository interface changes, these fakes fail to implement it and
the test suite won't compile, catching the break immediately.
"""
from __future__ import annotations

from src.application.interfaces.data_provider import FinancialDataProvider
from src.domain.entities.company import Company
from src.domain.entities.financial_statement import (
    BalanceSheet,
    CashFlowStatement,
    IncomeStatement,
    Period,
)
from src.domain.repositories.company_repository import CompanyRepository
from src.domain.repositories.financial_statement_repository import (
    FinancialStatementRepository,
)


class FakeCompanyRepository(CompanyRepository):
    def __init__(self) -> None:
        self._store: dict[str, Company] = {}

    def save(self, company: Company) -> None:
        self._store[company.ticker] = company

    def get_by_ticker(self, ticker: str) -> Company | None:
        return self._store.get(ticker.strip().upper())

    def list_all(self, active_only: bool = True) -> list[Company]:
        values = list(self._store.values())
        return [c for c in values if c.is_active] if active_only else values


class FakeFinancialStatementRepository(FinancialStatementRepository):
    def __init__(self) -> None:
        self.income_statements: list[IncomeStatement] = []
        self.balance_sheets: list[BalanceSheet] = []
        self.cash_flow_statements: list[CashFlowStatement] = []

    def save_income_statement(self, statement: IncomeStatement) -> None:
        self.income_statements = [
            s for s in self.income_statements if s.key != statement.key
        ] + [statement]

    def save_balance_sheet(self, statement: BalanceSheet) -> None:
        self.balance_sheets = [
            s for s in self.balance_sheets if s.key != statement.key
        ] + [statement]

    def save_cash_flow_statement(self, statement: CashFlowStatement) -> None:
        self.cash_flow_statements = [
            s for s in self.cash_flow_statements if s.key != statement.key
        ] + [statement]

    def get_income_statements(
        self, ticker: str, period: Period = Period.ANNUAL, limit: int = 5
    ) -> list[IncomeStatement]:
        matches = [
            s for s in self.income_statements
            if s.key.ticker == ticker.strip().upper() and s.key.period == period
        ]
        return sorted(matches, key=lambda s: s.fiscal_date_ending, reverse=True)[:limit]

    def get_balance_sheets(
        self, ticker: str, period: Period = Period.ANNUAL, limit: int = 5
    ) -> list[BalanceSheet]:
        matches = [
            s for s in self.balance_sheets
            if s.key.ticker == ticker.strip().upper() and s.key.period == period
        ]
        return sorted(matches, key=lambda s: s.fiscal_date_ending, reverse=True)[:limit]

    def get_cash_flow_statements(
        self, ticker: str, period: Period = Period.ANNUAL, limit: int = 5
    ) -> list[CashFlowStatement]:
        matches = [
            s for s in self.cash_flow_statements
            if s.key.ticker == ticker.strip().upper() and s.key.period == period
        ]
        return sorted(matches, key=lambda s: s.fiscal_date_ending, reverse=True)[:limit]


class FakeDataProvider(FinancialDataProvider):
    def __init__(
        self,
        company: Company,
        income_statements: list[IncomeStatement] | None = None,
        balance_sheets: list[BalanceSheet] | None = None,
        cash_flow_statements: list[CashFlowStatement] | None = None,
        sp500_tickers: list[str] | None = None,
        quote=None,
        quotes_by_ticker: dict | None = None,
    ) -> None:
        self._company = company
        self._income_statements = income_statements or []
        self._balance_sheets = balance_sheets or []
        self._cash_flow_statements = cash_flow_statements or []
        self._sp500_tickers = sp500_tickers or []
        self._quote = quote
        self._quotes_by_ticker = quotes_by_ticker or {}

    def get_company_profile(self, ticker: str) -> Company:
        return self._company

    def get_income_statements(
        self, ticker: str, period: Period, limit: int
    ) -> list[IncomeStatement]:
        return self._income_statements[:limit]

    def get_balance_sheets(
        self, ticker: str, period: Period, limit: int
    ) -> list[BalanceSheet]:
        return self._balance_sheets[:limit]

    def get_cash_flow_statements(
        self, ticker: str, period: Period, limit: int
    ) -> list[CashFlowStatement]:
        return self._cash_flow_statements[:limit]

    def get_sp500_constituent_tickers(self) -> list[str]:
        return self._sp500_tickers

    def get_quote(self, ticker: str):
        if ticker in self._quotes_by_ticker:
            return self._quotes_by_ticker[ticker]
        if self._quote is None:
            raise AssertionError("FakeDataProvider.get_quote called without a quote configured")
        return self._quote


class FakeResearchReportRepository:
    def __init__(self) -> None:
        self._reports: list = []

    def save(self, report) -> None:
        self._reports.append(report)

    def get_latest(self, ticker: str):
        matches = [r for r in self._reports if r.ticker == ticker.strip().upper()]
        return max(matches, key=lambda r: r.generated_at) if matches else None

    def list_history(self, ticker: str, limit: int = 10) -> list:
        matches = [r for r in self._reports if r.ticker == ticker.strip().upper()]
        return sorted(matches, key=lambda r: r.generated_at, reverse=True)[:limit]


class FakeResearchGenerator:
    """Records exactly what CompanyFinancials it was called with — this is
    what lets tests assert the grounding guarantee: the LLM adapter is
    never reachable without real financial data passed to it.
    """

    def __init__(self, result=None) -> None:
        from src.application.interfaces.research_generator import ResearchGenerationResult

        self._result = result or ResearchGenerationResult(
            business_overview="Test overview",
            financial_highlights="Test highlights",
            competitive_position="Test position",
            key_risks="Test risks",
            model_used="fake-model",
            raw_response={},
        )
        self.received_financials = None

    def generate(self, financials):
        self.received_financials = financials
        return self._result


class ScriptedFailureDataProvider(FinancialDataProvider):
    """Data provider whose behavior per ticker is scripted in advance —
    used to test retry/backoff and partial-failure isolation without
    real network calls or real timing.
    """

    def __init__(self, company: Company, behaviors: dict[str, list[Exception | None]]) -> None:
        self._company = company
        # Each ticker maps to a list of outcomes consumed one per call —
        # e.g. [TimeoutError(...), None] means "fail once, then succeed."
        self._behaviors = {k: list(v) for k, v in behaviors.items()}
        self.call_counts: dict[str, int] = {k: 0 for k in behaviors}

    def _next_outcome(self, ticker: str) -> None:
        self.call_counts[ticker] = self.call_counts.get(ticker, 0) + 1
        queue = self._behaviors.get(ticker, [])
        if queue:
            outcome = queue.pop(0)
            if outcome is not None:
                raise outcome

    def get_company_profile(self, ticker: str) -> Company:
        self._next_outcome(ticker)
        return self._company

    def get_income_statements(self, ticker: str, period: Period, limit: int) -> list[IncomeStatement]:
        return []

    def get_balance_sheets(self, ticker: str, period: Period, limit: int) -> list[BalanceSheet]:
        return []

    def get_cash_flow_statements(self, ticker: str, period: Period, limit: int) -> list[CashFlowStatement]:
        return []

    def get_sp500_constituent_tickers(self) -> list[str]:
        return sorted(self._behaviors.keys())

    def get_quote(self, ticker: str):
        raise NotImplementedError("ScriptedFailureDataProvider does not support get_quote")


class FakeWatchlistRepository:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str, str], object] = {}  # (user_id, list_name, ticker)

    def add(self, item) -> None:
        self._items[(item.user_id, item.list_name, item.ticker)] = item

    def remove(self, user_id: str, ticker: str, list_name: str | None = None) -> bool:
        ticker = ticker.strip().upper()
        keys = [
            k for k in self._items
            if k[0] == user_id and k[2] == ticker and (list_name is None or k[1] == list_name)
        ]
        for k in keys:
            del self._items[k]
        return bool(keys)

    def get(self, user_id: str, ticker: str, list_name: str):
        return self._items.get((user_id, list_name, ticker.strip().upper()))

    def list_for_user(self, user_id: str, list_name: str | None = None) -> list:
        return [
            item for (uid, lname, _), item in self._items.items()
            if uid == user_id and (list_name is None or lname == list_name)
        ]

    def contains(self, user_id: str, ticker: str) -> bool:
        ticker = ticker.strip().upper()
        return any(k[0] == user_id and k[2] == ticker for k in self._items)


class FakePortfolioRepository:
    def __init__(self) -> None:
        self._portfolios: dict = {}   # portfolio_id -> Portfolio (with holdings)

    def create(self, portfolio) -> None:
        self._portfolios[portfolio.portfolio_id] = portfolio

    def get_by_id(self, portfolio_id: str):
        return self._portfolios.get(portfolio_id)

    def list_for_user(self, user_id: str) -> list:
        return [p for p in self._portfolios.values() if p.user_id == user_id]

    def delete(self, portfolio_id: str) -> bool:
        if portfolio_id in self._portfolios:
            del self._portfolios[portfolio_id]
            return True
        return False

    def upsert_holding(self, portfolio_id: str, holding) -> None:
        from dataclasses import replace

        portfolio = self._portfolios[portfolio_id]
        remaining = [h for h in portfolio.holdings if h.ticker != holding.ticker]
        self._portfolios[portfolio_id] = replace(portfolio, holdings=remaining + [holding])

    def remove_holding(self, portfolio_id: str, ticker: str) -> bool:
        from dataclasses import replace

        portfolio = self._portfolios[portfolio_id]
        remaining = [h for h in portfolio.holdings if h.ticker != ticker]
        removed = len(remaining) != len(portfolio.holdings)
        self._portfolios[portfolio_id] = replace(portfolio, holdings=remaining)
        return removed

    def _same_contract(self, a, b) -> bool:
        return (
            a.underlying_ticker == b.underlying_ticker
            and a.strike == b.strike
            and a.expiration == b.expiration
            and a.option_type == b.option_type
        )

    def upsert_option_holding(self, portfolio_id: str, holding) -> None:
        from dataclasses import replace

        portfolio = self._portfolios[portfolio_id]
        remaining = [
            h for h in portfolio.option_holdings
            if not self._same_contract(h.contract, holding.contract)
        ]
        self._portfolios[portfolio_id] = replace(
            portfolio, option_holdings=remaining + [holding]
        )

    def remove_option_holding(self, portfolio_id: str, contract) -> bool:
        from dataclasses import replace

        portfolio = self._portfolios[portfolio_id]
        remaining = [
            h for h in portfolio.option_holdings if not self._same_contract(h.contract, contract)
        ]
        removed = len(remaining) != len(portfolio.option_holdings)
        self._portfolios[portfolio_id] = replace(portfolio, option_holdings=remaining)
        return removed


class FakeOptionsDataProvider:
    def __init__(self, quotes: dict | None = None) -> None:
        # keyed by (underlying_ticker, strike, expiration, option_type)
        self._quotes = quotes or {}

    def _key(self, contract):
        return (contract.underlying_ticker, contract.strike, contract.expiration, contract.option_type)

    def get_option_chain(self, underlying_ticker: str, expiration=None) -> list:
        return [q for k, q in self._quotes.items() if k[0] == underlying_ticker]

    def get_option_quote(self, contract):
        return self._quotes.get(self._key(contract))


class FakePriceSnapshotRepository:
    def __init__(self) -> None:
        self._snapshots: dict = {}  # ticker -> PriceSnapshot

    def get_latest(self, ticker: str):
        return self._snapshots.get(ticker)

    def save(self, snapshot) -> None:
        self._snapshots[snapshot.ticker] = snapshot


class FakeAlertRepository:
    def __init__(self) -> None:
        self._alerts: list = []
        self._next_id = 1

    def save(self, alert):
        from dataclasses import replace

        saved = replace(alert, id=self._next_id)
        self._next_id += 1
        self._alerts.append(saved)
        return saved

    def list_for_user(self, user_id: str, unread_only: bool = False) -> list:
        results = [a for a in self._alerts if a.user_id == user_id]
        if unread_only:
            results = [a for a in results if not a.is_read]
        return results

    def mark_read(self, user_id: str, alert_id: int) -> bool:
        from dataclasses import replace

        for i, alert in enumerate(self._alerts):
            if alert.user_id == user_id and alert.id == alert_id:
                self._alerts[i] = replace(alert, is_read=True)
                return True
        return False


class FakeBriefGenerator:
    """Records exactly what structured data it was called with — same
    grounding-verification pattern as FakeResearchGenerator."""

    def __init__(self, narrative: str = "Test brief narrative.") -> None:
        self._narrative = narrative
        self.received_watchlist_moves = None
        self.received_portfolio_summaries = None
        self.received_alert_count = None

    def generate(self, watchlist_moves, portfolio_summaries, unread_alert_count):
        from src.application.interfaces.brief_generator import BriefGenerationResult

        self.received_watchlist_moves = watchlist_moves
        self.received_portfolio_summaries = portfolio_summaries
        self.received_alert_count = unread_alert_count
        return BriefGenerationResult(narrative=self._narrative, model_used="fake-model")


class FakeFactorScoreRepository:
    def __init__(self) -> None:
        self._scores: dict[str, object] = {}
        self._latest_as_of = None

    def save_batch(self, scores: list) -> None:
        self._scores = {s.ticker: s for s in scores}
        self._latest_as_of = scores[0].as_of if scores else None

    def get_latest_as_of(self):
        return self._latest_as_of

    def get(self, ticker: str):
        return self._scores.get(ticker.strip().upper())

    def get_all(self) -> list:
        return list(self._scores.values())


class FakeUniverseThemeRepository:
    def __init__(self) -> None:
        self._themes: dict[str, object] = {}
        self._memberships: set[tuple[str, str]] = set()  # (theme_name, ticker)

    def create(self, theme) -> None:
        if theme.name not in self._themes:
            self._themes[theme.name] = theme

    def get(self, name: str):
        return self._themes.get(name.strip())

    def list_all(self) -> list:
        from src.domain.entities.universe_theme import UniverseThemeSummary
        return [
            UniverseThemeSummary(
                theme=theme,
                member_count=sum(1 for (t, _) in self._memberships if t == name),
            )
            for name, theme in self._themes.items()
        ]

    def add_ticker(self, theme_name: str, ticker: str) -> None:
        self._memberships.add((theme_name, ticker.strip().upper()))

    def remove_ticker(self, theme_name: str, ticker: str) -> bool:
        key = (theme_name, ticker.strip().upper())
        if key in self._memberships:
            self._memberships.discard(key)
            return True
        return False

    def get_tickers(self, theme_name: str) -> list[str]:
        return sorted(t for (name, t) in self._memberships if name == theme_name)

    def get_themes_for_ticker(self, ticker: str) -> list[str]:
        ticker = ticker.strip().upper()
        return sorted(name for (name, t) in self._memberships if t == ticker)


class FakeThemeSynthesisGenerator:
    """Records exactly what tickers it was called with — same
    grounding-verification pattern as FakeResearchGenerator."""

    def __init__(self, result=None) -> None:
        from src.application.interfaces.theme_synthesis_generator import (
            ThemeSynthesisGenerationResult,
        )

        self._result = result or ThemeSynthesisGenerationResult(
            overview="Test overview", common_threads="Test threads",
            notable_divergences="Test divergences", key_risks="Test risks",
            model_used="test-model", raw_response={},
        )
        self.received_theme_name = None
        self.received_theme_description = None
        self.received_tickers = None

    def generate(self, theme_name, theme_description, tickers):
        self.received_theme_name = theme_name
        self.received_theme_description = theme_description
        self.received_tickers = tickers
        return self._result
