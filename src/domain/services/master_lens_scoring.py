"""Pure functions computing each Master Lens's deterministic score.

Kept free of any repository/provider/LLM imports -- same principle as
valuation_math.py: given the same YearlyRatios and ValuationSnapshot
inputs, every score here has exactly one correct answer, hand-verifiable
and unit-testable in isolation from how those inputs get fetched.

Each of the 10 functions returns (score, basis) where score is 0-10 or
None (insufficient data -- never a fabricated default), and basis is a
short, honest, human-readable note on exactly what was computed --
this basis string is what gets handed to the LLM as its OWN grounding
for the narrative, so the narrative can never drift from what the
score actually measured.

Every proxy chosen here is a deliberate, documented interpretation of
that investor's real, historically attributed framework -- applied to
what's actually measurable from ingested financial statements and a
live valuation snapshot, not a claim that any single ratio fully
captures a lifetime of investment philosophy. The narrative step exists
specifically to carry the nuance the score alone can't.
"""
from __future__ import annotations

from src.domain.entities.financial_analysis import CompanyFinancialAnalysis
from src.domain.entities.valuation_snapshot import ValuationSnapshot


def _avg(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else None


def _stability(values: list[float | None]) -> float | None:
    """A simple, honest volatility proxy: mean absolute deviation from
    the average, on the original values' own scale. Lower = more
    stable. None if fewer than 2 real data points exist -- "stability"
    is not a meaningful concept for a single data point."""
    present = [v for v in values if v is not None]
    if len(present) < 2:
        return None
    mean = sum(present) / len(present)
    return sum(abs(v - mean) for v in present) / len(present)


def _clamp(score: float) -> float:
    return max(0.0, min(10.0, score))


def score_buffett(analysis: CompanyFinancialAnalysis) -> tuple[float | None, str]:
    """Moats & owner earnings: a durable moat shows up as a high,
    STABLE gross margin over time (pricing power that doesn't erode);
    owner earnings is approximated by free cash flow margin -- cash
    genuinely available to an owner after the business sustains
    itself, Buffett's own stated preference over reported net income."""
    gross_margins = [r.gross_margin for r in analysis.yearly_ratios]
    fcf_margins = [r.free_cash_flow_margin for r in analysis.yearly_ratios]
    avg_gross = _avg(gross_margins)
    avg_fcf = _avg(fcf_margins)
    stability = _stability(gross_margins)
    if avg_gross is None or avg_fcf is None:
        return None, "Insufficient gross margin / free cash flow data to assess a moat or owner earnings."
    moat_score = _clamp(avg_gross * 10)
    if stability is not None:
        moat_score = _clamp(moat_score - stability * 20)
    earnings_score = _clamp((avg_fcf + 0.05) * 40)
    score = round((moat_score + earnings_score) / 2, 1)
    basis = f"avg gross margin {avg_gross:.1%}, avg FCF margin {avg_fcf:.1%}"
    if stability is not None:
        basis += f", gross margin volatility {stability:.1%}"
    return score, basis


def score_munger(analysis: CompanyFinancialAnalysis) -> tuple[float | None, str]:
    """Inversion & incentives: instead of asking what makes this a good
    investment, ask what could genuinely kill it -- leverage and
    liquidity are the two most concrete, measurable "ways to die" in
    the financial statements themselves."""
    latest = analysis.yearly_ratios[-1] if analysis.yearly_ratios else None
    if latest is None or latest.debt_to_equity is None or latest.current_ratio is None:
        return None, "Insufficient leverage / liquidity data to invert for real, concrete failure modes."
    leverage_score = _clamp(10 - latest.debt_to_equity * 5)
    liquidity_score = _clamp(latest.current_ratio * 5)
    score = round((leverage_score + liquidity_score) / 2, 1)
    basis = f"debt/equity {latest.debt_to_equity:.2f}, current ratio {latest.current_ratio:.2f}"
    return score, basis


def score_graham(valuation: ValuationSnapshot | None) -> tuple[float | None, str]:
    """Margin of safety: lower P/E and P/B mean a smaller gap between
    price and demonstrated, already-reported earning power -- Graham's
    own preferred, conservative starting point."""
    if valuation is None or valuation.price_to_earnings is None or valuation.price_to_book is None:
        return None, "Insufficient valuation data to assess margin of safety."
    pe_score = _clamp(10 - (valuation.price_to_earnings / 3))
    pb_score = _clamp(10 - (valuation.price_to_book * 2))
    score = round((pe_score + pb_score) / 2, 1)
    basis = f"P/E {valuation.price_to_earnings:.1f}, P/B {valuation.price_to_book:.1f}"
    return score, basis


def score_lynch(analysis: CompanyFinancialAnalysis) -> tuple[float | None, str]:
    """Know what you own: a genuinely simple, understandable business
    shows up as consistent, predictable revenue growth -- not
    necessarily fast growth, but growth you could explain in one
    sentence without hedging."""
    growths = [r.revenue_growth_yoy for r in analysis.yearly_ratios]
    avg_growth = _avg(growths)
    volatility = _stability(growths)
    if avg_growth is None or volatility is None:
        return None, "Insufficient multi-year revenue history to assess growth consistency."
    consistency_score = _clamp(10 - volatility * 30)
    growth_score = _clamp((avg_growth + 0.05) * 30)
    score = round((consistency_score + growth_score) / 2, 1)
    basis = f"avg revenue growth {avg_growth:.1%}, growth volatility {volatility:.1%}"
    return score, basis


def score_dalio(analysis: CompanyFinancialAnalysis) -> tuple[float | None, str]:
    """Machines & cycles: leverage determines how exposed a business is
    to a real, external credit cycle turning against it; stable returns
    on assets across years suggest a business less at the mercy of that
    cycle's own swings."""
    latest = analysis.yearly_ratios[-1] if analysis.yearly_ratios else None
    roa_values = [r.return_on_assets for r in analysis.yearly_ratios]
    roa_stability = _stability(roa_values)
    if latest is None or latest.debt_to_equity is None:
        return None, "Insufficient leverage data to assess cycle exposure."
    leverage_score = _clamp(10 - latest.debt_to_equity * 4)
    if roa_stability is not None:
        stability_score = _clamp(10 - roa_stability * 50)
        score = round((leverage_score + stability_score) / 2, 1)
        basis = f"debt/equity {latest.debt_to_equity:.2f}, ROA volatility {roa_stability:.1%}"
    else:
        score = round(leverage_score, 1)
        basis = f"debt/equity {latest.debt_to_equity:.2f} (insufficient history for ROA stability)"
    return score, basis


def score_marks(valuation: ValuationSnapshot | None) -> tuple[float | None, str]:
    """Second-level thinking & cycles: a lower EV/EBITDA suggests the
    market hasn't already priced in an optimistic, first-level
    narrative -- Marks's own recurring warning about paying for
    consensus, obvious growth."""
    if valuation is None or valuation.ev_to_ebitda is None:
        return None, "Insufficient EV/EBITDA data to assess how much optimism is already priced in."
    score = round(_clamp(10 - (valuation.ev_to_ebitda / 3)), 1)
    basis = f"EV/EBITDA {valuation.ev_to_ebitda:.1f}"
    return score, basis


def score_klarman(analysis: CompanyFinancialAnalysis) -> tuple[float | None, str]:
    """Risk first: genuine downside protection is liquidity and low
    leverage -- Klarman's own, explicitly stated ordering (protect
    against loss before calculating potential gain)."""
    latest = analysis.yearly_ratios[-1] if analysis.yearly_ratios else None
    if latest is None or latest.current_ratio is None or latest.debt_to_equity is None:
        return None, "Insufficient liquidity / leverage data to assess downside protection."
    liquidity_score = _clamp(latest.current_ratio * 4)
    leverage_score = _clamp(10 - latest.debt_to_equity * 6)
    score = round((liquidity_score + leverage_score) / 2, 1)
    basis = f"current ratio {latest.current_ratio:.2f}, debt/equity {latest.debt_to_equity:.2f}"
    return score, basis


def score_fisher(analysis: CompanyFinancialAnalysis) -> tuple[float | None, str]:
    """Scuttlebutt: sustained, above-average revenue growth is the
    closest measurable proxy for the real demand Fisher sought to
    confirm by talking to customers and competitors directly."""
    growths = [r.revenue_growth_yoy for r in analysis.yearly_ratios]
    avg_growth = _avg(growths)
    if avg_growth is None:
        return None, "Insufficient multi-year revenue history to assess sustained demand."
    score = round(_clamp((avg_growth + 0.05) * 25), 1)
    basis = f"avg revenue growth {avg_growth:.1%}"
    return score, basis


def score_templeton(valuation: ValuationSnapshot | None) -> tuple[float | None, str]:
    """Maximum pessimism: a low price-to-sales multiple is the most
    honest, available proxy for a stock priced as if the market has
    genuinely given up on it -- Templeton's own preferred entry point,
    at the point of greatest pessimism, not optimism."""
    if valuation is None or valuation.price_to_sales is None:
        return None, "Insufficient price-to-sales data to assess market pessimism."
    score = round(_clamp(10 - (valuation.price_to_sales * 2)), 1)
    basis = f"P/S {valuation.price_to_sales:.1f}"
    return score, basis


def score_soros(analysis: CompanyFinancialAnalysis) -> tuple[float | None, str]:
    """Reflexivity: whether growth is genuinely accelerating or
    decelerating year over year is the closest measurable signal for
    a narrative that could be about to self-reinforce or self-correct
    -- reflexivity is fundamentally about the direction of change, not
    a static level."""
    growths = [r.revenue_growth_yoy for r in analysis.yearly_ratios if r.revenue_growth_yoy is not None]
    if len(growths) < 2:
        return None, "Insufficient multi-year growth history to assess whether the trend is accelerating."
    delta = growths[-1] - growths[-2]
    score = round(_clamp(5 + delta * 20), 1)
    basis = f"revenue growth moved from {growths[-2]:.1%} to {growths[-1]:.1%} year over year"
    return score, basis
