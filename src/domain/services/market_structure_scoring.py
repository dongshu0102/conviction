"""Pure functions computing real market concentration (HHI) and
classifying it into one of the four classic microeconomic market
structures.

Kept free of any repository/provider/LLM imports -- same principle as
valuation_math.py and master_lens_scoring.py: given the same list of
peer revenues, there is exactly one correct HHI and classification,
hand-verifiable and unit-testable in isolation from how the revenue
data gets fetched.
"""
from __future__ import annotations


def compute_market_shares(revenues: dict[str, float]) -> dict[str, float]:
    """ticker -> its share (0-1) of the group's total revenue.
    Companies with non-positive or missing revenue are simply excluded
    from the total -- a genuine revenue of $0 or a data gap should
    never silently count as "0% but still a real, valid competitor"
    in a concentration calculation."""
    positive = {t: r for t, r in revenues.items() if r is not None and r > 0}
    total = sum(positive.values())
    if total <= 0:
        return {}
    return {t: r / total for t, r in positive.items()}


def compute_hhi(market_shares: dict[str, float]) -> float:
    """The real Herfindahl-Hirschman Index: sum of each firm's market
    share (as a percentage, 0-100) squared. Ranges from near-0 (many,
    equal-sized firms) to 10000 (a single firm with 100% share) --
    this exact scale and formula is the one the U.S. DOJ/FTC
    themselves use for real antitrust market-concentration review."""
    return sum((share * 100) ** 2 for share in market_shares.values())


def classify_market_structure(hhi: float | None, company_share: float | None, peer_count: int) -> str:
    """Maps a real HHI and this company's own market share to one of
    the four classic categories, using the DOJ/FTC's own, real,
    published HHI thresholds (unconcentrated <1500, moderately
    concentrated 1500-2500, highly concentrated >2500) as the
    foundation, with two, honest refinements those thresholds alone
    don't capture:

    - A single firm with a genuinely dominant share (>50%) is
      classified Monopoly regardless of the group's overall HHI, since
      HHI alone can't distinguish "one dominant firm" from "two
      roughly equal firms," both of which can produce a high HHI.
    - Within the DOJ's own "unconcentrated" band, Perfect Competition
      is distinguished from Monopolistic Competition only by a
      genuinely large peer count (20+) and a near-zero HHI (<500) --
      the classic model's own defining trait (many small, roughly
      equal, price-taking firms). In practice, given this app's own
      large-cap-only universe, this combination essentially never
      occurs -- an honest, expected result of the data, not a bug.
    """
    if hhi is None or company_share is None or peer_count < 2:
        # Genuinely too little real, comparable data (e.g. this
        # company is the only ingested company in its own industry)
        # to honestly classify at all -- reported as unclassifiable,
        # never guessed.
        return "Unclassifiable (insufficient ingested peer data)"

    if company_share > 0.50:
        return "Monopoly"
    if hhi > 2500:
        return "Oligopoly"
    if hhi >= 500 or peer_count < 20:
        return "Monopolistic Competition"
    return "Perfect Competition"
