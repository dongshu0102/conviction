"""Use case: sync a genuinely filled brokerage order into a portfolio
holding.

Deliberately a separate, explicit action -- not an automatic side
effect of checking order status (a GET request should never silently
mutate portfolio data) and not a naive re-use of AddHoldingUseCase,
which REPLACES a holding's shares/cost_basis_per_share rather than
accumulating them (confirmed directly against the real
upsert_holding implementation and Portfolio's own documented
"holdings represent current position state" design before writing
this). Calling AddHoldingUseCase directly with just this one order's
own quantity/price would silently destroy an existing position's
prior shares and cost basis on a second buy of the same ticker.

The order's own financial numbers (filled_quantity, filled_avg_price,
status) are always re-fetched live from the brokerage via
get_order_status here, never trusted from caller-supplied input --
ticker and side are accepted from the caller only as identifying
metadata about which order this is, not as authoritative financial
data.

portfolio_id is OPTIONAL. When omitted, this maps automatically to a
dedicated, per-provider portfolio -- "Alpaca (auto-synced)",
"IBKR (auto-synced)", etc, found by name or created on first use --
since Alpaca, IBKR, and Tradier are three genuinely separate, real
brokerage accounts whose positions should not be silently blended
into one shared bucket by default. An explicit portfolio_id, when
given, is still honored exactly as before -- this is an added
default, not a removed capability.
"""
from __future__ import annotations

from src.application.interfaces.brokerage_provider import (
    BrokerageProvider,
    BrokerageProviderError,
)
from src.application.use_cases.manage_portfolio import (
    AddHoldingUseCase,
    CreatePortfolioUseCase,
    PortfolioNotFoundError,
    TickerNotIngestedError,
)
from src.domain.entities.portfolio import PortfolioHolding
from src.domain.repositories.portfolio_repository import PortfolioRepository

# Real, known provider identifiers this app supports -- matches
# Settings.active_brokerage_provider's own three valid values exactly
# (see get_brokerage_provider in api/routers/brokerage.py), so a typo
# or unrecognized name fails loudly rather than silently producing an
# oddly-named portfolio.
_PROVIDER_DISPLAY_NAMES = {"alpaca": "Alpaca", "ibkr": "IBKR", "tradier": "Tradier"}


class SyncFilledOrderError(Exception):
    """A real, visible failure — never silently swallowed."""


class OrderNotFilledError(SyncFilledOrderError):
    """The order's real, current status is not "filled" -- syncing an
    unfilled or partially-filled order's full requested quantity would
    misrepresent what was actually acquired. Raised, not silently
    worked around, since only the caller can decide whether to wait
    and retry or sync the partial amount deliberately."""


class UnrecognizedProviderError(SyncFilledOrderError):
    """provider_name wasn't one of this app's real, known providers --
    refused rather than silently creating a mis-named portfolio."""


class SyncFilledOrderToPortfolioUseCase:
    def __init__(
        self,
        provider: BrokerageProvider,
        portfolio_repo: PortfolioRepository,
        add_holding: AddHoldingUseCase,
        create_portfolio: CreatePortfolioUseCase,
    ) -> None:
        self._provider = provider
        self._portfolio_repo = portfolio_repo
        self._add_holding = add_holding
        self._create_portfolio = create_portfolio

    def _resolve_portfolio_id(self, user_id: str, provider_name: str) -> str:
        """Find this user's existing, dedicated portfolio for this
        provider by its own predictable name, or create it on first
        use. Genuinely idempotent across repeated calls -- never
        creates a second, duplicate portfolio for the same
        user+provider once one already exists."""
        display_name = _PROVIDER_DISPLAY_NAMES.get(provider_name)
        if display_name is None:
            raise UnrecognizedProviderError(
                f"'{provider_name}' is not a recognized brokerage provider "
                f"(expected one of: {sorted(_PROVIDER_DISPLAY_NAMES)})."
            )
        portfolio_name = f"{display_name} (auto-synced)"

        for portfolio in self._portfolio_repo.list_for_user(user_id):
            if portfolio.name == portfolio_name:
                return portfolio.portfolio_id

        created = self._create_portfolio.execute(user_id=user_id, name=portfolio_name)
        return created.portfolio_id

    def execute(
        self,
        order_id: str,
        ticker: str,
        side: str,
        user_id: str,
        provider_name: str,
        portfolio_id: str | None = None,
    ) -> PortfolioHolding | None:
        """Returns the holding's new, real state after syncing -- or
        None specifically when a sell fully closed the position (zero
        shares remain), since PortfolioHolding itself requires a
        positive share count and fabricating one here would misstate
        what's actually held."""
        ticker = ticker.strip().upper()
        side = side.strip().lower()

        try:
            order_status = self._provider.get_order_status(order_id)
        except BrokerageProviderError as exc:
            raise SyncFilledOrderError(str(exc)) from exc

        if order_status.status != "filled":
            raise OrderNotFilledError(
                f"Order {order_id} is '{order_status.status}', not 'filled' -- "
                f"nothing was synced to avoid misrepresenting the real position."
            )
        if order_status.filled_avg_price is None:
            raise OrderNotFilledError(
                f"Order {order_id} is reported 'filled' but has no real filled_avg_price "
                f"-- refusing to sync a position with an unknown cost basis."
            )

        if portfolio_id is None:
            portfolio_id = self._resolve_portfolio_id(user_id, provider_name)

        portfolio = self._portfolio_repo.get_by_id(portfolio_id)
        if portfolio is None:
            raise PortfolioNotFoundError(portfolio_id)

        existing = next((h for h in portfolio.holdings if h.ticker == ticker), None)
        filled_quantity = order_status.filled_quantity
        fill_price = order_status.filled_avg_price

        if side == "buy":
            if existing is None:
                new_shares = filled_quantity
                new_cost_basis = fill_price
            else:
                # Genuine, real weighted-average cost basis across the
                # existing position and this new fill -- never a bare
                # overwrite, which would silently erase the prior
                # position's own real cost history.
                new_shares = existing.shares + filled_quantity
                new_cost_basis = (
                    (existing.shares * existing.cost_basis_per_share) + (filled_quantity * fill_price)
                ) / new_shares
        elif side == "sell":
            if existing is None or existing.shares < filled_quantity:
                held = existing.shares if existing is not None else 0.0
                raise SyncFilledOrderError(
                    f"Order {order_id} sold {filled_quantity} shares of {ticker}, but the "
                    f"portfolio only holds {held} -- refusing to sync a negative position "
                    f"rather than silently misrepresenting it. The portfolio and the real "
                    f"brokerage account may have diverged and are worth reconciling by hand."
                )
            new_shares = existing.shares - filled_quantity
            # Realized P&L on a sell isn't tracked by this feature at
            # all (see manage_portfolio's own docstring: holdings are
            # current-state only, not a transaction log) -- the
            # remaining shares keep their own existing cost basis,
            # standard partial-sale accounting, not the sale price.
            new_cost_basis = existing.cost_basis_per_share
        else:
            raise SyncFilledOrderError(f"Unrecognized order side '{side}' -- expected 'buy' or 'sell'.")

        if new_shares <= 0:
            self._portfolio_repo.remove_holding(portfolio_id, ticker)
            return None

        try:
            return self._add_holding.execute(
                portfolio_id=portfolio_id, ticker=ticker,
                shares=new_shares, cost_basis_per_share=new_cost_basis,
            )
        except TickerNotIngestedError:
            raise
