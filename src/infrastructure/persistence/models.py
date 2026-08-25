"""SQLAlchemy ORM models.

These are intentionally NOT the domain entities. Keeping them separate
(and mapping between them in the repository implementations) means a
schema migration or an ORM-level quirk never leaks into domain or
application code — only infrastructure/persistence/*_repository_impl.py
know both shapes exist.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.persistence.database import Base


class CompanyModel(Base):
    __tablename__ = "companies"

    ticker: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str] = mapped_column(String(64), nullable=False)
    industry: Mapped[str] = mapped_column(String(128), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    country: Mapped[str] = mapped_column(String(64), nullable=False)
    ipo_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    asset_type: Mapped[str] = mapped_column(String(16), nullable=False, default="EQUITY", server_default="EQUITY")
    expense_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    aum: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    income_statements: Mapped[list["IncomeStatementModel"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    balance_sheets: Mapped[list["BalanceSheetModel"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    cash_flow_statements: Mapped[list["CashFlowStatementModel"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class UserModel(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)  # normalized email
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, server_default="user")


class PasswordResetTokenModel(Base):
    __tablename__ = "password_reset_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ApiKeyModel(Base):
    __tablename__ = "api_keys"

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    key_prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ResearchReportModel(Base):
    __tablename__ = "research_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(ForeignKey("companies.ticker"), nullable=False, index=True)
    business_overview: Mapped[str] = mapped_column(String, nullable=False)
    financial_highlights: Mapped[str] = mapped_column(String, nullable=False)
    competitive_position: Mapped[str] = mapped_column(String, nullable=False)
    key_risks: Mapped[str] = mapped_column(String, nullable=False)
    model_used: Mapped[str] = mapped_column(String(64), nullable=False)
    grounded_fiscal_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class PriceSnapshotModel(Base):
    __tablename__ = "price_snapshots"

    ticker: Mapped[str] = mapped_column(ForeignKey("companies.ticker"), primary_key=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class AlertModel(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(ForeignKey("companies.ticker"), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(String, nullable=False)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class PortfolioModel(Base):
    __tablename__ = "portfolios"

    portfolio_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    holdings: Mapped[list["PortfolioHoldingModel"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )
    option_holdings: Mapped[list["OptionHoldingModel"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )


class PortfolioHoldingModel(Base):
    __tablename__ = "portfolio_holdings"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "ticker", name="uq_portfolio_holding_ticker"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portfolio_id: Mapped[str] = mapped_column(
        ForeignKey("portfolios.portfolio_id"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(ForeignKey("companies.ticker"), nullable=False)
    shares: Mapped[float] = mapped_column(Float, nullable=False)
    cost_basis_per_share: Mapped[float] = mapped_column(Float, nullable=False)
    acquired_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    portfolio: Mapped["PortfolioModel"] = relationship(back_populates="holdings")


class OptionHoldingModel(Base):
    __tablename__ = "option_holdings"
    __table_args__ = (
        UniqueConstraint(
            "portfolio_id", "underlying_ticker", "strike", "expiration", "option_type",
            name="uq_option_holding_contract",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portfolio_id: Mapped[str] = mapped_column(
        ForeignKey("portfolios.portfolio_id"), nullable=False, index=True
    )
    # Not a ForeignKey to companies.ticker like stock holdings — options
    # can exist on indices/ETFs that aren't in our ingested company
    # universe, and the underlying doesn't need to be "known" to us for
    # us to track a position in an option on it.
    underlying_ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    strike: Mapped[float] = mapped_column(Float, nullable=False)
    expiration: Mapped[date] = mapped_column(Date, nullable=False)
    option_type: Mapped[str] = mapped_column(String(4), nullable=False)  # "call" or "put"
    contracts_held: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_basis_per_contract: Mapped[float] = mapped_column(Float, nullable=False)
    acquired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    portfolio: Mapped["PortfolioModel"] = relationship(back_populates="option_holdings")


class WatchlistItemModel(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("user_id", "list_name", "ticker", name="uq_watchlist_user_list_ticker"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(ForeignKey("companies.ticker"), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    list_name: Mapped[str] = mapped_column(String(128), nullable=False, default="Default", server_default="Default")
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    alert_threshold_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    added_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    added_pe: Mapped[float | None] = mapped_column(Float, nullable=True)


class IncomeStatementModel(Base):
    __tablename__ = "income_statements"
    __table_args__ = (
        UniqueConstraint("ticker", "fiscal_year", "fiscal_quarter", "period", name="uq_income_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(ForeignKey("companies.ticker"), nullable=False, index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_quarter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    period: Mapped[str] = mapped_column(String(16), nullable=False)
    fiscal_date_ending: Mapped[date] = mapped_column(Date, nullable=False)
    reported_currency: Mapped[str] = mapped_column(String(8), nullable=False)

    revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_of_revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    operating_expenses: Mapped[float | None] = mapped_column(Float, nullable=True)
    operating_income: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_income: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps_basic: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps_diluted: Mapped[float | None] = mapped_column(Float, nullable=True)
    ebitda: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    company: Mapped["CompanyModel"] = relationship(back_populates="income_statements")


class BalanceSheetModel(Base):
    __tablename__ = "balance_sheets"
    __table_args__ = (
        UniqueConstraint("ticker", "fiscal_year", "fiscal_quarter", "period", name="uq_balance_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(ForeignKey("companies.ticker"), nullable=False, index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_quarter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    period: Mapped[str] = mapped_column(String(16), nullable=False)
    fiscal_date_ending: Mapped[date] = mapped_column(Date, nullable=False)
    reported_currency: Mapped[str] = mapped_column(String(8), nullable=False)

    total_assets: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_current_assets: Mapped[float | None] = mapped_column(Float, nullable=True)
    cash_and_equivalents: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_liabilities: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_current_liabilities: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_debt: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_equity: Mapped[float | None] = mapped_column(Float, nullable=True)
    shares_outstanding: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    company: Mapped["CompanyModel"] = relationship(back_populates="balance_sheets")


class CashFlowStatementModel(Base):
    __tablename__ = "cash_flow_statements"
    __table_args__ = (
        UniqueConstraint("ticker", "fiscal_year", "fiscal_quarter", "period", name="uq_cashflow_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(ForeignKey("companies.ticker"), nullable=False, index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_quarter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    period: Mapped[str] = mapped_column(String(16), nullable=False)
    fiscal_date_ending: Mapped[date] = mapped_column(Date, nullable=False)
    reported_currency: Mapped[str] = mapped_column(String(8), nullable=False)

    operating_cash_flow: Mapped[float | None] = mapped_column(Float, nullable=True)
    capital_expenditures: Mapped[float | None] = mapped_column(Float, nullable=True)
    free_cash_flow: Mapped[float | None] = mapped_column(Float, nullable=True)
    dividends_paid: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_change_in_cash: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    company: Mapped["CompanyModel"] = relationship(back_populates="cash_flow_statements")


class FactorScoreModel(Base):
    """Latest-only cache: one row per ticker, overwritten on each
    universe refresh (same pattern as PriceSnapshotModel's
    get_latest/save). as_of is duplicated across every row in a batch
    so staleness can be read from any single row without a separate
    metadata table — the batch's freshness is queried as
    MAX(as_of) or, equivalently since all rows share one value,
    any row's as_of.
    """

    __tablename__ = "factor_scores"

    ticker: Mapped[str] = mapped_column(
        ForeignKey("companies.ticker"), primary_key=True
    )
    as_of: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    price_to_earnings: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_on_equity: Mapped[float | None] = mapped_column(Float, nullable=True)
    revenue_growth_yoy: Mapped[float | None] = mapped_column(Float, nullable=True)
    momentum_1m_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)

    value_z: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_z: Mapped[float | None] = mapped_column(Float, nullable=True)
    growth_z: Mapped[float | None] = mapped_column(Float, nullable=True)
    momentum_z: Mapped[float | None] = mapped_column(Float, nullable=True)
    size_z: Mapped[float | None] = mapped_column(Float, nullable=True)


class UniverseThemeModel(Base):
    __tablename__ = "universe_themes"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class UniverseThemeMembershipModel(Base):
    __tablename__ = "universe_theme_memberships"
    __table_args__ = (
        UniqueConstraint("theme_name", "ticker", name="uq_theme_membership_theme_ticker"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    theme_name: Mapped[str] = mapped_column(
        ForeignKey("universe_themes.name"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(
        ForeignKey("companies.ticker"), nullable=False, index=True
    )


class SpeculativeGrowthCandidateModel(Base):
    __tablename__ = "speculative_growth_candidates"
    __table_args__ = (
        UniqueConstraint("user_id", "ticker", name="uq_growth_candidate_user_ticker"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Last-known state for change detection — nullable because the
    # domain entity itself allows null (no baseline exists before the
    # very first check), not because the fields are ever optional at
    # write time once a real assessment has run.
    last_growth_trend: Mapped[str | None] = mapped_column(String, nullable=True)
    last_cash_runway_months: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CapitalFlowEventModel(Base):
    __tablename__ = "capital_flow_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Deliberately NOT a ForeignKey to companies.ticker, unlike
    # AlertModel.ticker — this is a broad, market-wide scan, so most
    # symbols it detects were never ingested into this platform's own
    # companies table at all. A foreign key here would make a real
    # insert fail for the common case, not the exception.
    symbol: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    headline: Mapped[str] = mapped_column(String, nullable=False)
    detail_url: Mapped[str | None] = mapped_column(String, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    # The dedup key IS the mechanism that prevents the same real-world
    # event from being persisted twice across separate scan runs — a
    # unique constraint here is a real, enforced guarantee, not just a
    # convention the application layer happens to follow.
    dedup_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    # Nullable, matching the domain entity's own None-for-not-applicable
    # convention — only ever True/False for SENATE/HOUSE events, where
    # a real STOCK Act deadline exists; genuinely None for every other
    # source (INSIDER, VOLUME, MACRO have no equivalent disclosure
    # deadline), never a fabricated False standing in for "not applicable."
    is_late_filing: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class CapitalFlowMonitorSnapshotModel(Base):
    """One saved day's Capital Flow Monitor board, per user — matches
    this platform's existing per-user pattern (watchlist, alerts,
    growth candidates), not a shared global board. Replaces the
    original artifact's window.storage persistence with real Postgres.
    """

    __tablename__ = "capital_flow_monitor_snapshots"
    __table_args__ = (
        UniqueConstraint("user_id", "snapshot_date", name="uq_cfm_snapshot_user_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # {module_id: [headline_value, headline_direction, as_of]} — a plain
    # JSON-serializable dict, matching the artifact's original compact
    # per-module shape (v/d/as_of) rather than the full module result.
    signals: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    regime_label: Mapped[str | None] = mapped_column(String, nullable=True)
    regime_stance: Mapped[str | None] = mapped_column(String(16), nullable=True)


class CapitalFlowMonitorAgentCacheModel(Base):
    """A shared, GLOBAL cache (module_id is the primary key — no
    user_id at all) for the Capital Flow Monitor's 9 agent-backed
    module results. Deliberately a separate table from
    CapitalFlowMonitorSnapshotModel, which is per-user history — this
    is a different concern (shared cost-saving cache), not a personal
    record."""

    __tablename__ = "capital_flow_monitor_agent_cache"

    module_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    # The full CapitalFlowMonitorModuleResult, serialized — see
    # capital_flow_monitor_repository_impl.py's _result_to_json /
    # _json_to_result for the exact shape.
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    cached_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class Form13FHoldingModel(Base):
    """One real, disclosed institutional holding from SEC's own free
    quarterly Form 13F data sets — bulk-ingested, not a live per-
    request API. No foreign key to `companies` — 13F holdings are
    identified by CUSIP, and this dataset has no ticker symbol at all,
    so there is no reliable join key against this platform's own
    ticker-keyed companies table without a separate CUSIP-to-ticker
    mapping this build deliberately does not attempt yet.

    Deliberately no DB-level unique constraint: a manager can
    genuinely report the same CUSIP+class more than once within one
    filing (e.g. a shared-discretion position split across different
    voting-authority arrangements), so a too-strict constraint risked
    hard-failing ingestion on real, legitimate data. Idempotent
    re-ingestion is instead handled at the application level — see
    scripts/ingest_form_13f.py, which deletes any existing rows for an
    accession_number before re-inserting it."""

    __tablename__ = "form_13f_holdings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cik: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    filer_name: Mapped[str] = mapped_column(String, nullable=False)
    period_of_report: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    accession_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name_of_issuer: Mapped[str] = mapped_column(String, nullable=False)
    title_of_class: Mapped[str] = mapped_column(String(32), nullable=False)
    cusip: Mapped[str] = mapped_column(String(9), nullable=False, index=True)
    value_usd: Mapped[float] = mapped_column(Float, nullable=False)
    shares_or_principal_amt: Mapped[float] = mapped_column(Float, nullable=False)
    shares_or_principal_type: Mapped[str] = mapped_column(String(8), nullable=False)
    put_call: Mapped[str | None] = mapped_column(String(8), nullable=True)
    investment_discretion: Mapped[str] = mapped_column(String(16), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class InstitutionalHoldingModel(Base):
    """One row from a Form 13F information table -- one security held
    by one institutional manager as of one quarter-end. Global data,
    not user-scoped (matches CapitalFlowEventModel's pattern, not the
    per-user Capital Flow Monitor snapshot pattern) -- these are
    public SEC filings, the same for every user.

    No unique constraint on (accession_number, cusip): a single filing
    can legitimately report the same CUSIP more than once (e.g. split
    across different investment_discretion or put_call rows) -- a
    surrogate primary key is the honest choice here, not an assumed
    uniqueness that might not hold.

    value_usd, shares_or_principal_amount, and voting_authority_* are
    BigInteger, not Integer -- confirmed as a real, necessary fix
    against actual production data: a single mega-fund's position in
    a mega-cap stock genuinely exceeds standard 32-bit INTEGER's
    ~2.147 billion range (a real ingestion run hit
    psycopg2.errors.NumericValueOutOfRange on exactly this)."""

    __tablename__ = "institutional_holdings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    accession_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    filer_cik: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    filer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    period_of_report: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    issuer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    title_of_class: Mapped[str] = mapped_column(String(150), nullable=False)
    cusip: Mapped[str] = mapped_column(String(9), nullable=False, index=True)
    value_usd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    shares_or_principal_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    share_type: Mapped[str] = mapped_column(String(10), nullable=False)
    put_call: Mapped[str | None] = mapped_column(String(10), nullable=True)
    investment_discretion: Mapped[str] = mapped_column(String(20), nullable=False)
    voting_authority_sole: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    voting_authority_shared: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    voting_authority_none: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class CusipTickerMapModel(Base):
    """A resolved (or genuinely attempted-and-failed) CUSIP-to-ticker
    mapping. Supplements the free, bulk-ingested SEC 13F pipeline,
    which has no ticker at all in its own raw data, with real ticker
    symbols from FMP's Ultimate-tier search-cusip endpoint. One row
    per unique CUSIP, resolved once and cached — not re-queried on
    every read, since there are far fewer distinct CUSIPs than
    institutional_holdings rows.

    ticker is nullable, and a NULL value is a real, meaningful,
    different state from no row existing at all: it means resolution
    was genuinely attempted and no US-listed ticker was found (see
    pick_primary_us_ticker's own docstring), so it will not be
    silently retried on every future ingestion run."""

    __tablename__ = "cusip_ticker_map"

    cusip: Mapped[str] = mapped_column(String(9), primary_key=True, nullable=False)
    ticker: Mapped[str | None] = mapped_column(String(16), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(), nullable=True)
    resolved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ConvictionScreenerResultModel(Base):
    """Latest-only cache, same pattern as FactorScoreModel: one row per
    ticker, overwritten on each full-universe screener run, with a
    shared as_of timestamp so staleness is honestly knowable from any
    single row. Lightweight by design -- only the three booleans and
    the tally, not the full holder/disclosure/transaction detail
    (which stays live-only, fetched fresh from GetConvictionSummaryUseCase
    when a single ticker's full detail is actually requested)."""

    __tablename__ = "conviction_screener_results"

    ticker: Mapped[str] = mapped_column(ForeignKey("companies.ticker"), primary_key=True)
    as_of: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    institutional_signal: Mapped[bool] = mapped_column(Boolean, nullable=False)
    activist_signal: Mapped[bool] = mapped_column(Boolean, nullable=False)
    insider_signal: Mapped[bool] = mapped_column(Boolean, nullable=False)
    signal_count: Mapped[int] = mapped_column(nullable=False, index=True)


class IndexMembershipModel(Base):
    """Many-to-many: which major index(es) a ticker belongs to (S&P
    500, Nasdaq-100, Dow Jones). A ticker can have zero, one, or
    several rows here -- substantial real overlap exists between
    these indices, confirmed directly tonight (only 8 of 123 combined
    Nasdaq-100 + Dow Jones tickers were genuinely new beyond the
    existing S&P 500 universe). No row at all for a given ticker is
    meaningful (membership not yet backfilled), not an error."""

    __tablename__ = "index_memberships"

    ticker: Mapped[str] = mapped_column(ForeignKey("companies.ticker"), primary_key=True)
    index_name: Mapped[str] = mapped_column(primary_key=True, index=True)


class SyncedOrderModel(Base):
    """Tracks which brokerage order_ids have already been synced into
    a portfolio -- a real, live bug caught directly by the user: the
    "Sync to portfolio" button had nothing preventing the same order
    from being synced twice, silently double- and triple-counting its
    real shares each time (SyncFilledOrderToPortfolioUseCase itself
    correctly accumulates shares on every call, which is necessary
    for genuinely buying more of a ticker over time, but has no way
    to know a given order was already counted). order_id is the
    primary key, not portfolio_id + order_id, because a specific,
    real brokerage order was either already synced once or it
    wasn't -- that's a fact about the order itself, independent of
    which portfolio it landed in."""

    __tablename__ = "synced_orders"

    order_id: Mapped[str] = mapped_column(primary_key=True)
    portfolio_id: Mapped[str] = mapped_column(nullable=False)
    ticker: Mapped[str] = mapped_column(nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Nasdaq100ClassificationModel(Base):
    """Latest-only cache across all six real screener dimensions, same
    pattern as ConvictionScreenerResultModel: one row per ticker,
    overwritten on each refresh, with a shared as_of timestamp so
    staleness is honestly knowable from any single row. Every column
    besides ticker/as_of/industry is deliberately nullable -- some are
    genuinely None when the underlying computation couldn't produce a
    real answer, never a fabricated placeholder."""

    __tablename__ = "nasdaq100_classifications"

    ticker: Mapped[str] = mapped_column(ForeignKey("companies.ticker"), primary_key=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    industry: Mapped[str] = mapped_column(nullable=False, index=True)

    market_structure_category: Mapped[str | None] = mapped_column(index=True, nullable=True)
    hhi: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_chain_position: Mapped[str | None] = mapped_column(index=True, nullable=True)
    business_model: Mapped[str | None] = mapped_column(index=True, nullable=True)
    market_cap_tier: Mapped[str | None] = mapped_column(index=True, nullable=True)
    maturity_stage: Mapped[str | None] = mapped_column(index=True, nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    revenue_growth: Mapped[float | None] = mapped_column(Float, nullable=True)


