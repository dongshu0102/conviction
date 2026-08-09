from datetime import date

from src.domain.entities.capital_flow import (
    CapitalFlowDirection,
    CapitalFlowSource,
    InsiderTrade,
    PoliticianTrade,
)
from src.domain.services.capital_flow_math import (
    DEFAULT_INSIDER_MIN_VALUE_USD,
    DEFAULT_POLITICIAN_MIN_VALUE_USD,
    build_insider_event,
    build_politician_event,
    is_meaningful_insider_trade,
    parse_amount_range,
)


def _insider(
    transaction_type="P-Purchase", acquisition_or_disposition="A",
    securities_transacted=1000.0, price=100.0, symbol="TEST",
) -> InsiderTrade:
    return InsiderTrade(
        symbol=symbol, filing_date=date(2026, 8, 7), transaction_date=date(2026, 8, 6),
        reporting_name="TEST PERSON", type_of_owner="officer: CEO",
        transaction_type=transaction_type, acquisition_or_disposition=acquisition_or_disposition,
        securities_transacted=securities_transacted, price=price, security_name="Common Stock",
        url="https://test.gov",
    )


def _politician(
    chamber=CapitalFlowSource.SENATE, transaction_type="Purchase",
    amount_range="$1,000,001 - $5,000,000", symbol="TEST",
) -> PoliticianTrade:
    return PoliticianTrade(
        chamber=chamber, symbol=symbol, disclosure_date=date(2026, 8, 7),
        transaction_date=date(2026, 7, 23), person_name="Test Person", office="Test Person",
        owner="Self", asset_description="Test Corp", asset_type="Stock",
        transaction_type=transaction_type, amount_range=amount_range, link="https://test",
    )


# --- parse_amount_range ------------------------------------------------------

def test_parse_amount_range_handles_real_disclosure_ranges() -> None:
    assert parse_amount_range("$1,001 - $15,000") == (1001.0, 15000.0)
    assert parse_amount_range("$1,000,001 - $5,000,000") == (1000001.0, 5000000.0)


def test_parse_amount_range_returns_none_for_unparseable_formats() -> None:
    """A real, genuinely open-ended format that does appear in the wild
    — returns None rather than guessing at a number."""
    assert parse_amount_range("Over $50,000,000") is None
    assert parse_amount_range("") is None


# --- is_meaningful_insider_trade ---------------------------------------------

def test_meaningful_insider_trade_accepts_real_purchases_and_sales() -> None:
    assert is_meaningful_insider_trade(_insider(transaction_type="P-Purchase")) is True
    assert is_meaningful_insider_trade(_insider(transaction_type="S-Sale")) is True


def test_meaningful_insider_trade_rejects_grants_and_conversions() -> None:
    """Regression test for the real row seen in production data tonight
    — a $0-price Gift transaction, which is noise, not a market signal."""
    assert is_meaningful_insider_trade(_insider(transaction_type="G-Gift")) is False
    assert is_meaningful_insider_trade(_insider(transaction_type="C-Conversion")) is False
    assert is_meaningful_insider_trade(_insider(transaction_type="M-Exempt")) is False


# --- build_insider_event ------------------------------------------------------

def test_build_insider_event_filters_out_gifts_regardless_of_size() -> None:
    """Even a huge Gift transaction isn't a real market signal."""
    huge_gift = _insider(transaction_type="G-Gift", securities_transacted=1_000_000, price=100.0)
    assert build_insider_event(huge_gift) is None


def test_build_insider_event_filters_out_small_purchases() -> None:
    small = _insider(securities_transacted=100.0, price=50.0)  # $5,000 total
    assert build_insider_event(small) is None


def test_build_insider_event_builds_a_real_event_for_a_large_purchase() -> None:
    big = _insider(
        transaction_type="P-Purchase", acquisition_or_disposition="A",
        securities_transacted=10_000, price=180.0, symbol="NVDA",  # $1.8M
    )
    event = build_insider_event(big)

    assert event is not None
    assert event.source == CapitalFlowSource.INSIDER
    assert event.symbol == "NVDA"
    assert event.direction == CapitalFlowDirection.BUY
    assert "bought" in event.headline
    assert "1,800,000" in event.headline or "$1,800,000" in event.headline


def test_build_insider_event_respects_a_custom_threshold() -> None:
    medium = _insider(securities_transacted=1000.0, price=100.0)  # $100,000
    assert build_insider_event(medium) is None  # below the $1M default
    assert build_insider_event(medium, min_value_usd=50_000.0) is not None  # above a lower custom bar


def test_build_insider_event_dedup_key_is_stable_and_unique_per_real_event() -> None:
    trade = _insider(symbol="AAPL", securities_transacted=100_000, price=200.0)
    event1 = build_insider_event(trade)
    event2 = build_insider_event(trade)
    assert event1.dedup_key == event2.dedup_key  # same underlying trade -> same key


# --- build_politician_event ---------------------------------------------------

def test_build_politician_event_filters_out_small_disclosures() -> None:
    small = _politician(amount_range="$1,001 - $15,000")
    assert build_politician_event(small) is None


def test_build_politician_event_builds_a_real_event_for_a_large_disclosure() -> None:
    big = _politician(
        chamber=CapitalFlowSource.SENATE, transaction_type="Sale",
        amount_range="$1,000,001 - $5,000,000", symbol="AAPL",
    )
    event = build_politician_event(big)

    assert event is not None
    assert event.source == CapitalFlowSource.SENATE
    assert event.direction == CapitalFlowDirection.SELL
    assert "Senator" in event.headline
    assert "$1,000,001 - $5,000,000" in event.headline


def test_build_politician_event_labels_house_members_correctly() -> None:
    big = _politician(chamber=CapitalFlowSource.HOUSE, amount_range="$1,000,001 - $5,000,000")
    event = build_politician_event(big)
    assert event is not None
    assert "Representative" in event.headline


def test_build_politician_event_returns_none_for_unparseable_amount() -> None:
    unparseable = _politician(amount_range="Over $50,000,000")
    assert build_politician_event(unparseable) is None


def test_defaults_are_the_documented_values() -> None:
    """Guards against a silent, undocumented threshold change."""
    assert DEFAULT_INSIDER_MIN_VALUE_USD == 1_000_000.0
    assert DEFAULT_POLITICIAN_MIN_VALUE_USD == 50_000.0


# --- build_volume_event -------------------------------------------------------

from datetime import date as _date
from src.domain.services.capital_flow_math import (
    DEFAULT_VOLUME_SPIKE_MULTIPLE,
    MIN_PRIOR_DAYS_REQUIRED,
    average_prior_volume,
    build_volume_event,
)


def test_average_prior_volume_excludes_todays_own_volume() -> None:
    """Regression guard: the baseline must never include the very
    day it's being compared against."""
    volumes = [90_000_000] + [30_000_000] * 20
    avg = average_prior_volume(volumes)
    assert avg == 30_000_000.0  # not pulled toward today's 90M at all


def test_average_prior_volume_returns_none_with_insufficient_history() -> None:
    short = [50_000_000, 30_000_000]  # only 1 prior day, below MIN_PRIOR_DAYS_REQUIRED
    assert average_prior_volume(short) is None


def test_build_volume_event_detects_a_real_hand_verified_spike() -> None:
    volumes = [90_000_000] + [30_000_000] * 20
    event = build_volume_event("NVDA", _date(2026, 8, 7), volumes)

    assert event is not None
    assert event.symbol == "NVDA"
    assert "3.0x" in event.headline
    assert event.dedup_key == "volume:NVDA:2026-08-07"


def test_build_volume_event_returns_none_for_normal_volume() -> None:
    volumes = [31_000_000] + [30_000_000] * 20  # ~1.03x, well below the 3x default
    assert build_volume_event("NVDA", _date(2026, 8, 7), volumes) is None


def test_build_volume_event_returns_none_with_insufficient_history() -> None:
    short = [50_000_000, 30_000_000]
    assert build_volume_event("NVDA", _date(2026, 8, 7), short) is None


def test_build_volume_event_respects_a_custom_spike_multiple() -> None:
    volumes = [45_000_000] + [30_000_000] * 20  # 1.5x
    assert build_volume_event("NVDA", _date(2026, 8, 7), volumes) is None  # below default 3x
    event = build_volume_event("NVDA", _date(2026, 8, 7), volumes, spike_multiple=1.4)
    assert event is not None  # above the custom, lower bar


def test_build_volume_event_direction_is_always_unknown() -> None:
    """A volume spike alone can't say which direction money moved —
    this function only receives volumes, never price, so it must
    never guess."""
    volumes = [90_000_000] + [30_000_000] * 20
    event = build_volume_event("NVDA", _date(2026, 8, 7), volumes)
    from src.domain.entities.capital_flow import CapitalFlowDirection
    assert event.direction == CapitalFlowDirection.UNKNOWN


def test_default_volume_constants_are_the_documented_values() -> None:
    assert MIN_PRIOR_DAYS_REQUIRED == 10
    assert DEFAULT_VOLUME_SPIKE_MULTIPLE == 3.0


# --- build_macro_flow_event ---------------------------------------------------

from src.domain.entities.economic_indicator import EconomicIndicatorReading
from src.domain.services.capital_flow_math import (
    DEFAULT_MACRO_FLOW_CHANGE_THRESHOLD,
    build_macro_flow_event,
    compute_macro_flow_change,
)


def _reading(value, as_of=date(2026, 4, 1)) -> EconomicIndicatorReading:
    return EconomicIndicatorReading(name="TEST", as_of=as_of, value=value)


def test_compute_macro_flow_change_hand_verified_cases() -> None:
    assert abs(compute_macro_flow_change(150_000, 80_000) - 0.875) < 1e-9  # +87.5%
    assert compute_macro_flow_change(-50_000, 30_000) < -2.0  # a real, meaningful sign-flip swing


def test_compute_macro_flow_change_returns_none_for_zero_prior() -> None:
    """Genuinely undefined, never fabricated as infinity or a capped value."""
    assert compute_macro_flow_change(10_000, 0) is None


def test_build_macro_flow_event_detects_a_real_large_move() -> None:
    event = build_macro_flow_event("TEST", "Test Series", _reading(150_000), _reading(80_000, date(2026, 1, 1)))

    assert event is not None
    assert event.source == CapitalFlowSource.MACRO
    assert event.symbol is None  # never forced onto a single ticker
    assert event.direction == CapitalFlowDirection.BUY
    assert "+87.5%" in event.headline


def test_build_macro_flow_event_direction_reflects_the_real_sign() -> None:
    event = build_macro_flow_event("TEST", "Test Series", _reading(-50_000), _reading(30_000, date(2026, 1, 1)))
    assert event is not None
    assert event.direction == CapitalFlowDirection.SELL


def test_build_macro_flow_event_returns_none_for_small_moves() -> None:
    event = build_macro_flow_event("TEST", "Test Series", _reading(100.0), _reading(98.0, date(2026, 1, 1)))
    assert event is None  # ~2% move, well below the 25% default threshold


def test_build_macro_flow_event_returns_none_when_change_is_undefined() -> None:
    event = build_macro_flow_event("TEST", "Test Series", _reading(10_000), _reading(0.0, date(2026, 1, 1)))
    assert event is None


def test_build_macro_flow_event_respects_a_custom_threshold() -> None:
    small_move = (_reading(102.0), _reading(100.0, date(2026, 1, 1)))  # 2% move
    assert build_macro_flow_event("TEST", "Test Series", *small_move) is None  # below default 25%
    event = build_macro_flow_event("TEST", "Test Series", *small_move, change_threshold=0.01)
    assert event is not None  # above a custom, lower 1% bar


def test_default_macro_flow_threshold_is_the_documented_value() -> None:
    assert DEFAULT_MACRO_FLOW_CHANGE_THRESHOLD == 0.25
