"""Domain entity for real, human Wall Street analyst ratings and
price targets -- Step 2's "analyst ratings" from the original
screen/rank/validate/monitor workflow.

Deliberately built from FMP's own /grades-summary and
/price-target-summary endpoints, not /ratings-snapshot: ratings-snapshot
is FMP's own internal, algorithmically-computed score derived from
fundamentals (DCF/ROE/ROA/debt-to-equity/etc), not real analyst
opinions at all -- confirmed directly by testing all three live before
choosing, not assumed from the endpoint name alone. grades-summary and
price-target-summary are the real, genuine buy/sell/hold consensus and
price targets from actual analysts at real publishers.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AnalystRatings:
    ticker: str
    strong_buy: int
    buy: int
    hold: int
    sell: int
    strong_sell: int
    consensus: str
    last_month_avg_price_target: float | None
    last_month_count: int
    last_quarter_avg_price_target: float | None
    last_quarter_count: int
    last_year_avg_price_target: float | None
    last_year_count: int

    @property
    def total_analysts(self) -> int:
        return self.strong_buy + self.buy + self.hold + self.sell + self.strong_sell
