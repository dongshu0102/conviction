"""Pure logic: given today's date, which 13F quarter (period_of_report)
should already be complete and available, based on the SEC's own
real, published deadline calendar?

Reuses FORM_13F_DEADLINES directly (capital_flow_math.py) rather than
re-deriving deadline dates independently — a second, parallel deadline
calculation would risk silently drifting from the real, confirmed
calendar over time.
"""
from __future__ import annotations

from datetime import date

from src.domain.services.capital_flow_math import FORM_13F_DEADLINES

# Each entry in FORM_13F_DEADLINES is commented with its quarter (1Q,
# 2Q, 3Q, 4Q of the labeled year) in source order. This maps each
# deadline, in that same order, to the real calendar quarter-end date
# it reports on -- confirmed directly against the comments already in
# FORM_13F_DEADLINES, not re-derived independently.
_DEADLINE_TO_PERIOD: dict[date, date] = {
    date(2026, 5, 15): date(2026, 3, 31),
    date(2026, 8, 14): date(2026, 6, 30),
    date(2026, 11, 16): date(2026, 9, 30),
    date(2027, 2, 16): date(2026, 12, 31),
    date(2027, 5, 17): date(2027, 3, 31),
    date(2027, 8, 16): date(2027, 6, 30),
    date(2027, 11, 15): date(2027, 9, 30),
    date(2028, 2, 14): date(2027, 12, 31),
    date(2028, 5, 15): date(2028, 3, 31),
    date(2028, 8, 14): date(2028, 6, 30),
    date(2028, 11, 14): date(2028, 9, 30),
    date(2029, 2, 14): date(2028, 12, 31),
}

assert set(_DEADLINE_TO_PERIOD.keys()) == set(FORM_13F_DEADLINES), (
    "This mapping has drifted out of sync with FORM_13F_DEADLINES — "
    "every real deadline must have a corresponding period_of_report."
)


def latest_expected_complete_period(as_of: date) -> date | None:
    """The most recent quarter-end (period_of_report) whose 45-day
    filing deadline has already passed as of as_of — i.e. the newest
    quarter that SHOULD already be complete and available, not
    necessarily what any particular data source actually has yet.

    Returns None if as_of is before every known deadline (no quarter
    has completed yet within the published calendar) — an honest
    "genuinely unknown," never a guessed period."""
    passed_deadlines = [d for d in FORM_13F_DEADLINES if d <= as_of]
    if not passed_deadlines:
        return None
    most_recent_deadline = max(passed_deadlines)
    return _DEADLINE_TO_PERIOD[most_recent_deadline]
