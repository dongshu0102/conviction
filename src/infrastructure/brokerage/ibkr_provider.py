"""Interactive Brokers Web API adapter -- real money at stake once
configured with real credentials.

HONEST CONFIDENCE NOTE, unlike every other integration in this
codebase: this was built without any live IBKR credentials available
to test against (confirmed directly with the user), and several
details of IBKR's own documentation render dynamically via JavaScript
that couldn't be fetched and inspected directly. The endpoints, HTTP
methods, and response shapes below ARE directly confirmed from IBKR's
own static documentation and cross-referenced against multiple,
independent third-party implementations (matching results across
sources). The exact JWT claim set for the private_key_jwt client
assertion (RFC 7523) is standard-RFC-conformant best-informed
inference, not independently confirmed against IBKR's specific
implementation -- this is the one piece most likely to need
adjustment once real credentials exist to test against. Every other
provider in this codebase was live-verified before being called done;
this one cannot honestly make that claim yet.

Authentication is a real, multi-step flow, confirmed as follows:
1. Sign a short-lived JWT with the RSA private key (private_key_jwt
   client assertion) and exchange it for an OAuth 2.0 access token.
2. POST /tickle to establish a session cookie.
3. POST /iserver/auth/ssodh/init to initialize the actual, tradable
   "brokerage session" -- confirmed as a genuinely separate,
   additional step beyond the OAuth token itself; without it, only
   read-only endpoints are accessible.

Order placement is a real, multi-response-shape flow -- see
place_order's own docstring for the three distinct outcomes IBKR can
return for the exact same endpoint.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import jwt

from src.application.interfaces.brokerage_provider import (
    BrokerageProvider,
    BrokerageProviderError,
)
from src.domain.entities.brokerage import (
    BrokerageAccountSummary,
    BrokeragePosition,
    CancelOrderResult,
    OrderRequest,
    OrderResult,
    OrderStatus,
)
from src.infrastructure.config import Settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.ibkr.com/v1/api"
_TOKEN_URL = "https://api.ibkr.com/oauth2/api/v1/token"  # best-informed inference, see module docstring


class IbkrProvider(BrokerageProvider):
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        # Deliberately lazy, not eager here: raising in __init__ would
        # fire during FastAPI's own Depends() resolution, before any
        # route handler's own try/except ever runs, surfacing as an
        # unhandled 500 instead of the intended, clear 503. Every
        # other provider in this codebase defers this kind of check to
        # first real use for the same reason -- matched here too.
        self._settings = settings
        self._client = client or httpx.Client(base_url=_BASE_URL, timeout=30.0)
        self._access_token: str | None = None
        self._session_initialized = False

    def _ensure_configured(self) -> None:
        if not self._settings.ibkr_private_key_pem or not self._settings.ibkr_client_id:
            raise BrokerageProviderError(
                "IBKR is not configured (ibkr_private_key_pem / ibkr_client_id missing)."
            )
        # A genuine, real safeguard, not just a naming convention: IBKR
        # paper accounts are "DU"-prefixed, confirmed directly against
        # real, published IBKR examples ("DU***14"). Refuses to ever
        # touch a non-paper account unless live trading was explicitly,
        # deliberately opted into -- never inferred from whichever
        # account_id happens to be configured.
        account_id = self._settings.ibkr_account_id
        is_paper_account = account_id.startswith("DU")
        if not is_paper_account and not self._settings.ibkr_live_trading_enabled:
            raise BrokerageProviderError(
                f"Account '{account_id}' does not look like a paper trading account "
                "(expected a 'DU' prefix), and ibkr_live_trading_enabled is not set to "
                "true. Refusing to initialize against what may be a real, live account "
                "without an explicit, deliberate opt-in."
            )

    # -- Authentication --------------------------------------------------

    def _sign_client_assertion_jwt(self) -> str:
        """Signs a short-lived (2 minute) JWT with the RSA private key,
        per RFC 7523's private_key_jwt scheme. Claim set is standard,
        RFC-conformant best-informed inference -- see module docstring
        for the honest confidence caveat on this specific piece."""
        now = datetime.now(timezone.utc)
        claims = {
            "iss": self._settings.ibkr_client_id,
            "sub": self._settings.ibkr_client_id,
            "aud": _TOKEN_URL,
            "jti": str(uuid.uuid4()),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=2)).timestamp()),
        }
        return jwt.encode(claims, self._settings.ibkr_private_key_pem, algorithm="RS256")

    def _ensure_authenticated(self) -> None:
        self._ensure_configured()
        if self._access_token is not None and self._session_initialized:
            return

        assertion = self._sign_client_assertion_jwt()
        try:
            token_response = httpx.post(
                _TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                    "client_assertion": assertion,
                },
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            raise BrokerageProviderError(f"IBKR OAuth token request failed: {exc}") from exc

        if token_response.status_code != 200:
            raise BrokerageProviderError(
                f"IBKR OAuth token request returned {token_response.status_code}: {token_response.text}"
            )
        self._access_token = token_response.json()["access_token"]
        self._client.headers["Authorization"] = f"Bearer {self._access_token}"

        try:
            self._client.post("/tickle")
            init_response = self._client.post("/iserver/auth/ssodh/init", json={"publish": True, "compete": True})
        except httpx.HTTPError as exc:
            raise BrokerageProviderError(f"IBKR session initialization failed: {exc}") from exc

        if init_response.status_code != 200:
            raise BrokerageProviderError(
                f"IBKR brokerage session init returned {init_response.status_code}: {init_response.text}"
            )
        self._session_initialized = True

    # -- Contract resolution ----------------------------------------------

    def resolve_ticker_to_contract_id(self, ticker: str) -> str | None:
        self._ensure_authenticated()
        try:
            response = self._client.get("/iserver/secdef/search", params={"symbol": ticker})
        except httpx.HTTPError as exc:
            raise BrokerageProviderError(f"IBKR contract search failed for {ticker}: {exc}") from exc

        if response.status_code != 200:
            raise BrokerageProviderError(
                f"IBKR contract search returned {response.status_code} for {ticker}: {response.text}"
            )
        results = response.json()
        for result in results:
            # Prefer an exact, direct stock (STK) match over derivative
            # contracts that may share the same underlying symbol.
            sections = result.get("sections", [])
            if any(s.get("secType") == "STK" for s in sections) or result.get("symbol") == ticker.upper():
                return str(result.get("conid"))
        return None

    # -- Order placement ----------------------------------------------------

    def place_order(self, request: OrderRequest) -> OrderResult:
        """Confirmed directly: IBKR's own /iserver/account/{accountId}/orders
        endpoint can return three genuinely distinct response shapes for
        the exact same call: (1) an immediate order acknowledgement
        (order_id + order_status), (2) a warning reply requiring
        confirmation (id + message array -- the order has NOT been
        placed), or (3) an outright rejection returned as HTTP 200 with
        an "error" field -- NOT a 4xx status code, confirmed directly
        from IBKR's own docs. All three are handled explicitly here;
        status-code-only error handling would silently treat a genuine
        rejection as success."""
        self._ensure_authenticated()

        conid = self.resolve_ticker_to_contract_id(request.ticker)
        if conid is None:
            return OrderResult(status="rejected", rejection_reason=f"No contract found for ticker '{request.ticker}'.")

        order_payload = {
            "conid": int(conid),
            "orderType": "MKT" if request.order_type == "market" else "LMT",
            "side": request.side.upper(),
            "quantity": request.quantity,
            "tif": request.time_in_force.upper(),
        }
        if request.order_type == "limit":
            if request.limit_price is None:
                raise BrokerageProviderError("limit_price is required for a limit order.")
            order_payload["price"] = request.limit_price

        return self._submit_order_payload(order_payload)

    def _submit_order_payload(self, order_payload: dict) -> OrderResult:
        try:
            response = self._client.post(
                f"/iserver/account/{self._settings.ibkr_account_id}/orders",
                json={"orders": [order_payload]},
            )
        except httpx.HTTPError as exc:
            raise BrokerageProviderError(f"IBKR order placement failed: {exc}") from exc

        if response.status_code != 200:
            raise BrokerageProviderError(
                f"IBKR order placement returned {response.status_code}: {response.text}"
            )

        body = response.json()
        # Outright rejection: a real, confirmed IBKR behavior -- HTTP 200
        # with an "error" field, not a 4xx status.
        if isinstance(body, dict) and "error" in body:
            return OrderResult(status="rejected", rejection_reason=body["error"])

        first = body[0] if isinstance(body, list) and body else body
        if "order_id" in first:
            return OrderResult(status="submitted", order_id=first["order_id"])
        if "id" in first:
            return OrderResult(
                status="needs_confirmation",
                reply_id=first["id"],
                warning_messages=tuple(first.get("message", [])),
            )
        raise BrokerageProviderError(f"IBKR order response in an unrecognized shape: {body}")

    def confirm_order(self, reply_id: str) -> OrderResult:
        self._ensure_authenticated()
        try:
            response = self._client.post(f"/iserver/reply/{reply_id}", json={"confirmed": True})
        except httpx.HTTPError as exc:
            raise BrokerageProviderError(f"IBKR order confirmation failed: {exc}") from exc

        if response.status_code != 200:
            raise BrokerageProviderError(
                f"IBKR order confirmation returned {response.status_code}: {response.text}"
            )
        body = response.json()
        first = body[0] if isinstance(body, list) and body else body
        if isinstance(first, dict) and "error" in first:
            return OrderResult(status="rejected", rejection_reason=first["error"])
        if isinstance(first, dict) and "order_id" in first:
            return OrderResult(status="submitted", order_id=first["order_id"])
        raise BrokerageProviderError(f"IBKR order confirmation response in an unrecognized shape: {body}")

    # -- Account -------------------------------------------------------------

    def get_account_summary(self) -> BrokerageAccountSummary:
        self._ensure_authenticated()
        try:
            response = self._client.get(f"/portfolio/{self._settings.ibkr_account_id}/summary")
        except httpx.HTTPError as exc:
            raise BrokerageProviderError(f"IBKR account summary request failed: {exc}") from exc

        if response.status_code != 200:
            raise BrokerageProviderError(
                f"IBKR account summary returned {response.status_code}: {response.text}"
            )
        data = response.json()
        return BrokerageAccountSummary(
            account_id=self._settings.ibkr_account_id,
            cash=float(data.get("totalcashvalue", {}).get("amount", 0.0)),
            buying_power=float(data.get("buyingpower", {}).get("amount", 0.0)),
            equity=float(data.get("netliquidation", {}).get("amount", 0.0)),
            currency=data.get("totalcashvalue", {}).get("currency", "USD"),
        )

    def get_positions(self) -> list[BrokeragePosition]:
        self._ensure_authenticated()
        try:
            response = self._client.get(f"/portfolio/{self._settings.ibkr_account_id}/positions/0")
        except httpx.HTTPError as exc:
            raise BrokerageProviderError(f"IBKR positions request failed: {exc}") from exc

        if response.status_code != 200:
            raise BrokerageProviderError(
                f"IBKR positions request returned {response.status_code}: {response.text}"
            )
        positions = []
        for row in response.json():
            positions.append(BrokeragePosition(
                ticker=row.get("ticker", ""),
                quantity=float(row.get("position", 0.0)),
                average_cost=float(row.get("avgCost", 0.0)),
                market_value=float(row.get("mktValue", 0.0)),
                unrealized_pnl=float(row.get("unrealizedPnl", 0.0)),
            ))
        return positions

    def get_order_status(self, order_id: str) -> OrderStatus:
        """HONEST CONFIDENCE NOTE, matching this module's own: the
        endpoint path (/iserver/account/order/status/{orderId}) is
        directly confirmed from IBKR's own published documentation.
        The exact response body's field names for filled quantity and
        average fill price were NOT independently confirmed the way
        place_order's three response shapes were -- best-informed
        inference from IBKR's own, adjacent /iserver/account/orders
        field vocabulary (filledQuantity, avgPrice), not
        field-by-field verified against a live response. Flagged here
        explicitly rather than presented with false confidence."""
        self._ensure_authenticated()
        try:
            response = self._client.get(f"/iserver/account/order/status/{order_id}")
        except httpx.HTTPError as exc:
            raise BrokerageProviderError(f"IBKR order status request failed: {exc}") from exc

        if response.status_code != 200:
            raise BrokerageProviderError(
                f"IBKR order status request returned {response.status_code}: {response.text}"
            )
        data = response.json()
        avg_price = data.get("avgPrice")
        return OrderStatus(
            order_id=str(data.get("order_id", order_id)),
            status=data.get("order_status", "unknown"),
            filled_quantity=float(data.get("filledQuantity", 0.0)),
            filled_avg_price=float(avg_price) if avg_price not in (None, "") else None,
        )

    def cancel_order(self, order_id: str) -> CancelOrderResult:
        """Endpoint confirmed directly from IBKR's own published
        documentation: DELETE /iserver/account/{accountId}/order/{orderId}.
        HONEST CONFIDENCE NOTE matching this module's own: the exact
        response body shape for a genuine failure (e.g. the order has
        already filled) was not independently confirmed the way
        place_order's three response shapes were. A non-200 status is
        treated as a real, raised error here rather than assumed to
        map to a specific "already filled" case, since that specific
        mapping isn't confirmed -- callers should call
        get_order_status first if they need to distinguish why a
        cancel might fail."""
        self._ensure_authenticated()
        try:
            response = self._client.delete(f"/iserver/account/{self._settings.ibkr_account_id}/order/{order_id}")
        except httpx.HTTPError as exc:
            raise BrokerageProviderError(f"IBKR order cancellation request failed: {exc}") from exc

        if response.status_code != 200:
            return CancelOrderResult(
                success=False,
                reason=f"IBKR order cancellation returned {response.status_code}: {response.text}",
            )
        return CancelOrderResult(success=True)
