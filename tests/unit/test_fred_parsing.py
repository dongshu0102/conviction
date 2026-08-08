"""Tests for FRED's response parsing, using a real, documented sample
response shape from FRED's own API documentation.

Imports the pure parsing function directly, not the provider class —
the provider class's module imports httpx, which isn't always
installed in every environment this test might run in; the parsing
logic itself has no such dependency, and it's the part with real risk
(wire-format bugs), not the HTTP mechanics. Same pattern as
test_marketdata_app_provider.py.
"""
from __future__ import annotations

from datetime import date

from src.infrastructure.data_providers.fred_parsing import parse_series_observations

# This matches FRED's own documented sample response shape exactly —
# field names, nesting, string-typed values — taken directly from
# their real API docs, not invented. Ascending (oldest-first) order,
# matching FRED's real, documented default.
_REAL_SAMPLE_RESPONSE = {
    "realtime_start": "2024-01-01",
    "realtime_end": "2024-01-01",
    "observation_start": "2020-01-01",
    "observation_end": "2020-04-01",
    "units": "lin",
    "output_type": 1,
    "file_type": "json",
    "order_by": "observation_date",
    "sort_order": "asc",
    "count": 4,
    "offset": 0,
    "limit": 100000,
    "observations": [
        {"realtime_start": "2024-01-01", "realtime_end": "2024-01-01", "date": "2020-01-01", "value": "21427.2"},
        {"realtime_start": "2024-01-01", "realtime_end": "2024-01-01", "date": "2020-02-01", "value": "21706.5"},
        # A genuinely missing observation, real FRED convention — not null, not omitted, the literal string ".".
        {"realtime_start": "2024-01-01", "realtime_end": "2024-01-01", "date": "2020-03-01", "value": "."},
        {"realtime_start": "2024-01-01", "realtime_end": "2024-01-01", "date": "2020-04-01", "value": "19477.4"},
    ],
}


def test_parses_real_documented_response_shape_correctly() -> None:
    readings = parse_series_observations(_REAL_SAMPLE_RESPONSE, "GDP")

    assert len(readings) == 3  # the "." row is genuinely skipped, not fabricated as 0.0
    assert all(r.name == "GDP" for r in readings)


def test_returns_most_recent_first_reversing_freds_own_ascending_default() -> None:
    readings = parse_series_observations(_REAL_SAMPLE_RESPONSE, "GDP")

    assert readings[0].as_of == date(2020, 4, 1)
    assert readings[0].value == 19477.4
    assert readings[-1].as_of == date(2020, 1, 1)
    assert readings[-1].value == 21427.2


def test_string_values_are_correctly_parsed_as_floats() -> None:
    """FRED's real quirk: value comes back as a string in the wire
    format, not a JSON number."""
    readings = parse_series_observations(_REAL_SAMPLE_RESPONSE, "GDP")

    assert isinstance(readings[0].value, float)


def test_missing_value_marker_is_skipped_not_fabricated_as_zero() -> None:
    readings = parse_series_observations(_REAL_SAMPLE_RESPONSE, "GDP")

    dates_present = {r.as_of for r in readings}
    assert date(2020, 3, 1) not in dates_present


def test_unexpected_payload_shape_returns_empty_list_not_error() -> None:
    assert parse_series_observations({"unexpected": "shape"}, "GDP") == []
    assert parse_series_observations(None, "GDP") == []
    assert parse_series_observations([], "GDP") == []


def test_malformed_observation_row_is_skipped_not_fatal() -> None:
    """One bad row among many shouldn't crash the whole parse."""
    broken_response = dict(_REAL_SAMPLE_RESPONSE)
    broken_response["observations"] = [
        {"date": "2020-01-01", "value": "21427.2"},
        {"date": "not-a-real-date", "value": "21706.5"},  # malformed date
        {"date": "2020-04-01"},  # missing value key entirely
        {"date": "2020-05-01", "value": "not-a-number"},  # unparseable value
        {"date": "2020-06-01", "value": "22000.0"},  # this one is fine
    ]

    readings = parse_series_observations(broken_response, "GDP")

    # Only the two genuinely well-formed rows survive.
    assert len(readings) == 2
    assert {r.value for r in readings} == {21427.2, 22000.0}
