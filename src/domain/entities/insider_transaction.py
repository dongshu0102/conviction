from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class InsiderTransaction:
    """One reported transaction from a Form 3, 4, or 5 filing -- an
    officer, director, or 10%+ owner ("insider") buying, selling, or
    otherwise changing their reported holdings in their own company's
    stock. Genuinely different from Schedule 13D/13G: this is about
    an insider's own trading activity, not a separate party crossing
    5% beneficial ownership, and Form 4 is filed within 2 business
    days of the transaction itself -- the fastest, most current
    disclosure of the SEC filings covered by this platform.

    price can be genuinely 0 -- not missing data, a real, honest
    reflection of the transaction itself. Confirmed directly against
    real data: an "M-Exempt" (option exercise / RSU vesting) pair of
    real Apple filings both showed price=0, since these are routine,
    scheduled compensation events, not open-market, discretionary
    trades. A real purchase ("P-Purchase") or sale ("S-Sale") at a
    genuine, non-zero price is a materially different, stronger
    signal than a price=0 compensation event, and callers should
    treat them differently rather than presenting every transaction
    type as equivalent "insider activity."

    acquisition_or_disposition is "A" (acquired) or "D" (disposed of)
    -- confirmed directly that a single M-Exempt event can produce TWO
    separate rows for the same insider on the same day: one "D" row
    for the option/RSU being exercised away, one "A" row for the
    underlying common stock received in its place. These are not two
    independent trading decisions; they are one mechanical event
    reported as a matched pair.

    securities_owned is the insider's TOTAL reported holdings after
    this transaction, not the transaction size itself -- that's
    securities_transacted."""

    symbol: str
    filing_date: date
    transaction_date: date
    reporting_cik: str
    company_cik: str
    reporting_name: str
    type_of_owner: str
    transaction_type: str  # raw, as-filed, e.g. "P-Purchase", "S-Sale", "M-Exempt", "A-Award"
    acquisition_or_disposition: str  # "A" or "D"
    direct_or_indirect: str  # "D" (direct) or "I" (indirect, e.g. via a trust)
    security_name: str
    securities_transacted: float
    securities_owned: float
    price: float
    source_url: str
