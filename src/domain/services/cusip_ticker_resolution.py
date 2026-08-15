"""Pure logic: given FMP's search-cusip response for one CUSIP (which
can legitimately return several rows -- one per exchange listing of
the same underlying company), pick the single, correct primary US
ticker.

Confirmed directly against real FMP data, not assumed: searching CUSIP
037833100 (Apple) returns FOUR rows -- "AAPL" (US, no exchange
suffix), plus "AAPL.MX" (Mexico), "APC.DE" (Germany, Xetra), and
"APC.F" (Germany, Frankfurt). 13F itself only covers U.S.
exchange-listed equity positions (a caveat already established
throughout this codebase), so the correct row is always the one
without a dot-suffixed exchange code.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CusipSearchResult:
    """One row from FMP's search-cusip response."""

    symbol: str
    company_name: str
    market_cap: float | None


def pick_primary_us_ticker(results: list[CusipSearchResult]) -> str | None:
    """Returns the correct US ticker, or None if no US-listed (no-dot)
    candidate exists at all -- never guesses by picking a foreign
    listing, since that would be a genuinely wrong ticker, not a
    reasonable fallback."""
    us_candidates = [r for r in results if "." not in r.symbol]

    if not us_candidates:
        return None

    if len(us_candidates) == 1:
        return us_candidates[0].symbol

    # More than one no-dot candidate is a real, if rare, possibility
    # (e.g. share classes). Prefer the largest by market cap, since
    # that's the most likely to be the primary, most liquid listing.
    best = max(
        us_candidates,
        key=lambda r: r.market_cap if r.market_cap is not None else -1,
    )
    return best.symbol
