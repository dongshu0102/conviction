"""Pure functions for cross-sectional z-scoring and composite weighting.

Kept free of any repository/provider imports — this is exactly the kind
of arithmetic that must be hand-verifiable and unit-testable in
isolation, same principle as the Greeks and option-P&L pure math.
"""
from __future__ import annotations

import statistics

from src.domain.entities.factor_scores import FactorWeights, FactorZScores


def zscore_cross_section(
    values_by_ticker: dict[str, float | None], invert: bool = False
) -> dict[str, float | None]:
    """Standardizes one factor's raw metric across the universe.

    Tickers with a None raw value get a None z-score — excluded from
    the mean/stdev computation AND left honestly absent in the output,
    never defaulted to 0 (which would misrepresent "no data" as
    "exactly average"). invert=True flips the sign, for factors where
    a LOWER raw value is the favorable direction (Value's P/E, Size's
    market cap) — so a positive z-score always means "more attractive"
    across every factor, regardless of the raw metric's natural
    direction.

    Fewer than 2 known values -> stdev is undefined -> every z-score is
    None (can't standardize a single point, and 0 known points is
    trivially the same problem).
    """
    known = {t: v for t, v in values_by_ticker.items() if v is not None}
    if len(known) < 2:
        return {t: None for t in values_by_ticker}

    mean = statistics.fmean(known.values())
    stdev = statistics.pstdev(known.values())

    result: dict[str, float | None] = {}
    for ticker, value in values_by_ticker.items():
        if value is None:
            result[ticker] = None
            continue
        if stdev == 0:
            # Every ticker has the identical value -> perfectly average,
            # not undefined -> 0.0 is the correct z-score here, not None.
            result[ticker] = 0.0
            continue
        z = (value - mean) / stdev
        result[ticker] = -z if invert else z
    return result


def composite_score(z_scores: FactorZScores, weights: FactorWeights) -> tuple[float | None, int]:
    """Weighted sum over whichever factors are actually present for
    this ticker. Returns (composite, factors_used). A factor missing
    for this ticker is excluded from both the numerator AND the weight
    total actually used — so a ticker missing Growth data is scored
    fairly on the 4 factors it has, never penalized for the hole.
    composite is None only when every single factor is missing."""
    pairs = [
        (z_scores.value, weights.value),
        (z_scores.quality, weights.quality),
        (z_scores.growth, weights.growth),
        (z_scores.momentum, weights.momentum),
        (z_scores.size, weights.size),
    ]
    present = [(z, w) for z, w in pairs if z is not None]
    if not present:
        return None, 0

    weight_total = sum(w for _, w in present)
    if weight_total == 0:
        return None, len(present)  # all present factors were explicitly weighted to zero

    weighted_sum = sum(z * w for z, w in present)
    return weighted_sum / weight_total, len(present)
