"""API response schemas.

Deliberately separate from domain entities. The API's shape is a
presentation concern (what a client needs) and will diverge from the
domain's shape (what the business logic needs) as the platform grows —
e.g. we'll add computed ratios here later without touching the domain.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class CompanySchema(BaseModel):
    ticker: str
    name: str
    sector: str
    industry: str
    exchange: str
    country: str
    ipo_date: date | None
    description: str | None
    website: str | None
    is_active: bool


class IncomeStatementSchema(BaseModel):
    fiscal_year: int
    fiscal_quarter: int | None
    period: str
    fiscal_date_ending: date
    reported_currency: str
    revenue: float | None
    gross_profit: float | None
    operating_income: float | None
    net_income: float | None
    eps_diluted: float | None
    ebitda: float | None


class BalanceSheetSchema(BaseModel):
    fiscal_year: int
    fiscal_quarter: int | None
    period: str
    fiscal_date_ending: date
    reported_currency: str
    total_assets: float | None
    total_liabilities: float | None
    total_equity: float | None
    cash_and_equivalents: float | None
    total_debt: float | None


class CashFlowStatementSchema(BaseModel):
    fiscal_year: int
    fiscal_quarter: int | None
    period: str
    fiscal_date_ending: date
    reported_currency: str
    operating_cash_flow: float | None
    capital_expenditures: float | None
    free_cash_flow: float | None


class CompanyFinancialsSchema(BaseModel):
    company: CompanySchema
    income_statements: list[IncomeStatementSchema]
    balance_sheets: list[BalanceSheetSchema]
    cash_flow_statements: list[CashFlowStatementSchema]


class ChatMessageSchema(BaseModel):
    role: str
    content: str


class ChatMessagePartSchema(BaseModel):
    type: str
    text: str | None = None


class VercelChatMessageSchema(BaseModel):
    """The real shape this SDK version sends: a `parts` array of typed
    blocks, not a flat `content` string — confirmed directly from a
    422 validation error against the actual installed frontend package,
    not assumed from documentation."""

    role: str
    parts: list[ChatMessagePartSchema] = []

    @property
    def text_content(self) -> str:
        return "".join(p.text or "" for p in self.parts if p.type == "text")


class VercelChatRequestSchema(BaseModel):
    messages: list[VercelChatMessageSchema]


class ChatRequestSchema(BaseModel):
    message: str
    history: list[ChatMessageSchema] = []


class ChatResponseSchema(BaseModel):
    reply: str


class SP500ConstituentsSchema(BaseModel):
    tickers: list[str]
    count: int


class IngestResultSchema(BaseModel):
    ticker: str
    income_statements_ingested: int
    balance_sheets_ingested: int
    cash_flow_statements_ingested: int


class YearlyRatiosSchema(BaseModel):
    fiscal_year: int
    revenue_growth_yoy: float | None
    gross_margin: float | None
    operating_margin: float | None
    net_margin: float | None
    free_cash_flow_margin: float | None
    return_on_equity: float | None
    return_on_assets: float | None
    debt_to_equity: float | None
    current_ratio: float | None


class CompanyFinancialAnalysisSchema(BaseModel):
    ticker: str
    yearly_ratios: list[YearlyRatiosSchema]


class ValuationSnapshotSchema(BaseModel):
    ticker: str
    as_of: datetime
    price: float
    market_cap: float
    enterprise_value: float | None
    fundamentals_fiscal_year: int
    price_to_earnings: float | None
    price_to_sales: float | None
    price_to_book: float | None
    price_to_free_cash_flow: float | None
    ev_to_ebitda: float | None


class PortfolioHoldingSchema(BaseModel):
    ticker: str
    shares: float
    cost_basis_per_share: float
    acquired_at: date | None


class PortfolioSchema(BaseModel):
    portfolio_id: str
    user_id: str
    name: str
    created_at: datetime
    holdings: list[PortfolioHoldingSchema]


class PositionValueSchema(BaseModel):
    ticker: str
    shares: float
    cost_basis_per_share: float
    current_price: float
    market_value: float
    cost_basis_total: float
    unrealized_gain: float
    unrealized_gain_pct: float | None
    weight: float | None


class PortfolioValuationSchema(BaseModel):
    portfolio_id: str
    name: str
    as_of: datetime
    positions: list[PositionValueSchema]
    total_market_value: float
    total_cost_basis: float
    total_unrealized_gain: float
    total_unrealized_gain_pct: float | None


class SectorExposureSchema(BaseModel):
    sector: str
    weight: float


class PairwiseCorrelationSchema(BaseModel):
    ticker_a: str
    ticker_b: str
    correlation: float


class PortfolioRiskAnalysisSchema(BaseModel):
    portfolio_id: str
    as_of: datetime
    largest_position_weight: float | None
    herfindahl_index: float | None
    sector_exposures: list[SectorExposureSchema]
    weighted_avg_debt_to_equity: float | None
    excluded_from_leverage_calc: list[str]
    portfolio_daily_volatility: float | None = None
    portfolio_annualized_volatility: float | None = None
    parametric_var_95_1day_dollar: float | None = None
    volatility_covered_weight: float | None = None
    volatility_lookback_days_used: int | None = None
    pairwise_correlations: list[PairwiseCorrelationSchema] = []
    excluded_from_volatility_calc: list[str] = []


class RiskParityRequestSchema(BaseModel):
    tickers: list[str]
    total_investment: float


class RiskParityAllocationSchema(BaseModel):
    ticker: str
    daily_volatility: float
    target_weight: float
    target_dollar_amount: float
    current_price: float
    suggested_shares: float


class RiskParityConstructionResponseSchema(BaseModel):
    as_of: datetime
    total_investment: float
    allocations: list[RiskParityAllocationSchema]
    excluded: list[str]
    methodology_note: str


class EtfIngestResultSchema(BaseModel):
    ticker: str
    name: str
    expense_ratio: float | None
    aum: float | None


class ForgotPasswordRequestSchema(BaseModel):
    email: str


class ResetPasswordRequestSchema(BaseModel):
    token: str
    new_password: str


class GenericMessageSchema(BaseModel):
    message: str


class UserSummarySchema(BaseModel):
    user_id: str
    role: str
    created_at: datetime


class ChangeRoleRequestSchema(BaseModel):
    role: str


class SpeculativeGrowthAssessmentSchema(BaseModel):
    ticker: str
    as_of: datetime
    market_cap: float | None
    revenue_growth_latest_yoy: float | None
    revenue_growth_prior_yoy: float | None
    growth_trend: str
    is_profitable: bool | None
    net_income_latest: float | None
    cash_runway_months: float | None
    years_of_data_available: int
    risk_flags: list[str]


class SpeculativeGrowthCandidateSchema(BaseModel):
    ticker: str
    added_at: datetime
    last_growth_trend: str | None
    last_cash_runway_months: float | None
    last_market_cap: float | None
    last_checked_at: datetime | None


class SignUpRequestSchema(BaseModel):
    email: str
    password: str


class LogInRequestSchema(BaseModel):
    email: str
    password: str


class ApiKeyCreatedSchema(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    plaintext_key: str
    key_prefix: str
    user_id: str
    name: str
    created_at: datetime
    warning: str = "Save this key now — it will not be shown again."


class ApiKeySummarySchema(BaseModel):
    key_prefix: str
    user_id: str
    name: str
    is_active: bool
    created_at: datetime


class WatchlistPriceMoveSchema(BaseModel):
    ticker: str
    current_price: float
    prior_price: float | None
    change_pct: float | None


class PortfolioBriefSummarySchema(BaseModel):
    portfolio_id: str
    name: str
    total_market_value: float
    total_unrealized_gain_pct: float | None
    largest_position_weight: float | None
    herfindahl_index: float | None


class DailyBriefSchema(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    user_id: str
    generated_at: datetime
    narrative: str
    model_used: str
    unread_alert_count: int
    watchlist_moves: list[WatchlistPriceMoveSchema]
    portfolio_summaries: list[PortfolioBriefSummarySchema]


class AlertSchema(BaseModel):
    id: int | None
    user_id: str
    ticker: str
    alert_type: str
    message: str
    change_pct: float | None
    is_read: bool
    created_at: datetime


class WatchlistItemSchema(BaseModel):
    user_id: str
    ticker: str
    added_at: datetime
    notes: str | None
    list_name: str = "Default"
    target_price: float | None = None
    alert_threshold_pct: float | None = None
    added_price: float | None = None
    added_pe: float | None = None


class FactorRawMetricsSchema(BaseModel):
    price_to_earnings: float | None
    return_on_equity: float | None
    revenue_growth_yoy: float | None
    momentum_1m_pct: float | None
    market_cap: float | None


class RankedFactorScoreSchema(BaseModel):
    ticker: str
    as_of: datetime
    composite_score: float | None
    factors_used: int
    value_z: float | None
    quality_z: float | None
    growth_z: float | None
    momentum_z: float | None
    size_z: float | None
    raw: FactorRawMetricsSchema


class FactorScoreResponseSchema(BaseModel):
    scoring_note: str
    result: RankedFactorScoreSchema


class FactorRankingResponseSchema(BaseModel):
    scoring_note: str
    results: list[RankedFactorScoreSchema]


# --- Options subsystem ---------------------------------------------------

class OptionHoldingRequestSchema(BaseModel):
    underlying_ticker: str
    strike: float
    expiration: date
    option_type: str
    contracts_held: float
    cost_basis_per_contract: float


class OptionHoldingRemoveRequestSchema(BaseModel):
    underlying_ticker: str
    strike: float
    expiration: date
    option_type: str


class OptionHoldingResultSchema(BaseModel):
    underlying_ticker: str
    strike: float
    expiration: date
    option_type: str
    contracts_held: float
    status: str


class PortfolioGreeksSchema(BaseModel):
    total_delta: float
    total_gamma: float
    total_theta: float
    total_vega: float
    positions_included: int
    positions_excluded: list[str]


class OptionPositionSchema(BaseModel):
    contract: str
    underlying_ticker: str
    strike: float
    expiration: date
    option_type: str
    contracts_held: float
    current_price: float
    market_value: float
    unrealized_gain: float
    unrealized_gain_pct: float


class OptionPortfolioValuationSchema(BaseModel):
    total_market_value: float
    total_cost_basis: float
    total_unrealized_gain: float
    total_unrealized_gain_pct: float
    positions: list[OptionPositionSchema]
    positions_excluded: list[str]


class HedgingSuggestionSchema(BaseModel):
    underlying_ticker: str
    net_delta: float
    shares_to_trade: float
    resulting_delta: float


class HedgingPlanSchema(BaseModel):
    suggestions: list[HedgingSuggestionSchema]
    positions_excluded: list[str]
    note: str | None = None


# --- Screening / recommendations / rebalancing ----------------------------

class ScreenRequestSchema(BaseModel):
    tickers: list[str] | None = None
    theme_name: str | None = None


class ScreenedStockSchema(BaseModel):
    ticker: str
    price: float
    price_to_earnings: float | None
    price_to_sales: float | None
    ev_to_ebitda: float | None
    return_on_equity: float | None
    net_margin: float | None
    debt_to_equity: float | None
    value_score: float | None
    quality_score: float | None
    composite_score: float | None


class ScreenResultSchema(BaseModel):
    scoring_note: str
    excluded: list[str]
    results: list[ScreenedStockSchema]


class RecommendationPickSchema(BaseModel):
    ticker: str
    gap_sector: str
    current_sector_weight: float
    price: float
    price_to_earnings: float | None
    return_on_equity: float | None
    composite_score: float | None


class RecommendationsSchema(BaseModel):
    gap_sectors: list[str]
    scoring_note: str | None = None
    picks: list[RecommendationPickSchema]
    note: str | None = None


class RebalanceSuggestionSchema(BaseModel):
    ticker: str
    current_weight: float
    target_weight: float
    shares_to_trim: float
    estimated_proceeds: float


class RebalancePlanSchema(BaseModel):
    target_max_weight: float
    suggestions: list[RebalanceSuggestionSchema]
    note: str | None = None


# --- Watchlist extras -------------------------------------------------------

class WatchlistSummarySchema(BaseModel):
    name: str
    item_count: int


class UpdateWatchlistItemRequestSchema(BaseModel):
    list_name: str = "Default"
    notes: str | None = None
    target_price: float | None = None
    alert_threshold_pct: float | None = None


class SuggestedTickerSchema(BaseModel):
    ticker: str
    company_name: str
    reasoning: str
    already_ingested: bool


class ThemeSuggestionSchema(BaseModel):
    theme_name: str
    rationale: str
    candidate_tickers: list[SuggestedTickerSchema]
    sourced_headlines: list[str]
    generated_at: datetime
    model_used: str


class ThemeSynthesisReportSchema(BaseModel):
    theme_name: str
    generated_at: datetime
    tickers_covered: list[str]
    tickers_excluded: list[str]
    overview: str
    common_threads: str
    notable_divergences: str
    key_risks: str
    model_used: str


class UniverseThemeSchema(BaseModel):
    name: str
    description: str | None
    created_at: datetime


class UniverseThemeSummarySchema(BaseModel):
    theme: UniverseThemeSchema
    member_count: int


class UniverseThemeListSchema(BaseModel):
    themes: list[UniverseThemeSummarySchema]


class ThemeTickersSchema(BaseModel):
    theme_name: str
    tickers: list[str]


class EarningsEventSchema(BaseModel):
    ticker: str
    report_date: date
    eps_estimated: float | None
    eps_actual: float | None
    revenue_estimated: float | None
    revenue_actual: float | None


class UpcomingEarningsResponseSchema(BaseModel):
    events: list[EarningsEventSchema]


class TriageSignalsSchema(BaseModel):
    day_move_pct: float | None
    move_since_added_pct: float | None
    momentum_1m_pct: float | None
    pe_drift_pct: float | None
    target_crossed: bool
    current_price: float | None
    current_pe: float | None


class TriageItemSchema(BaseModel):
    ticker: str
    list_name: str
    triage_score: float
    signals: TriageSignalsSchema
    notes: str | None


class TriageResponseSchema(BaseModel):
    as_of: datetime
    scoring_note: str
    items: list[TriageItemSchema]
    tickers_excluded: list[str]


class NewsArticleSchema(BaseModel):
    ticker: str
    title: str
    published_at: datetime | None
    source: str | None
    url: str | None
    snippet: str | None


class WatchlistNewsResponseSchema(BaseModel):
    news: dict[str, list[NewsArticleSchema]]
    tickers_failed: list[str]


class ResearchReportSchema(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    ticker: str
    business_overview: str
    financial_highlights: str
    competitive_position: str
    key_risks: str
    generated_at: datetime
    model_used: str
    grounded_fiscal_year: int | None
