"""Alpaca Trading API adapter -- real money at stake once configured
with real, live-trading credentials.

Genuinely, substantially simpler than ibkr_provider.py, confirmed
directly from Alpaca's own documentation: authentication is a plain
API key/secret pair sent as headers (no OAuth, no JWT signing, no
multi-step session establishment); orders reference a ticker symbol
directly (no separate contract-ID lookup step); and a single POST to
/v2/orders either succeeds or fails outright via a normal HTTP status
code (200/201 for accepted, 403 for insufficient buying power, 422 for
unrecognized parameters) -- there is no multi-step warning-confirmation
flow the way there genuinely is for IBKR. status="needs_confirmation"
is therefore never returned by this provider; OrderResult's own
generic shape still applies since it's shared across brokerages, but
this specific provider only ever produces "submitted" or "rejected".

Paper vs. live is a genuinely different mechanism than IBKR's
"DU"-prefixed account ID: Alpaca uses two entirely separate base URLs
(paper-api.alpaca.markets vs. api.alpaca.markets). The same explicit,
separate opt-in principle still applies -- see _ensure_configured.

HONEST CONFIDENCE NOTE, matching ibkr_provider.py: built without live
Alpaca credentials to test against (confirmed directly with the
user), so this is unit-tested against fakes only, not live-verified
the way every other integration earlier tonight was. The request-side
order fields ARE directly confirmed from Alpaca's own, static
documentation (not JavaScript-rendered, unlike several of IBKR's own
docs pages), giving genuinely higher confidence in the request shape
here than in IBKR's -- but the response shape is well-established,
stable, publicly-documented Alpaca fields, not independently,
directly re-confirmed field-by-field the way tonight's other,
live-tested integrations were.
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
    OrderRequest,
    OrderResult,
)
from src.infrastructure.config import Settings

_PAPER_BASE_URL = "https://paper-api.alpaca.markets/v2"
_LIVE_BASE_URL = "https://api.alpaca.markets/v2"


class AlpacaProvider(BrokerageProvider):
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        # Deliberately lazy, not eager -- see ibkr_provider.py's own
        # __init__ docstring for why raising here would surface as an
        # unhandled 500 during FastAPI's Depends() resolution instead
        # of the intended, clear 503.
        self._settings = settings
        self._client = client

    def _ensure_configured(self) -> httpx.Client:
        if not self._settings.alpaca_api_key or not self._settings.alpaca_api_secret:
            raise BrokerageProviderError(
                "Alpaca is not configured (alpaca_api_key / alpaca_api_secret missing)."
            )
        # A genuine, real safeguard, not just a naming convention:
        # Alpaca's live and paper environments are two entirely
        # separate base URLs, confirmed directly from Alpaca's own
        # documentation. Refuses to ever point at the real, live base
        # URL unless live trading was explicitly, deliberately opted
        # into -- never inferred from whichever API key happens to be
        # configured (a paper key sent to the live URL, or vice versa,
        # is simply rejected by Alpaca itself, but this check exists
        # so the intent is explicit before that round trip even
        # happens).
        if self._settings.alpaca_live_trading_enabled:
            base_url = _LIVE_BASE_URL
        else:
            base_url = _PAPER_BASE_URL

        if self._client is None:
            self._client = httpx.Client(
                base_url=base_url,
                headers={
                    "APCA-API-KEY-ID": self._settings.alpaca_api_key,
                    "APCA-API-SECRET-KEY": self._settings.alpaca_api_secret,
                },
                timeout=30.0,
            )
        return self._client

    # -- Contract resolution (trivial for Alpaca -- see module docstring) --

    def resolve_ticker_to_contract_id(self, ticker: str) -> str | None:
        """Alpaca orders reference a plain ticker directly -- there is
        no separate contract-ID concept the way there genuinely is for
        IBKR. Returns the ticker itself, honestly satisfying this
        interface method's contract ("resolve a ticker to whatever
        identifier this brokerage needs for order placement") without
        a fake, unnecessary lookup call. Confirms the ticker is a real,
        tradable asset via Alpaca's own /assets/{symbol} endpoint
        rather than blindly trusting the caller's input."""
        client = self._ensure_configured()
        try:
            response = client.get(f"/assets/{ticker.upper()}")
        except httpx.HTTPError as exc:
            raise BrokerageProviderError(f"Alpaca asset lookup failed for {ticker}: {exc}") from exc

        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise BrokerageProviderError(
                f"Alpaca asset lookup returned {response.status_code} for {ticker}: {response.text}"
            )
        data = response.json()
        if not data.get("tradable", False):
            return None
        return ticker.upper()

    # -- Order placement -----------------------------------------------------

    def place_order(self, request: OrderRequest) -> OrderResult:
        """Confirmed directly from Alpaca's own documentation: a single
        POST to /v2/orders either succeeds (200/201, an order object
        with a real order id and status) or fails outright via a
        normal HTTP status code (403 insufficient buying power, 422
        unrecognized parameters) -- genuinely simpler than IBKR's
        three-response-shape flow. status="needs_confirmation" is
        never returned by this provider."""
        client = self._ensure_configured()

        resolved = self.resolve_ticker_to_contract_id(request.ticker)
        if resolved is None:
            return OrderResult(status="rejected", rejection_reason=f"'{request.ticker}' is not a tradable asset on Alpaca.")

        order_payload = {
            "symbol": resolved,
            "qty": str(request.quantity),
            "side": request.side,
            "type": request.order_type,
            "time_in_force": request.time_in_force,
        }
        if request.order_type == "limit":
            if request.limit_price is None:
                raise BrokerageProviderError("limit_price is required for a limit order.")
            order_payload["limit_price"] = str(request.limit_price)

        try:
            response = client.post("/orders", json=order_payload)
        except httpx.HTTPError as exc:
            raise BrokerageProviderError(f"Alpaca order placement failed: {exc}") from exc

        if response.status_code in (200, 201):
            body = response.json()
            return OrderResult(status="submitted", order_id=body.get("id"))

        # Confirmed directly: Alpaca returns a real error message
        # under "message" for both 403 (insufficient buying power)
        # and 422 (unrecognized parameters) rejections.
        if response.status_code in (403, 422):
            body = response.json()
            return OrderResult(status="rejected", rejection_reason=body.get("message", response.text))

        raise BrokerageProviderError(
            f"Alpaca order placement returned an unexpected {response.status_code}: {response.text}"
        )

    def confirm_order(self, reply_id: str) -> OrderResult:
        """Alpaca has no warning-confirmation flow -- place_order's
        own docstring explains why status="needs_confirmation" is
        never returned by this provider in the first place, so this
        should genuinely never be called for an Alpaca-placed order.
        Raises rather than silently returning something misleading."""
        raise BrokerageProviderError(
            "Alpaca orders are never left pending confirmation -- there is nothing to confirm."
        )

    # -- Account -------------------------------------------------------------

    def get_account_summary(self) -> BrokerageAccountSummary:
        client = self._ensure_configured()
        try:
            response = client.get("/account")
        except httpx.HTTPError as exc:
            raise BrokerageProviderError(f"Alpaca account summary request failed: {exc}") from exc

        if response.status_code != 200:
            raise BrokerageProviderError(
                f"Alpaca account summary returned {response.status_code}: {response.text}"
            )
        data = response.json()
        return BrokerageAccountSummary(
            account_id=data.get("account_number", ""),
            cash=float(data.get("cash", 0.0)),
            buying_power=float(data.get("buying_power", 0.0)),
            equity=float(data.get("equity", 0.0)),
            currency=data.get("currency", "USD"),
        )

    def get_positions(self) -> list[BrokeragePosition]:
        client = self._ensure_configured()
        try:
            response = client.get("/positions")
        except httpx.HTTPError as exc:
            raise BrokerageProviderError(f"Alpaca positions request failed: {exc}") from exc

        if response.status_code != 200:
            raise BrokerageProviderError(
                f"Alpaca positions request returned {response.status_code}: {response.text}"
            )
        positions = []
        for row in response.json():
            positions.append(BrokeragePosition(
                ticker=row.get("symbol", ""),
                quantity=float(row.get("qty", 0.0)),
                average_cost=float(row.get("avg_entry_price", 0.0)),
                market_value=float(row.get("market_value", 0.0)),
                unrealized_pnl=float(row.get("unrealized_pl", 0.0)),
            ))
        return positions
