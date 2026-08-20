"""Tradier Brokerage API adapter -- real money at stake once configured
with real, live-trading credentials.

Genuinely, richly confirmed against Tradier's own, STATIC documentation
(unlike several of IBKR's own docs pages, which render dynamically via
JavaScript and couldn't be fetched directly) -- meaningfully higher
confidence in this provider's shape than in ibkr_provider.py's.

Order requests are form-urlencoded (application/x-www-form-urlencoded),
genuinely different from both ibkr_provider.py's and
alpaca_provider.py's JSON bodies -- confirmed directly, not assumed.

Follows Tradier's own, explicitly documented "Recommended Workflow"
internally: every real order is first submitted with preview=true (a
real, live call to Tradier's own validation -- real buying-power
checks, real cost estimates -- not just a local, offline check) before
the real, actual submission. This is an extra, genuine safety layer
beyond PlaceOrderUseCase's own confirm=True gate, native to this
specific brokerage's own API design, not something invented here.

Tradier's own docs are explicit that a 200 OK on order submission only
confirms the API call itself was well-formed -- the order can still be
rejected at the brokerage level afterward. status="submitted" from
this provider means "accepted for processing," not "guaranteed
filled" -- callers should still poll get_positions or a future
get_order_status capability to confirm the real, final outcome.

HONEST CONFIDENCE NOTE, matching the other two providers: built
without live Tradier credentials to test against (confirmed directly
with the user). Unit-tested against fakes only, not live-verified.
"""
from __future__ import annotations

import httpx

from src.application.interfaces.brokerage_provider import (
    BrokerageProvider,
    BrokerageProviderError,
)
from src.domain.entities.brokerage import (
    BrokerageAccountSummary,
    BrokeragePosition,
    CancelOrderResult,
    OrderHistoryEntry,
    OrderRequest,
    OrderResult,
    OrderStatus,
)
from src.infrastructure.config import Settings

_PRODUCTION_BASE_URL = "https://api.tradier.com/v1"
_SANDBOX_BASE_URL = "https://sandbox.tradier.com/v1"

# Confirmed directly from Tradier's own docs -- "duration", not
# "time_in_force". This app's own OrderRequest.time_in_force values
# ("day", "gtc", etc.) already match Tradier's own vocabulary
# directly, so no translation table is needed here, just a rename.
_DURATION_PARAM_NAME = "duration"


class TradierProvider(BrokerageProvider):
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        # Deliberately lazy, not eager -- see ibkr_provider.py's own
        # __init__ docstring for why raising here would surface as an
        # unhandled 500 during FastAPI's Depends() resolution instead
        # of the intended, clear 503.
        self._settings = settings
        self._client = client

    def _ensure_configured(self) -> httpx.Client:
        if not self._settings.tradier_api_token or not self._settings.tradier_account_id:
            raise BrokerageProviderError(
                "Tradier is not configured (tradier_api_token / tradier_account_id missing)."
            )
        # A genuine, real safeguard, same principle as the other two
        # providers: Tradier's live and sandbox (paper) environments
        # are two entirely separate base URLs, confirmed directly from
        # Tradier's own documentation. Refuses to ever point at the
        # real, live base URL unless live trading was explicitly,
        # deliberately opted into.
        if self._settings.tradier_live_trading_enabled:
            base_url = _PRODUCTION_BASE_URL
        else:
            base_url = _SANDBOX_BASE_URL

        if self._client is None:
            self._client = httpx.Client(
                base_url=base_url,
                headers={
                    "Authorization": f"Bearer {self._settings.tradier_api_token}",
                    "Accept": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    # -- Contract resolution (trivial for Tradier -- plain tickers) --------

    def resolve_ticker_to_contract_id(self, ticker: str) -> str | None:
        """Tradier orders reference a plain ticker directly, the same
        as Alpaca -- no separate contract-ID concept the way there
        genuinely is for IBKR. Confirms the ticker is a real, known
        symbol via Tradier's own /markets/quotes endpoint rather than
        blindly trusting the caller's input."""
        client = self._ensure_configured()
        try:
            response = client.get("/markets/quotes", params={"symbols": ticker.upper()})
        except httpx.HTTPError as exc:
            raise BrokerageProviderError(f"Tradier quote lookup failed for {ticker}: {exc}") from exc

        if response.status_code != 200:
            raise BrokerageProviderError(
                f"Tradier quote lookup returned {response.status_code} for {ticker}: {response.text}"
            )
        data = response.json()
        quotes = data.get("quotes", {})
        # Tradier returns an "unmatched_symbols" section, not a 404,
        # for a genuinely unknown ticker -- confirmed directly.
        if "unmatched_symbols" in quotes or not quotes.get("quote"):
            return None
        return ticker.upper()

    # -- Order placement -----------------------------------------------------

    def place_order(self, request: OrderRequest) -> OrderResult:
        """Follows Tradier's own documented workflow internally: a
        real preview=true call first (real validation against
        Tradier's own systems, not just a local check), then the real
        submission only if that preview reports result=true. See
        module docstring for why this is a genuine, extra safety layer
        specific to this brokerage's own API design."""
        client = self._ensure_configured()

        resolved = self.resolve_ticker_to_contract_id(request.ticker)
        if resolved is None:
            return OrderResult(status="rejected", rejection_reason=f"'{request.ticker}' is not a recognized ticker on Tradier.")

        order_payload = {
            "class": "equity",
            "symbol": resolved,
            "side": request.side,
            "quantity": str(request.quantity),
            "type": request.order_type,
            _DURATION_PARAM_NAME: request.time_in_force,
        }
        if request.order_type == "limit":
            if request.limit_price is None:
                raise BrokerageProviderError("limit_price is required for a limit order.")
            order_payload["price"] = str(request.limit_price)

        preview_result = self._submit_order_payload({**order_payload, "preview": "true"})
        if preview_result.status == "rejected":
            return preview_result

        return self._submit_order_payload(order_payload)

    def _submit_order_payload(self, order_payload: dict) -> OrderResult:
        client = self._ensure_configured()
        try:
            response = client.post(
                f"/accounts/{self._settings.tradier_account_id}/orders", data=order_payload,
            )
        except httpx.HTTPError as exc:
            raise BrokerageProviderError(f"Tradier order request failed: {exc}") from exc

        if response.status_code == 400:
            # Confirmed directly from Tradier's own docs: 400 bodies
            # are descriptive and explain exactly what's wrong.
            return OrderResult(status="rejected", rejection_reason=response.text)
        if response.status_code != 200:
            raise BrokerageProviderError(
                f"Tradier order request returned {response.status_code}: {response.text}"
            )

        body = response.json().get("order", {})
        if body.get("result") is False or body.get("status") not in ("ok", None) and "id" not in body:
            return OrderResult(status="rejected", rejection_reason=str(body))
        if "id" in body:
            return OrderResult(status="submitted", order_id=str(body["id"]))
        # A preview response (no "id", just a validated cost/status
        # estimate) -- "submitted" here means "preview passed," the
        # caller in place_order() knows to treat this as a green light
        # to proceed to the real submission, not as a placed order.
        return OrderResult(status="submitted")

    def confirm_order(self, reply_id: str) -> OrderResult:
        """Tradier has no warning-confirmation flow the way IBKR
        genuinely does -- place_order's own preview-then-submit
        pattern is Tradier's own, native equivalent, and it happens
        automatically inside place_order() itself, not as a separate,
        caller-driven step. Raises rather than silently returning
        something misleading."""
        raise BrokerageProviderError(
            "Tradier orders are never left pending confirmation -- preview happens "
            "automatically inside place_order(), there is nothing separate to confirm."
        )

    # -- Account -------------------------------------------------------------

    def get_account_summary(self) -> BrokerageAccountSummary:
        """Field mapping confirmed directly against Tradier's own,
        real, documented /balances response shape (not guessed):
        total_cash and total_equity are always top-level fields
        regardless of account_type, but buying power genuinely lives
        in a different, type-specific sub-object (margin.*, cash.*,
        or pdt.*) depending on the real account_type returned --
        handled explicitly here, not assumed to be one shape."""
        client = self._ensure_configured()
        try:
            response = client.get(f"/accounts/{self._settings.tradier_account_id}/balances")
        except httpx.HTTPError as exc:
            raise BrokerageProviderError(f"Tradier account balances request failed: {exc}") from exc

        if response.status_code != 200:
            raise BrokerageProviderError(
                f"Tradier account balances returned {response.status_code}: {response.text}"
            )
        data = response.json().get("balances", {})
        account_type = data.get("account_type", "cash")
        if account_type == "cash":
            buying_power = float(data.get("cash", {}).get("cash_available", 0.0))
        else:
            # "margin" and "pdt" account types both carry a
            # stock_buying_power field under their own, matching
            # sub-key, confirmed directly.
            buying_power = float(data.get(account_type, {}).get("stock_buying_power", 0.0))

        return BrokerageAccountSummary(
            account_id=data.get("account_number", self._settings.tradier_account_id),
            cash=float(data.get("total_cash", 0.0)),
            buying_power=buying_power,
            equity=float(data.get("total_equity", 0.0)),
            currency="USD",
        )

    def get_positions(self) -> list[BrokeragePosition]:
        """Field mapping confirmed directly against Tradier's own,
        real, documented /positions response shape (not guessed).
        market_value and unrealized_pnl are honestly reported as 0.0,
        not silently faked from cost_basis -- this endpoint genuinely
        does not return either figure at all; a real market_value
        would require a separate, live quote lookup this method
        doesn't perform."""
        client = self._ensure_configured()
        try:
            response = client.get(f"/accounts/{self._settings.tradier_account_id}/positions")
        except httpx.HTTPError as exc:
            raise BrokerageProviderError(f"Tradier positions request failed: {exc}") from exc

        if response.status_code != 200:
            raise BrokerageProviderError(
                f"Tradier positions request returned {response.status_code}: {response.text}"
            )
        data = response.json().get("positions")
        if not data or data == "null":
            return []  # Tradier returns the literal string "null" for zero positions, confirmed directly
        raw_positions = data.get("position", [])
        if isinstance(raw_positions, dict):
            raw_positions = [raw_positions]  # Tradier returns a bare object, not a list, for exactly one position

        positions = []
        for row in raw_positions:
            cost_basis = float(row.get("cost_basis", 0.0))
            quantity = float(row.get("quantity", 0.0))
            average_cost = cost_basis / quantity if quantity else 0.0
            positions.append(BrokeragePosition(
                ticker=row.get("symbol", ""), quantity=quantity, average_cost=average_cost,
                market_value=0.0, unrealized_pnl=0.0,
            ))
        return positions

    def get_order_status(self, order_id: str) -> OrderStatus:
        """Endpoint confirmed directly from Tradier's own documentation
        (GET /v1/accounts/{account_id}/orders/{order_id}, explicitly
        documented as the way to poll for open/partially_filled/filled
        vs. rejected/canceled). HONEST CONFIDENCE NOTE matching the
        other two providers: the exact field names for filled quantity
        and average fill price were not independently confirmed
        field-by-field the way this module's place_order() request
        shape was -- best-informed inference from Tradier's own
        adjacent, confirmed field vocabulary (exec_quantity,
        avg_fill_price), consistent with this provider's own
        documented terminology elsewhere, not independently verified
        against a live response."""
        client = self._ensure_configured()
        try:
            response = client.get(f"/accounts/{self._settings.tradier_account_id}/orders/{order_id}")
        except httpx.HTTPError as exc:
            raise BrokerageProviderError(f"Tradier order status request failed: {exc}") from exc

        if response.status_code != 200:
            raise BrokerageProviderError(
                f"Tradier order status request returned {response.status_code}: {response.text}"
            )
        data = response.json().get("order", {})
        avg_price = data.get("avg_fill_price")
        return OrderStatus(
            order_id=str(data.get("id", order_id)),
            status=data.get("status", "unknown"),
            filled_quantity=float(data.get("exec_quantity", 0.0)),
            filled_avg_price=float(avg_price) if avg_price not in (None, 0, "0", "0.00000000") else None,
        )

    def cancel_order(self, order_id: str) -> CancelOrderResult:
        """Endpoint confirmed directly from Tradier's own documentation:
        DELETE /v1/accounts/{account_id}/orders/{order_id}, which
        Tradier's own docs explicitly state returns 200 OK on a
        successful cancel and recommend immediately re-checking the
        order's status to confirm it. HONEST CONFIDENCE NOTE matching
        this module's own: the exact response body shape on failure
        wasn't independently confirmed -- a non-200 status is treated
        as a real, raised error rather than assumed to map to a
        specific "already filled" case."""
        client = self._ensure_configured()
        try:
            response = client.delete(f"/accounts/{self._settings.tradier_account_id}/orders/{order_id}")
        except httpx.HTTPError as exc:
            raise BrokerageProviderError(f"Tradier order cancellation request failed: {exc}") from exc

        if response.status_code != 200:
            return CancelOrderResult(
                success=False,
                reason=f"Tradier order cancellation returned {response.status_code}: {response.text}",
            )
        return CancelOrderResult(success=True)

    def get_order_history(self, limit: int = 50) -> list[OrderHistoryEntry]:
        """Endpoint confirmed directly from Tradier's own documentation:
        GET /v1/accounts/{account_id}/orders ("Get current market
        session orders for an account"). HONEST CONFIDENCE NOTE
        matching this module's own: reuses the same per-order field
        vocabulary (exec_quantity, avg_fill_price) already confirmed
        for get_order_status against Tradier's adjacent, single-order
        endpoint, not independently re-verified for the list response
        specifically. This endpoint's own limit/pagination support
        was not confirmed, so limit is applied client-side after the
        fetch -- flagged honestly, not hidden. Same defensive handling
        as get_positions for Tradier's own, confirmed quirks: the
        literal string "null" for an empty result, and a bare object
        instead of a list for exactly one order."""
        client = self._ensure_configured()
        try:
            response = client.get(f"/accounts/{self._settings.tradier_account_id}/orders")
        except httpx.HTTPError as exc:
            raise BrokerageProviderError(f"Tradier order history request failed: {exc}") from exc

        if response.status_code != 200:
            raise BrokerageProviderError(
                f"Tradier order history request returned {response.status_code}: {response.text}"
            )
        data = response.json().get("orders")
        if not data or data == "null":
            return []  # Tradier returns the literal string "null" for zero orders, same as get_positions
        raw_orders = data.get("order", [])
        if isinstance(raw_orders, dict):
            raw_orders = [raw_orders]  # a bare object, not a list, for exactly one order -- same as get_positions

        entries = []
        for row in raw_orders[:limit]:
            avg_price = row.get("avg_fill_price")
            entries.append(OrderHistoryEntry(
                order_id=str(row.get("id", "")),
                ticker=row.get("symbol", ""),
                side=row.get("side", ""),
                quantity=float(row.get("quantity", 0.0)),
                order_type=row.get("type", ""),
                status=row.get("status", "unknown"),
                filled_quantity=float(row.get("exec_quantity", 0.0)),
                filled_avg_price=float(avg_price) if avg_price not in (None, 0, "0", "0.00000000") else None,
                submitted_at=row.get("create_date"),
            ))
        return entries
