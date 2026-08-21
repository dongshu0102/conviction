"""Real brokerage/trading routes -- real money at stake once
configured with real credentials for any supported brokerage
(Interactive Brokers, Alpaca, or Tradier -- see
active_brokerage_provider in config.py for how the active one is
chosen).

Gated by get_admin_user_id, not just get_authenticated_user_id, unlike
every other new router built tonight (13F, 13D/13G, insider
transactions) which are deliberately public (any valid API key) since
they only ever expose non-user-owned public SEC/market data. This
router is different in kind: it can move real money in one specific,
shared brokerage account, so "any signed-up user's API key" is a real,
meaningful risk here, not just an MVP simplification -- matching
admin.py's own reasoning for the same gate on its own sensitive
endpoints.

HONEST CONFIDENCE NOTE, matching all three providers' own docstrings:
built without live credentials for any of the three brokerages to test
against. Unit-tested against fakes only, not live-verified against
any brokerage's real servers the way every other integration tonight
was. Do not treat this the same as a live-verified feature. Tradier's
own documentation was genuinely static and fully fetchable (unlike
several of IBKR's own docs pages, which render dynamically via
JavaScript), giving meaningfully higher confidence in that specific
provider's request/response shapes than in IBKR's own.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.api.auth import get_admin_user_id
from src.api.routers.companies import get_company_repository
from src.api.routers.portfolios import get_portfolio_repository
from src.api.schemas import (
    BrokerageAccountSummarySchema,
    BrokeragePositionSchema,
    BrokeragePositionsResponseSchema,
    CancelOrderResponseSchema,
    ConfirmOrderRequestSchema,
    OrderHistoryEntrySchema,
    OrderHistoryResponseSchema,
    OrderResultSchema,
    OrderStatusSchema,
    PlaceOrderRequestSchema,
    PlaceOrderResponseSchema,
    SyncFilledOrderRequestSchema,
    SyncFilledOrderResponseSchema,
    SyncMultipleOrdersRequestSchema,
    SyncMultipleOrdersResponseSchema,
    SyncOrderOutcomeSchema,
)
from src.application.interfaces.brokerage_provider import BrokerageProvider, BrokerageProviderError
from src.application.use_cases.cancel_order import CancelOrderError, CancelOrderUseCase
from src.application.use_cases.confirm_order import ConfirmOrderError, ConfirmOrderUseCase
from src.application.use_cases.get_brokerage_account_summary import (
    GetBrokerageAccountSummaryError,
    GetBrokerageAccountSummaryUseCase,
)
from src.application.use_cases.get_brokerage_positions import (
    GetBrokeragePositionsError,
    GetBrokeragePositionsUseCase,
)
from src.application.use_cases.get_order_history import GetOrderHistoryError, GetOrderHistoryUseCase
from src.application.use_cases.get_order_status import GetOrderStatusError, GetOrderStatusUseCase
from src.application.use_cases.manage_portfolio import (
    AddHoldingUseCase,
    CreatePortfolioUseCase,
    PortfolioNotFoundError,
    TickerNotIngestedError,
)
from src.application.use_cases.place_order import PlaceOrderError, PlaceOrderUseCase
from src.application.use_cases.sync_filled_order_to_portfolio import (
    OrderNotFilledError,
    SyncFilledOrderError,
    SyncFilledOrderToPortfolioUseCase,
    UnrecognizedProviderError,
)
from src.application.use_cases.sync_multiple_filled_orders import SyncMultipleFilledOrdersUseCase
from src.domain.entities.brokerage import OrderRequest
from src.infrastructure.brokerage.alpaca_provider import AlpacaProvider
from src.infrastructure.brokerage.ibkr_provider import IbkrProvider
from src.infrastructure.brokerage.tradier_provider import TradierProvider
from src.infrastructure.config import get_settings
from src.infrastructure.persistence.synced_order_repository_impl import SqlAlchemySyncedOrderRepository

router = APIRouter(prefix="/brokerage", tags=["brokerage"])


def get_brokerage_provider() -> BrokerageProvider:
    """Chosen explicitly from active_brokerage_provider, never
    inferred from which credentials happen to be configured -- all
    three providers can be fully configured at once, but only one is
    ever active for real order placement."""
    settings = get_settings()
    if settings.active_brokerage_provider == "alpaca":
        return AlpacaProvider(settings=settings)
    if settings.active_brokerage_provider == "tradier":
        return TradierProvider(settings=settings)
    return IbkrProvider(settings=settings)


def get_synced_order_repository() -> SqlAlchemySyncedOrderRepository:
    return SqlAlchemySyncedOrderRepository()


_BROKERAGE_SOURCE_NOTES = {
    "ibkr": (
        "Interactive Brokers, live brokerage integration — real money is at "
        "stake once confirm=true is sent. confirmed=false means this was a "
        "preview only; no order was placed."
    ),
    "alpaca": (
        "Alpaca, live brokerage integration — real money is at "
        "stake once confirm=true is sent against a live (non-paper) account. "
        "confirmed=false means this was a preview only; no order was placed."
    ),
    "tradier": (
        "Tradier, live brokerage integration — real money is at "
        "stake once confirm=true is sent against a live (non-paper) account. "
        "confirmed=false means this was a preview only; no order was placed."
    ),
}


def _to_order_result_schema(result) -> OrderResultSchema:
    return OrderResultSchema(
        status=result.status, order_id=result.order_id, reply_id=result.reply_id,
        warning_messages=list(result.warning_messages), rejection_reason=result.rejection_reason,
    )


@router.post("/orders", response_model=PlaceOrderResponseSchema)
def place_order(
    body: PlaceOrderRequestSchema,
    admin_user_id: str = Depends(get_admin_user_id),
    provider: BrokerageProvider = Depends(get_brokerage_provider),
    settings=Depends(get_settings),
) -> PlaceOrderResponseSchema:
    use_case = PlaceOrderUseCase(provider)
    request = OrderRequest(
        ticker=body.ticker, side=body.side, quantity=body.quantity, order_type=body.order_type,
        limit_price=body.limit_price, time_in_force=body.time_in_force,
    )
    try:
        result = use_case.execute(request, confirm=body.confirm)
    except PlaceOrderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BrokerageProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return PlaceOrderResponseSchema(
        confirmed=result.confirmed,
        order_result=_to_order_result_schema(result.order_result) if result.order_result else None,
        source_note=_BROKERAGE_SOURCE_NOTES.get(
            settings.active_brokerage_provider, _BROKERAGE_SOURCE_NOTES["ibkr"]
        ),
    )



@router.post("/orders/confirm", response_model=OrderResultSchema)
def confirm_order(
    body: ConfirmOrderRequestSchema,
    admin_user_id: str = Depends(get_admin_user_id),
    provider: BrokerageProvider = Depends(get_brokerage_provider),
) -> OrderResultSchema:
    use_case = ConfirmOrderUseCase(provider)
    try:
        result = use_case.execute(body.reply_id)
    except ConfirmOrderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return _to_order_result_schema(result)


@router.get("/account", response_model=BrokerageAccountSummarySchema)
def get_account_summary(
    admin_user_id: str = Depends(get_admin_user_id),
    provider: BrokerageProvider = Depends(get_brokerage_provider),
) -> BrokerageAccountSummarySchema:
    use_case = GetBrokerageAccountSummaryUseCase(provider)
    try:
        summary = use_case.execute()
    except GetBrokerageAccountSummaryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return BrokerageAccountSummarySchema(
        account_id=summary.account_id, cash=summary.cash,
        buying_power=summary.buying_power, equity=summary.equity, currency=summary.currency,
    )


@router.get("/positions", response_model=BrokeragePositionsResponseSchema)
def get_positions(
    admin_user_id: str = Depends(get_admin_user_id),
    provider: BrokerageProvider = Depends(get_brokerage_provider),
) -> BrokeragePositionsResponseSchema:
    use_case = GetBrokeragePositionsUseCase(provider)
    try:
        result = use_case.execute()
    except GetBrokeragePositionsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return BrokeragePositionsResponseSchema(
        positions=[
            BrokeragePositionSchema(
                ticker=p.ticker, quantity=p.quantity, average_cost=p.average_cost,
                market_value=p.market_value, unrealized_pnl=p.unrealized_pnl,
            )
            for p in result.positions
        ],
    )


@router.get("/orders/history", response_model=OrderHistoryResponseSchema)
def get_order_history(
    limit: int = 50,
    admin_user_id: str = Depends(get_admin_user_id),
    provider: BrokerageProvider = Depends(get_brokerage_provider),
) -> OrderHistoryResponseSchema:
    """Declared BEFORE GET /orders/{order_id} deliberately -- FastAPI
    matches routes in declaration order, and a literal path segment
    ("history") must be registered ahead of a parameterized one
    ({order_id}) on the same prefix, or a request to /orders/history
    would incorrectly match {order_id}="history" instead."""
    use_case = GetOrderHistoryUseCase(provider)
    try:
        result = use_case.execute(limit=limit)
    except GetOrderHistoryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return OrderHistoryResponseSchema(
        entries=[
            OrderHistoryEntrySchema(
                order_id=e.order_id, ticker=e.ticker, side=e.side, quantity=e.quantity,
                order_type=e.order_type, status=e.status, filled_quantity=e.filled_quantity,
                filled_avg_price=e.filled_avg_price, submitted_at=e.submitted_at,
            )
            for e in result.entries
        ],
    )


@router.get("/orders/{order_id}", response_model=OrderStatusSchema)
def get_order_status(
    order_id: str,
    admin_user_id: str = Depends(get_admin_user_id),
    provider: BrokerageProvider = Depends(get_brokerage_provider),
) -> OrderStatusSchema:
    use_case = GetOrderStatusUseCase(provider)
    try:
        status = use_case.execute(order_id)
    except GetOrderStatusError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return OrderStatusSchema(
        order_id=status.order_id, status=status.status,
        filled_quantity=status.filled_quantity, filled_avg_price=status.filled_avg_price,
    )


@router.delete("/orders/{order_id}", response_model=CancelOrderResponseSchema)
def cancel_order(
    order_id: str,
    admin_user_id: str = Depends(get_admin_user_id),
    provider: BrokerageProvider = Depends(get_brokerage_provider),
) -> CancelOrderResponseSchema:
    use_case = CancelOrderUseCase(provider)
    try:
        result = use_case.execute(order_id)
    except CancelOrderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return CancelOrderResponseSchema(success=result.success, reason=result.reason)


@router.post("/orders/{order_id}/sync-to-portfolio", response_model=SyncFilledOrderResponseSchema)
def sync_filled_order_to_portfolio(
    order_id: str,
    body: SyncFilledOrderRequestSchema,
    admin_user_id: str = Depends(get_admin_user_id),
    provider: BrokerageProvider = Depends(get_brokerage_provider),
    portfolio_repo=Depends(get_portfolio_repository),
    company_repo=Depends(get_company_repository),
    settings=Depends(get_settings),
    synced_order_repo=Depends(get_synced_order_repository),
) -> SyncFilledOrderResponseSchema:
    """A deliberate, explicit POST -- never an automatic side effect of
    checking order status. Re-fetches the order's real, live status
    from the brokerage itself before syncing anything; the request
    body's ticker/side are used only to identify which order this is,
    never trusted as the source of the actual fill quantity or price.

    portfolio_id is optional in the request body -- when omitted, this
    syncs to a dedicated, per-broker portfolio automatically, using
    settings.active_brokerage_provider (this app's own, real source of
    truth for which broker is currently active) rather than trusting
    the client to say which broker it was."""
    add_holding = AddHoldingUseCase(portfolio_repo, company_repo)
    create_portfolio = CreatePortfolioUseCase(portfolio_repo)
    use_case = SyncFilledOrderToPortfolioUseCase(provider, portfolio_repo, add_holding, create_portfolio, synced_order_repo)
    try:
        result = use_case.execute(
            order_id, ticker=body.ticker, side=body.side,
            user_id=admin_user_id, provider_name=settings.active_brokerage_provider,
            portfolio_id=body.portfolio_id,
        )
    except (OrderNotFilledError, TickerNotIngestedError, UnrecognizedProviderError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PortfolioNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SyncFilledOrderError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if result is None:
        return SyncFilledOrderResponseSchema(position_closed=True)
    return SyncFilledOrderResponseSchema(
        ticker=result.ticker, shares=result.shares, cost_basis_per_share=result.cost_basis_per_share,
    )


@router.post("/orders/sync-to-portfolio", response_model=SyncMultipleOrdersResponseSchema)
def sync_multiple_filled_orders(
    body: SyncMultipleOrdersRequestSchema,
    admin_user_id: str = Depends(get_admin_user_id),
    provider: BrokerageProvider = Depends(get_brokerage_provider),
    portfolio_repo=Depends(get_portfolio_repository),
    company_repo=Depends(get_company_repository),
    settings=Depends(get_settings),
    synced_order_repo=Depends(get_synced_order_repository),
) -> SyncMultipleOrdersResponseSchema:
    """Bulk sync for a caller-specified list of order_ids -- never
    "sync everything filled automatically," since this app has no
    persistent record of which orders were already synced, and a
    naive full-history sync run twice would silently double-count
    shares. One order's own failure never aborts the rest of the
    batch -- every outcome is reported back individually and
    honestly, success or failure."""
    add_holding = AddHoldingUseCase(portfolio_repo, company_repo)
    create_portfolio = CreatePortfolioUseCase(portfolio_repo)
    sync_one = SyncFilledOrderToPortfolioUseCase(provider, portfolio_repo, add_holding, create_portfolio, synced_order_repo)
    get_history = GetOrderHistoryUseCase(provider)
    use_case = SyncMultipleFilledOrdersUseCase(get_history, sync_one)

    outcomes = use_case.execute(
        body.order_ids, user_id=admin_user_id,
        provider_name=settings.active_brokerage_provider, portfolio_id=body.portfolio_id,
    )

    return SyncMultipleOrdersResponseSchema(
        outcomes=[
            SyncOrderOutcomeSchema(
                order_id=o.order_id, succeeded=o.succeeded, error=o.error, position_closed=o.position_closed,
                ticker=o.holding.ticker if o.holding else None,
                shares=o.holding.shares if o.holding else None,
                cost_basis_per_share=o.holding.cost_basis_per_share if o.holding else None,
            )
            for o in outcomes
        ],
    )
