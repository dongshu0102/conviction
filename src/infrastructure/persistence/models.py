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
