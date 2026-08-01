"""Pure parsing logic for MarketData.app's option chain response.

Deliberately separated from marketdata_app_provider.py's HTTP client
code — this module has zero I/O dependencies (no httpx import), so it
can be tested in complete isolation from network/client concerns, and
so a test environment without httpx installed can still verify the
actual parsing correctness, which is where the real risk lives (wire
format bugs), not the HTTP mechanics.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.domain.entities.option import OptionContract, OptionQuote

logger = logging.getLogger(__name__)


def parse_option_chain_response(data: dict) -> list[OptionQuote]:
    """Converts MarketData.app's columnar (parallel-array) response
    into a normal list of OptionQuote records. Every array in the
    response is the same length, indexed by position —
    data["strike"][i] and data["delta"][i] describe the same contract.
    Verified against their real, documented sample response.
    """
    if data.get("s") != "ok":
        return []  # "no_data" status — a real, valid "nothing found" response

    count = len(data.get("strike", []))
    quotes: list[OptionQuote] = []
    for i in range(count):
        try:
            contract = OptionContract(
                underlying_ticker=data["underlying"][i],
                strike=data["strike"][i],
                expiration=datetime.fromtimestamp(
                    data["expiration"][i], tz=timezone.utc
                ).date(),
                option_type=data["side"][i],
            )
            quotes.append(
                OptionQuote(
                    contract=contract,
                    bid=data.get("bid", [None] * count)[i],
                    ask=data.get("ask", [None] * count)[i],
                    last=data.get("last", [None] * count)[i],
                    implied_volatility=data.get("iv", [None] * count)[i],
                    open_interest=data.get("openInterest", [None] * count)[i],
                    volume=data.get("volume", [None] * count)[i],
                    delta=data.get("delta", [None] * count)[i],
                    gamma=data.get("gamma", [None] * count)[i],
                    theta=data.get("theta", [None] * count)[i],
                    vega=data.get("vega", [None] * count)[i],
                    underlying_price=data.get("underlyingPrice", [None] * count)[i],
                    as_of=(
                        datetime.fromtimestamp(data["updated"][i], tz=timezone.utc)
                        if data.get("updated")
                        else datetime.now(timezone.utc)
                    ),
                )
            )
        except (KeyError, IndexError, TypeError) as exc:
            # One malformed contract in a chain of hundreds shouldn't
            # take down the whole response — skip it, log it, move on.
            logger.warning("Skipping malformed contract at index %d: %s", i, exc)
            continue

    return quotes
