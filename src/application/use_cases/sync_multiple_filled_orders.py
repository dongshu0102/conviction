"""Use case: sync several specific, already-filled orders into
portfolios in one batch call.

Deliberately takes an explicit list of order_ids from the caller,
rather than automatically discovering and syncing "every filled order
in history" -- this app has no persistent record of which orders have
already been synced before, so a naive "sync everything filled" run a
second time would silently double-count shares for orders already
synced the first time. Requiring the caller to specify exactly which
orders to sync avoids that risk by design, not by fragile inference
(e.g. guessing from a holding's current share count, which could
coincidentally match for unrelated reasons or have been hand-edited
since).

One order's own failure (e.g. a sell exceeding held shares, or an
order that isn't actually filled) does not abort the rest of the
batch -- each result is reported back individually and honestly.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.application.use_cases.get_order_history import GetOrderHistoryUseCase
from src.application.use_cases.sync_filled_order_to_portfolio import (
    SyncFilledOrderError,
    SyncFilledOrderToPortfolioUseCase,
)
from src.domain.entities.portfolio import PortfolioHolding


@dataclass(frozen=True, slots=True)
class SyncOrderOutcome:
    order_id: str
    succeeded: bool
    holding: PortfolioHolding | None  # None on failure, or on a genuine, successful full-close sell
    position_closed: bool
    error: str | None  # None on success


class SyncMultipleFilledOrdersUseCase:
    def __init__(
        self,
        get_order_history: GetOrderHistoryUseCase,
        sync_filled_order: SyncFilledOrderToPortfolioUseCase,
    ) -> None:
        self._get_order_history = get_order_history
        self._sync_filled_order = sync_filled_order

    def execute(
        self,
        order_ids: list[str],
        user_id: str,
        provider_name: str,
        portfolio_id: str | None = None,
    ) -> list[SyncOrderOutcome]:
        # One real order-history fetch for the whole batch, not one
        # per order -- avoids N redundant calls just to look up each
        # order's own ticker/side.
        history = self._get_order_history.execute(limit=len(order_ids) + 50).entries
        history_by_id = {entry.order_id: entry for entry in history}

        outcomes: list[SyncOrderOutcome] = []
        for order_id in order_ids:
            entry = history_by_id.get(order_id)
            if entry is None:
                outcomes.append(SyncOrderOutcome(
                    order_id=order_id, succeeded=False, holding=None, position_closed=False,
                    error=f"Order {order_id} was not found in recent order history.",
                ))
                continue

            try:
                holding = self._sync_filled_order.execute(
                    order_id, ticker=entry.ticker, side=entry.side,
                    user_id=user_id, provider_name=provider_name, portfolio_id=portfolio_id,
                )
            except SyncFilledOrderError as exc:
                outcomes.append(SyncOrderOutcome(
                    order_id=order_id, succeeded=False, holding=None, position_closed=False, error=str(exc),
                ))
                continue

            outcomes.append(SyncOrderOutcome(
                order_id=order_id, succeeded=True, holding=holding,
                position_closed=holding is None, error=None,
            ))

        return outcomes
