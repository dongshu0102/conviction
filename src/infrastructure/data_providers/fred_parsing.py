"""FRED (St. Louis Fed) response parsing.

This is the ONLY module in the codebase that knows what FRED's JSON
response shape looks like — same quarantine principle as
fmp_parsing.py and marketdata_parsing.py. Two real, confirmed quirks
specific to this vendor, verified against FRED's own documentation and
multiple independent client libraries before writing this:

1. `value` comes back as a STRING (e.g. "4.5"), not a number — every
   other provider in this codebase returns numeric JSON values
   directly, so this needs explicit, deliberate parsing here.
2. A missing observation is represented as the literal string "." —
   not null, not omitted, not 0. Silently parsing "." as 0.0 would
   inject a real, fabricated data point into a series where the Fed
   itself is saying "we don't have this reading" — every "." row is
   skipped, not defaulted.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from src.domain.entities.economic_indicator import EconomicIndicatorReading

logger = logging.getLogger(__name__)

FRED_MISSING_VALUE_MARKER = "."


def parse_series_observations(payload, series_id: str) -> list[EconomicIndicatorReading]:
    """Parses FRED's /fred/series/observations payload:
    {..., "observations": [{"date": "2020-01-01", "value": "4.5", ...}, ...]}
    Returns readings most recent first, matching this codebase's
    convention — FRED itself returns oldest-first by default, so this
    reverses the order. A malformed row, or a genuinely missing "."
    observation, is skipped rather than fatal to the whole batch."""
    if not isinstance(payload, dict) or "observations" not in payload:
        logger.warning("Unexpected FRED observations payload shape: %s", type(payload))
        return []

    observations = payload["observations"]
    if not isinstance(observations, list):
        logger.warning("Unexpected FRED observations['observations'] shape: %s", type(observations))
        return []

    readings: list[EconomicIndicatorReading] = []
    for i, row in enumerate(observations):
        try:
            raw_value = row["value"]
            if raw_value == FRED_MISSING_VALUE_MARKER:
                continue
            as_of = _parse_date(row["date"])
            readings.append(
                EconomicIndicatorReading(name=series_id, as_of=as_of, value=float(raw_value))
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipping malformed FRED observation row %d for %s: %s", i, series_id, exc)
            continue

    readings.reverse()  # FRED returns oldest-first; this codebase's convention is most-recent-first.
    return readings


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()
