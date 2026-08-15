"""In-memory fakes for domain repositories and the data provider.

Testing use cases against these (rather than mocks-of-everything) keeps
tests fast, deterministic, and honest about the actual interface contract
— if a repository interface changes, these fakes fail to implement it and
the test suite won't compile, catching the break immediately.
"""
from __future__ import annotations

from dataclasses import replace

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

    def delete(self, name: str) -> bool:
        name = name.strip()
        if name not in self._themes:
            return False
        del self._themes[name]
        self._memberships = {(t, tk) for (t, tk) in self._memberships if t != name}
        return True


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


class FakeThemeSuggestionGenerator:
    """Records exactly what it was called with — same grounding-
    verification pattern as FakeThemeSynthesisGenerator."""

    def __init__(self, result=None) -> None:
        from src.application.interfaces.theme_suggestion_generator import (
            SuggestedTickerResult,
            ThemeSuggestionGenerationResult,
        )

        self._result = result or ThemeSuggestionGenerationResult(
            theme_name="Test Theme", rationale="Test rationale",
            candidate_tickers=[
                SuggestedTickerResult(ticker="AAA", company_name="AAA Inc", reasoning="Test"),
            ],
            model_used="test-model", raw_response={},
        )
        self.received_headlines = None
        self.received_user_hint = None

    def generate(self, headlines, user_hint):
        self.received_headlines = headlines
        self.received_user_hint = user_hint
        return self._result


class FakeUserRepository:
    def __init__(self) -> None:
        self._users = {}

    def save(self, user) -> None:
        self._users[user.user_id] = user

    def get_by_user_id(self, user_id: str):
        return self._users.get(user_id.strip().lower())

    def list_all(self):
        return list(self._users.values())


class FakeApiKeyRepository:
    def __init__(self) -> None:
        self._keys = []

    def save(self, api_key) -> None:
        self._keys.append(api_key)

    def get_by_hash(self, key_hash: str):
        return next((k for k in self._keys if k.key_hash == key_hash), None)

    def list_for_user(self, user_id: str):
        return [k for k in self._keys if k.user_id == user_id]

    def deactivate_all_for_user(self, user_id: str) -> int:
        count = 0
        for i, k in enumerate(self._keys):
            if k.user_id == user_id and k.is_active:
                self._keys[i] = replace(k, is_active=False)
                count += 1
        return count


class FakeEmailSender:
    """Records every send, and can be configured to fail — used to
    prove RequestPasswordResetUseCase never lets an email failure leak
    account-existence information to the caller."""

    def __init__(self, fail: bool = False) -> None:
        self._fail = fail
        self.sent: list[tuple[str, str, str]] = []  # (to, subject, body)

    def send(self, to: str, subject: str, body_text: str) -> None:
        if self._fail:
            from src.application.interfaces.email_sender import EmailSendError
            raise EmailSendError("simulated send failure")
        self.sent.append((to, subject, body_text))


class FakePasswordResetTokenRepository:
    def __init__(self) -> None:
        self._tokens = {}

    def save(self, token) -> None:
        self._tokens[token.token_hash] = token

    def get_by_hash(self, token_hash: str):
        return self._tokens.get(token_hash)

    def mark_used(self, token_hash: str) -> None:
        existing = self._tokens.get(token_hash)
        if existing is not None:
            self._tokens[token_hash] = replace(existing, used=True)


class FakeSpeculativeGrowthCandidateRepository:
    def __init__(self) -> None:
        self._candidates: dict[tuple[str, str], object] = {}

    def add(self, candidate):
        key = (candidate.user_id, candidate.ticker)
        if key in self._candidates:
            return self._candidates[key]
        self._candidates[key] = candidate
        return candidate

    def remove(self, user_id: str, ticker: str) -> bool:
        key = (user_id, ticker)
        if key in self._candidates:
            del self._candidates[key]
            return True
        return False

    def list_for_user(self, user_id: str) -> list:
        return [c for (u, t), c in self._candidates.items() if u == user_id]

    def update_last_state(
        self, user_id: str, ticker: str, growth_trend, cash_runway_months, market_cap, checked_at
    ) -> None:
        key = (user_id, ticker)
        existing = self._candidates.get(key)
        if existing is not None:
            self._candidates[key] = replace(
                existing,
                last_growth_trend=growth_trend,
                last_cash_runway_months=cash_runway_months,
                last_market_cap=market_cap,
                last_checked_at=checked_at,
            )


class FakeCapitalFlowRepository:
    """Matches the real save_new_events semantics: dedup by dedup_key,
    return only the genuinely new events."""

    def __init__(self) -> None:
        self._seen_dedup_keys: set = set()
        self._saved: list = []

    def save_new_events(self, events: list) -> list:
        new_events = [e for e in events if e.dedup_key not in self._seen_dedup_keys]
        for e in new_events:
            self._seen_dedup_keys.add(e.dedup_key)
        self._saved.extend(new_events)
        return new_events

    def list_recent(self, source=None, limit: int = 50) -> list:
        results = self._saved if source is None else [e for e in self._saved if e.source == source]
        return list(reversed(results))[:limit]


class FakeCapitalFlowMonitorAgent:
    """Scripted per-module results/errors, matching the real
    CapitalFlowMonitorAgent protocol without needing the anthropic
    package installed."""

    def __init__(self, results_by_module_id=None, raise_for_module_ids=None, synthesis_result=None, raise_on_synthesize=False):
        self._results_by_module_id = results_by_module_id or {}
        self._raise_for_module_ids = raise_for_module_ids or set()
        self._synthesis_result = synthesis_result
        self._raise_on_synthesize = raise_on_synthesize
        self.fetch_calls: list = []
        self.synthesize_calls: list = []

    def fetch_module(self, module_def):
        from src.application.interfaces.capital_flow_monitor_agent import CapitalFlowMonitorAgentError
        self.fetch_calls.append(module_def.id)
        if module_def.id in self._raise_for_module_ids:
            raise CapitalFlowMonitorAgentError(f"agent failed for {module_def.id}")
        return self._results_by_module_id[module_def.id]

    def synthesize(self, loaded):
        from src.application.interfaces.capital_flow_monitor_agent import CapitalFlowMonitorAgentError
        self.synthesize_calls.append(loaded)
        if self._raise_on_synthesize:
            raise CapitalFlowMonitorAgentError("synthesis failed")
        return self._synthesis_result


class FakeMacroHistoryProviderForMonitor:
    """Separate from _FakeMacroHistoryProvider in
    test_run_capital_flow_scan.py (that one's local to its own test
    module) — same simple shape, reused here since the Capital Flow
    Monitor's use cases need the identical interface."""

    def __init__(self, readings_by_series=None, raise_on_series=None):
        self._readings_by_series = readings_by_series or {}
        self._raise_on_series = raise_on_series or set()

    def get_series_history(self, series_id: str, limit: int = 24):
        if series_id in self._raise_on_series:
            raise NotImplementedError("not supported")
        return self._readings_by_series.get(series_id, [])[:limit]


class FakeCapitalFlowMonitorSnapshotRepository:
    def __init__(self) -> None:
        self._snapshots: dict = {}  # (user_id, snapshot_date) -> CapitalFlowMonitorSnapshot

    def save_snapshot(self, user_id: str, snapshot) -> None:
        key = (user_id, snapshot.snapshot_date)
        existing = self._snapshots.get(key)
        if existing is None:
            self._snapshots[key] = snapshot
        else:
            from src.domain.entities.capital_flow_monitor import CapitalFlowMonitorSnapshot
            merged_signals = {**existing.signals, **snapshot.signals}
            self._snapshots[key] = CapitalFlowMonitorSnapshot(
                snapshot_date=existing.snapshot_date,
                signals=merged_signals,
                regime_label=snapshot.regime_label if snapshot.regime_label is not None else existing.regime_label,
                regime_stance=snapshot.regime_stance if snapshot.regime_label is not None else existing.regime_stance,
            )

    def list_recent(self, user_id: str, limit: int = 14) -> list:
        mine = [s for (u, _), s in self._snapshots.items() if u == user_id]
        return sorted(mine, key=lambda s: s.snapshot_date, reverse=True)[:limit]


class FakeCapitalFlowMonitorAgentCacheRepository:
    """Matches the real repository's semantics: a shared, GLOBAL cache
    (module_id only, no user scoping) with an age-based TTL check."""

    def __init__(self) -> None:
        self._cache: dict = {}  # module_id -> (result, cached_at)
        self.get_calls: list = []
        self.set_calls: list = []

    def get_cached(self, module_id: str, max_age_seconds: float):
        from datetime import datetime, timezone
        self.get_calls.append(module_id)
        entry = self._cache.get(module_id)
        if entry is None:
            return None
        result, cached_at = entry
        age_seconds = (datetime.now(timezone.utc) - cached_at).total_seconds()
        if age_seconds > max_age_seconds:
            return None
        return result

    def set_cached(self, result) -> None:
        from datetime import datetime, timezone
        self.set_calls.append(result.module_id)
        self._cache[result.module_id] = (result, datetime.now(timezone.utc))


class FakeSecForm13FDownloader:
    def __init__(self, files_by_period: dict | None = None, raise_for_periods: set | None = None) -> None:
        self._files_by_period = files_by_period or {}
        self._raise_for_periods = raise_for_periods or set()
        self.download_calls: list = []

    def download_quarter(self, period_label: str) -> dict:
        from src.infrastructure.data_providers.sec_form_13f_downloader import Form13FDownloadError
        self.download_calls.append(period_label)
        if period_label in self._raise_for_periods:
            raise Form13FDownloadError(f"fake download failure for {period_label}")
        return self._files_by_period[period_label]


class FakeInstitutionalHoldingRepository:
    def __init__(self) -> None:
        self._holdings: list = []
        self.delete_period_calls: list = []
        self.bulk_save_calls: list = []

    def bulk_save(self, holdings: list) -> int:
        self.bulk_save_calls.append(len(holdings))
        self._holdings.extend(holdings)
        return len(holdings)

    def delete_period(self, period_of_report) -> int:
        self.delete_period_calls.append(period_of_report)
        before = len(self._holdings)
        self._holdings = [h for h in self._holdings if h.period_of_report != period_of_report]
        return before - len(self._holdings)

    def get_existing_accession_numbers(self, period_of_report):
        return {h.accession_number for h in self._holdings if h.period_of_report == period_of_report}

    def get_by_cusip(self, cusip: str, period_of_report):
        return [h for h in self._holdings if h.cusip == cusip and h.period_of_report == period_of_report]

    def get_by_filer(self, filer_cik: str, period_of_report):
        return [h for h in self._holdings if h.filer_cik == filer_cik and h.period_of_report == period_of_report]

    def search_by_issuer_name(self, name_query: str, period_of_report, limit: int = 50):
        matches = [
            h for h in self._holdings
            if name_query.lower() in h.issuer_name.lower() and h.period_of_report == period_of_report
        ]
        return sorted(matches, key=lambda h: h.value_usd, reverse=True)[:limit]

    def resolve_issuer_by_name(self, name_query: str, period_of_report):
        matches = [
            h for h in self._holdings
            if name_query.lower() in h.issuer_name.lower() and h.period_of_report == period_of_report
        ]
        if not matches:
            return None
        totals_by_cusip: dict = {}
        for h in matches:
            totals_by_cusip[h.cusip] = totals_by_cusip.get(h.cusip, 0) + h.value_usd
        best_cusip = max(totals_by_cusip, key=lambda c: totals_by_cusip[c])

        from collections import Counter
        name_counts = Counter(h.issuer_name for h in matches if h.cusip == best_cusip)
        best_name = name_counts.most_common(1)[0][0]
        return (best_cusip, best_name)

    def search_by_filer_name(self, name_query: str, period_of_report, limit: int = 50):
        matches = [
            h for h in self._holdings
            if name_query.lower() in h.filer_name.lower() and h.period_of_report == period_of_report
        ]
        return sorted(matches, key=lambda h: h.value_usd, reverse=True)[:limit]

    def resolve_filer_by_name(self, name_query: str, period_of_report):
        matches = [
            h for h in self._holdings
            if name_query.lower() in h.filer_name.lower() and h.period_of_report == period_of_report
        ]
        if not matches:
            return None
        totals_by_cik: dict = {}
        for h in matches:
            totals_by_cik[h.filer_cik] = totals_by_cik.get(h.filer_cik, 0) + h.value_usd
        best_cik = max(totals_by_cik, key=lambda c: totals_by_cik[c])

        from collections import Counter
        name_counts = Counter(h.filer_name for h in matches if h.filer_cik == best_cik)
        best_name = name_counts.most_common(1)[0][0]
        return (best_cik, best_name)

    def get_latest_period_of_report(self):
        periods = {h.period_of_report for h in self._holdings}
        return max(periods) if periods else None

    def get_all_periods_of_report(self):
        periods = {h.period_of_report for h in self._holdings}
        return sorted(periods, reverse=True)

    def get_aggregated_portfolio(self, filer_cik: str, period_of_report):
        from src.domain.entities.aggregated_position import AggregatedPosition

        matches = [
            h for h in self._holdings
            if h.filer_cik == filer_cik and h.period_of_report == period_of_report
        ]
        by_cusip: dict = {}
        for h in matches:
            if h.cusip not in by_cusip:
                by_cusip[h.cusip] = {"issuer_name": h.issuer_name, "shares": 0, "value": 0}
            by_cusip[h.cusip]["shares"] += h.shares_or_principal_amount
            by_cusip[h.cusip]["value"] += h.value_usd
        return [
            AggregatedPosition(
                cusip=cusip, issuer_name=data["issuer_name"],
                total_shares=data["shares"], total_value_usd=data["value"],
            )
            for cusip, data in by_cusip.items()
        ]


class FakeCusipTickerMapRepository:
    def __init__(self):
        self._mappings = {}

    def get(self, cusip: str):
        return self._mappings.get(cusip)

    def get_many(self, cusips: list):
        return {c: self._mappings[c] for c in cusips if c in self._mappings}

    def save(self, mapping) -> None:
        self._mappings[mapping.cusip] = mapping

    def get_unresolved(self, cusips: list) -> list:
        return [c for c in cusips if c not in self._mappings]


class FakeCusipSearchProvider:
    """Stands in for FinancialModelingPrepProvider — only the
    search_cusip method this use case actually calls."""

    def __init__(self, results_by_cusip: dict | None = None):
        self._results_by_cusip = results_by_cusip or {}
        self.search_cusip_calls = []

    def search_cusip(self, cusip: str):
        self.search_cusip_calls.append(cusip)
        return self._results_by_cusip.get(cusip, [])


class FakeFreshnessFallbackProvider:
    """Stands in for FinancialDataProvider — only the one method this
    use case's freshness fallback actually calls."""

    def __init__(self, holdings_by_cik_quarter: dict | None = None, raise_error: Exception | None = None):
        self._holdings_by_cik_quarter = holdings_by_cik_quarter or {}
        self._raise_error = raise_error
        self.calls = []

    def get_institutional_holdings_by_filer(self, cik, year, quarter, filer_name):
        self.calls.append((cik, year, quarter, filer_name))
        if self._raise_error is not None:
            raise self._raise_error
        return self._holdings_by_cik_quarter.get((cik, year, quarter), [])
