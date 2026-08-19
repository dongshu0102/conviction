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


class CompanyListItemSchema(BaseModel):
    ticker: str
    name: str


class CompanyListResponseSchema(BaseModel):
    companies: list[CompanyListItemSchema]


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


class DcfProjectionYearSchema(BaseModel):
    year: int
    projected_fcf: float
    present_value: float


class DcfAssumptionsSchema(BaseModel):
    base_fcf: float
    growth_rate: float
    growth_rate_was_default: bool
    discount_rate: float
    terminal_growth_rate: float
    years: int
    net_debt: float
    shares_outstanding: float | None


class DcfResponseSchema(BaseModel):
    ticker: str
    as_of: datetime
    assumptions: DcfAssumptionsSchema
    enterprise_value: float
    equity_value: float
    per_share_value: float | None
    terminal_value: float
    present_value_of_terminal_value: float
    projections: list[DcfProjectionYearSchema]


class ReverseDcfAssumptionsSchema(BaseModel):
    base_fcf: float
    discount_rate: float
    terminal_growth_rate: float
    years: int
    net_debt: float
    shares_outstanding: float


class ReverseDcfResponseSchema(BaseModel):
    ticker: str
    as_of: datetime
    current_price: float
    implied_growth_rate: float | None
    assumptions: ReverseDcfAssumptionsSchema


class IrrScenarioSchema(BaseModel):
    entry_price: float
    exit_price: float
    years: int
    annual_dividend_per_share: float
    cash_flows: list[float]


class IrrResponseSchema(BaseModel):
    ticker: str | None
    as_of: datetime
    irr: float | None
    scenario: IrrScenarioSchema


class CompsResponseSchema(BaseModel):
    ticker: str
    as_of: datetime
    metric: str
    peer_match_level: str
    peers_considered: list[str]
    peers_used: list[str]
    peers_skipped: list[str]
    peer_count: int
    median_multiple: float
    mean_multiple: float
    implied_enterprise_value: float | None
    implied_equity_value: float | None
    implied_per_share_value: float | None


class TreasuryRatesSchema(BaseModel):
    as_of: date
    month1: float | None
    month2: float | None
    month3: float | None
    month6: float | None
    year1: float | None
    year2: float | None
    year3: float | None
    year5: float | None
    year7: float | None
    year10: float | None
    year20: float | None
    year30: float | None
    suggested_discount_rate: float | None


class EconomicIndicatorSchema(BaseModel):
    name: str
    as_of: date
    value: float


class MarketRiskPremiumSchema(BaseModel):
    country: str
    country_risk_premium: float
    total_equity_risk_premium: float


class GeneralNewsHeadlineSchema(BaseModel):
    title: str
    published_at: datetime | None
    publisher: str | None
    url: str | None
    snippet: str | None


class MacroSnapshotSchema(BaseModel):
    as_of: datetime
    gdp: EconomicIndicatorSchema | None
    cpi: EconomicIndicatorSchema | None
    inflation_rate: EconomicIndicatorSchema | None
    unemployment_rate: EconomicIndicatorSchema | None
    risk_premium: MarketRiskPremiumSchema | None
    recent_news: list[GeneralNewsHeadlineSchema]


class YieldCurveReadingSchema(BaseModel):
    spread_10y_2y: float | None
    spread_10y_3m: float | None
    is_inverted: bool
    interpretation: str


class TaylorRuleResultSchema(BaseModel):
    target_rate: float
    current_rate: float | None
    gap: float | None
    inflation_rate: float
    output_gap_pct: float | None
    interpretation: str


class SahmRuleResultSchema(BaseModel):
    current_3mo_avg: float
    trailing_12mo_min_3mo_avg: float
    gap: float
    is_triggered: bool
    interpretation: str


class CapitalFlowEventSchema(BaseModel):
    source: str
    symbol: str | None
    event_date: date
    direction: str
    headline: str
    detail_url: str | None
    detected_at: datetime
    is_late_filing: bool | None = None


class CapitalFlowScanResultSchema(BaseModel):
    new_event_count: int
    events: list[CapitalFlowEventSchema]


class Next13FDeadlineSchema(BaseModel):
    next_deadline: date | None
    days_until: int | None
    source_note: str


class InstitutionalHoldingSchema(BaseModel):
    filer_name: str
    issuer_name: str
    cusip: str
    ticker: str | None
    title_of_class: str
    value_usd: int
    shares_or_principal_amount: int
    share_type: str
    put_call: str | None
    investment_discretion: str


class InstitutionalHoldersResponseSchema(BaseModel):
    issuer_query: str
    issuer_name: str
    period_of_report: date
    holders: list[InstitutionalHoldingSchema]
    source: str = "sec_bulk"  # "sec_bulk" or "fmp_live" — never a hardcoded claim
    source_note: str = "SEC EDGAR Form 13F, free official bulk data set — not a paid vendor."


class InstitutionalPortfolioResponseSchema(BaseModel):
    filer_query: str
    filer_name: str
    period_of_report: date
    holdings: list[InstitutionalHoldingSchema]
    source: str = "sec_bulk"  # "sec_bulk" or "fmp_live" — never a hardcoded claim
    source_note: str = "SEC EDGAR Form 13F, free official bulk data set — not a paid vendor."


class PositionChangeSchema(BaseModel):
    cusip: str
    ticker: str | None
    issuer_name: str
    change_type: str
    prior_shares: int
    current_shares: int
    prior_value_usd: int
    current_value_usd: int
    pct_change: float | None


class PositionChangesResponseSchema(BaseModel):
    filer_query: str
    filer_name: str
    prior_period: date
    current_period: date
    changes: list[PositionChangeSchema]
    filer_had_no_prior_period_data: bool
    source: str = "sec_bulk"  # "sec_bulk" or "fmp_live" — never a hardcoded claim
    source_note: str = (
        "SEC EDGAR Form 13F, free official bulk data set. Based on share-count "
        "changes only, not value_usd — a position's dollar value can change "
        "purely from the security's price moving, with zero actual trading."
    )


class BeneficialOwnershipDisclosureSchema(BaseModel):
    cik: str
    filing_date: date
    accepted_date: date
    cusip: str
    name_of_reporting_person: str
    citizenship_or_place_of_organization: str | None
    sole_voting_power: int
    shared_voting_power: int
    sole_dispositive_power: int
    shared_dispositive_power: int
    amount_beneficially_owned: int
    percent_of_class: float
    type_of_reporting_person: str | None
    form_type: str
    source_url: str


class BeneficialOwnershipDisclosuresResponseSchema(BaseModel):
    ticker: str
    disclosures: list[BeneficialOwnershipDisclosureSchema]
    source_note: str = (
        "Schedule 13D/13G filings, live from FMP — no free SEC bulk data set "
        "exists for these schedules (unlike Form 13F). form_type is 13D "
        "(possible activist intent, an Item 4 purpose statement was filed) "
        "or 13G (passive investor, no such stated intent)."
    )


class InsiderTransactionSchema(BaseModel):
    filing_date: date
    transaction_date: date
    reporting_cik: str
    company_cik: str
    reporting_name: str
    type_of_owner: str
    transaction_type: str
    acquisition_or_disposition: str
    direct_or_indirect: str
    security_name: str
    securities_transacted: float
    securities_owned: float
    price: float
    source_url: str


class InsiderTransactionsResponseSchema(BaseModel):
    ticker: str
    transactions: list[InsiderTransactionSchema]
    source_note: str = (
        "Form 3/4/5 insider transactions, live from FMP — no free, structured "
        "SEC bulk data set exists for these forms (unlike Form 13F). price can "
        "be genuinely 0 for option exercises and RSU vesting (routine "
        "compensation events, not open-market trades) — a real, honest "
        "reflection of the transaction, not missing data."
    )


class InstitutionalHolderSignalSchema(BaseModel):
    filer_name: str
    current_shares: int
    current_value_usd: int
    is_increasing: bool | None


class ConvictionSummaryResponseSchema(BaseModel):
    ticker: str
    institutional_holders: list[InstitutionalHolderSignalSchema]
    institutional_signal: bool
    activist_disclosures_13d: list[BeneficialOwnershipDisclosureSchema]
    activist_signal: bool
    insider_purchases: list[InsiderTransactionSchema]
    insider_signal: bool
    signal_count: int
    source_note: str = (
        "Combines three genuinely independent SEC disclosure regimes: "
        "institutional accumulation (13F, up to 45 days late), activist intent "
        "(13D, within 5 business days), and insider buying (Form 4, within 2 "
        "business days). signal_count is an honest, coarse tally (0-3) of how "
        "many show real, current buying activity — deliberately not a "
        "fabricated, falsely-precise numeric score. Institutional signal only "
        "checks the top 5 holders' own quarter-over-quarter change; the "
        "largest holders are often passive index funds, so an absent "
        "institutional signal doesn't mean no institution holds this stock, "
        "only that none of the top 5 recently increased. 13D filings are "
        "verified against this ticker's own real CUSIP (from its 13F holdings "
        "data) before counting toward the activist signal — confirmed directly "
        "that large institutions which are themselves active 13D/13G filers "
        "(e.g. JPMorgan Chase) can otherwise appear to have 'activist' filings "
        "that are actually about a different company entirely. When no "
        "verified CUSIP is available for this ticker, 13D filings are shown "
        "unfiltered and may include unverified results."
    )


class ConvictionScreenerResultSchema(BaseModel):
    ticker: str
    institutional_signal: bool
    activist_signal: bool
    insider_signal: bool
    signal_count: int
    as_of: datetime
    # Which major index(es) this ticker belongs to (S&P 500,
    # Nasdaq-100, Dow Jones) -- empty if membership hasn't been
    # backfilled for this ticker yet, never fabricated.
    index_memberships: list[str] = []


class ConvictionScreenerResultsResponseSchema(BaseModel):
    results: list[ConvictionScreenerResultSchema]
    source_note: str = (
        "Stored results from the most recent full-universe scan, not computed "
        "live — trigger POST /conviction-summary/screen to refresh. Each row is "
        "a lightweight summary (no holder/disclosure/transaction detail); call "
        "GET /conviction-summary?ticker=X for a specific ticker's full detail."
    )


class ScreenForConvictionResponseSchema(BaseModel):
    status: str
    message: str


class PlaceOrderRequestSchema(BaseModel):
    ticker: str
    side: str  # "buy" or "sell"
    quantity: float
    order_type: str  # "market" or "limit"
    limit_price: float | None = None
    time_in_force: str = "day"
    # Real money at stake once true. Defaults to false, matching
    # PlaceOrderUseCase's own default -- omitting this field entirely
    # returns a preview only, never places a real order.
    confirm: bool = False


class OrderResultSchema(BaseModel):
    status: str  # "submitted", "needs_confirmation", or "rejected"
    order_id: str | None = None
    reply_id: str | None = None
    warning_messages: list[str] = []
    rejection_reason: str | None = None


class PlaceOrderResponseSchema(BaseModel):
    confirmed: bool
    order_result: OrderResultSchema | None = None
    source_note: str = (
        "Interactive Brokers, live brokerage integration — real money is at "
        "stake once confirm=true is sent. confirmed=false means this was a "
        "preview only; no order was placed."
    )


class ConfirmOrderRequestSchema(BaseModel):
    reply_id: str


class BrokeragePositionSchema(BaseModel):
    ticker: str
    quantity: float
    average_cost: float
    market_value: float
    unrealized_pnl: float


class BrokeragePositionsResponseSchema(BaseModel):
    positions: list[BrokeragePositionSchema]


class BrokerageAccountSummarySchema(BaseModel):
    account_id: str
    cash: float
    buying_power: float
    equity: float
    currency: str


class RateSignalsSchema(BaseModel):
    as_of: datetime
    yield_curve: YieldCurveReadingSchema
    taylor_rule: TaylorRuleResultSchema | None
    taylor_rule_unavailable_reason: str | None
    sahm_rule: SahmRuleResultSchema | None
    sahm_rule_unavailable_reason: str | None


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


class MasterLensResultSchema(BaseModel):
    master_name: str
    lens_label: str
    score: float | None
    score_basis: str
    narrative: str


class MasterLensAnalysisSchema(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    ticker: str
    generated_at: datetime
    results: list[MasterLensResultSchema]
    model_used: str


class CapitalFlowMonitorModuleDefSchema(BaseModel):
    id: str
    group: str
    title: str
    cadence: str
    source: str
    is_agent_estimate: bool  # tells the frontend whether this module's numbers are a real API reading or an AI's best-effort web-search estimate


class CapitalFlowMonitorDetailSchema(BaseModel):
    label: str
    value: str


class CapitalFlowMonitorModuleResultSchema(BaseModel):
    module_id: str
    headline_value: str
    headline_direction: str | None
    headline_label: str
    details: list[CapitalFlowMonitorDetailSchema]
    read: str
    source_note: str
    as_of: str
    fetched_at: datetime
    is_agent_estimate: bool


class CapitalFlowMonitorLoadedModuleSchema(BaseModel):
    title: str
    group: str
    result: CapitalFlowMonitorModuleResultSchema


class CapitalFlowMonitorSynthesisRequestSchema(BaseModel):
    loaded: list[CapitalFlowMonitorLoadedModuleSchema]


class CapitalFlowMonitorSynthesisSchema(BaseModel):
    regime: str
    stance: str
    supportive: list[str]
    headwinds: list[str]
    conflict: str
    watch: str


class CapitalFlowMonitorSnapshotSchema(BaseModel):
    snapshot_date: date
    # module_id -> [headline_value, headline_direction, as_of]
    signals: dict[str, list[str | None]]
    regime_label: str | None
    regime_stance: str | None
