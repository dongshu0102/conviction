"""Pure functions for portfolio volatility, correlation, and parametric
VaR. Kept free of any repository/provider imports for the same reason
as factor_math.py — this arithmetic must be hand-verifiable and
unit-testable in total isolation from data access.

METHODOLOGY NOTES (read before changing constants):
- Returns are SIMPLE returns (P_t - P_t-1)/P_t-1, not log returns —
  consistent with every other percentage-change convention already in
  this codebase (day_move_pct, momentum_pct, etc).
- Covariance/variance use the SAMPLE convention (n-1 denominator, via
  statistics.covariance/statistics.variance), the standard convention
  in portfolio risk reporting.
- Trading-day alignment across tickers is POSITIONAL, not by explicit
  calendar date — this assumes all holdings share the same U.S. trading
  calendar, which holds for ordinary listed equities but is a known
  simplification for a ticker with a recent halt or a very recent IPO.
"""
from __future__ import annotations

import statistics

TRADING_DAYS_PER_YEAR = 252
Z_SCORE_95 = 1.645  # one-tailed 95% confidence, standard normal


def compute_simple_returns(closes_most_recent_first: list[float]) -> list[float]:
    """closes_most_recent_first[0] is the newest close (matches
    get_daily_closes' contract). Returns simple returns in the same
    most-recent-first order; length is len(closes) - 1."""
    returns = []
    for i in range(len(closes_most_recent_first) - 1):
        newer, older = closes_most_recent_first[i], closes_most_recent_first[i + 1]
        if older == 0:
            continue  # a zero close is bad data, not a valid return point
        returns.append((newer - older) / older)
    return returns


def trim_to_common_length(
    returns_by_ticker: dict[str, list[float]], min_observations: int
) -> tuple[dict[str, list[float]], list[str]]:
    """Excludes any ticker with fewer than min_observations return
    points entirely (honest exclusion, same principle as screen_stocks
    and factor scoring — a too-short history isn't force-fit into the
    calculation). Every KEPT series is trimmed to the same length (the
    shortest among the kept series) so covariance can be computed
    pairwise on aligned, same-length arrays."""
    kept = {t: r for t, r in returns_by_ticker.items() if len(r) >= min_observations}
    excluded = [t for t in returns_by_ticker if t not in kept]
    if not kept:
        return {}, excluded
    common_length = min(len(r) for r in kept.values())
    trimmed = {t: r[:common_length] for t, r in kept.items()}
    return trimmed, excluded


def portfolio_variance(
    weights: dict[str, float], returns_by_ticker: dict[str, list[float]]
) -> float | None:
    """w^T * Cov * w. Weights need not sum to 1 — normalize before
    calling if that matters for interpretation (it does for annualized
    volatility to mean anything as a whole-portfolio number). Returns
    None if there are fewer than 2 aligned return observations, since
    sample covariance is undefined below that."""
    tickers = list(returns_by_ticker.keys())
    if not tickers or any(len(r) < 2 for r in returns_by_ticker.values()):
        return None

    variance = 0.0
    for i, ticker_i in enumerate(tickers):
        for j, ticker_j in enumerate(tickers):
            w_i, w_j = weights.get(ticker_i, 0.0), weights.get(ticker_j, 0.0)
            if w_i == 0.0 or w_j == 0.0:
                continue
            cov = (
                statistics.variance(returns_by_ticker[ticker_i])
                if i == j
                else statistics.covariance(returns_by_ticker[ticker_i], returns_by_ticker[ticker_j])
            )
            variance += w_i * w_j * cov
    return variance


def correlation(ticker_a_returns: list[float], ticker_b_returns: list[float]) -> float | None:
    """None if either series has zero variance (a flat price series —
    no meaningful correlation to a constant) or fewer than 2 points."""
    if len(ticker_a_returns) < 2 or len(ticker_b_returns) < 2:
        return None
    var_a = statistics.variance(ticker_a_returns)
    var_b = statistics.variance(ticker_b_returns)
    if var_a == 0 or var_b == 0:
        return None
    cov = statistics.covariance(ticker_a_returns, ticker_b_returns)
    return cov / ((var_a ** 0.5) * (var_b ** 0.5))


def annualize_volatility(daily_volatility: float, trading_days: int = TRADING_DAYS_PER_YEAR) -> float:
    return daily_volatility * (trading_days ** 0.5)


def parametric_var(
    portfolio_value: float, daily_volatility: float, z_score: float = Z_SCORE_95
) -> float:
    """Parametric (variance-covariance) 1-day VaR: the estimated dollar
    loss not expected to be exceeded with the given confidence, assuming
    normally-distributed returns — a standard, well-known approximation,
    not a novel model."""
    return portfolio_value * daily_volatility * z_score


def inverse_volatility_weights(volatility_by_ticker: dict[str, float]) -> dict[str, float]:
    """NAIVE (inverse-volatility) risk parity: weight_i is proportional
    to 1/volatility_i, normalized to sum to 1.

    This is NOT full Equal Risk Contribution (ERC) — true ERC accounts
    for the covariance BETWEEN assets and requires solving a nonlinear
    system with no closed-form solution in general, which would make
    this a numerical black box nobody could hand-verify. Inverse-vol
    weighting ignores cross-asset correlation in the weighting formula
    itself and is a deliberate, documented simplification — but it is
    a legitimate, widely-used industry approximation (this is literally
    how many "risk parity" ETFs weight within an asset class), and
    every step here is a simple, auditable formula rather than an
    iterative solve.

    A ticker with volatility <= 0 is meaningless to invert (zero risk
    ⇒ infinite weight) and is silently excluded from this function —
    callers are expected to have already filtered out such tickers.
    """
    inverse = {t: 1.0 / v for t, v in volatility_by_ticker.items() if v > 0}
    total = sum(inverse.values())
    if total == 0:
        return {}
    return {t: inv / total for t, inv in inverse.items()}
