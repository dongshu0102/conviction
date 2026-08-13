from src.domain.entities.aggregated_position import AggregatedPosition
from src.domain.services.position_change_detection import detect_position_changes


def test_identical_shares_with_different_value_is_not_a_change() -> None:
    """Regression guard for a real, confirmed finding against actual
    ingested data: Berkshire Hathaway's Apple stake showed an
    IDENTICAL share count across two real quarters while value_usd
    changed by billions, purely from the stock's price moving, not any
    actual buying or selling. A value-based signal would have falsely
    flagged this as trading activity."""
    prior = [AggregatedPosition(cusip="037833100", issuer_name="APPLE INC", total_shares=227917808, total_value_usd=61960000000)]
    current = [AggregatedPosition(cusip="037833100", issuer_name="APPLE INC", total_shares=227917808, total_value_usd=57840000000)]

    changes = detect_position_changes(prior, current)

    assert changes == []


def test_a_security_only_in_current_is_a_new_position() -> None:
    prior: list = []
    current = [AggregatedPosition(cusip="594918104", issuer_name="MICROSOFT CORP", total_shares=1000, total_value_usd=500_000)]

    changes = detect_position_changes(prior, current)

    assert len(changes) == 1
    assert changes[0].change_type == "new"
    assert changes[0].prior_shares == 0
    assert changes[0].current_shares == 1000
    assert changes[0].pct_change is None


def test_a_security_only_in_prior_is_a_closed_position() -> None:
    prior = [AggregatedPosition(cusip="594918104", issuer_name="MICROSOFT CORP", total_shares=1000, total_value_usd=500_000)]
    current: list = []

    changes = detect_position_changes(prior, current)

    assert len(changes) == 1
    assert changes[0].change_type == "closed"
    assert changes[0].prior_shares == 1000
    assert changes[0].current_shares == 0
    assert changes[0].pct_change is None


def test_more_shares_in_current_is_an_increase_with_correct_pct() -> None:
    prior = [AggregatedPosition(cusip="037833100", issuer_name="APPLE INC", total_shares=100_000, total_value_usd=25_000_000)]
    current = [AggregatedPosition(cusip="037833100", issuer_name="APPLE INC", total_shares=150_000, total_value_usd=38_000_000)]

    changes = detect_position_changes(prior, current)

    assert len(changes) == 1
    assert changes[0].change_type == "increased"
    assert abs(changes[0].pct_change - 0.5) < 0.0001


def test_fewer_shares_in_current_is_a_decrease_with_correct_pct() -> None:
    prior = [AggregatedPosition(cusip="037833100", issuer_name="APPLE INC", total_shares=100_000, total_value_usd=25_000_000)]
    current = [AggregatedPosition(cusip="037833100", issuer_name="APPLE INC", total_shares=80_000, total_value_usd=20_000_000)]

    changes = detect_position_changes(prior, current)

    assert len(changes) == 1
    assert changes[0].change_type == "decreased"
    assert abs(changes[0].pct_change - (-0.2)) < 0.0001


def test_min_pct_change_filters_small_changes_but_always_keeps_new_and_closed() -> None:
    prior = [
        AggregatedPosition(cusip="AAA", issuer_name="TINY CHANGE CO", total_shares=100_000, total_value_usd=1_000_000),
        AggregatedPosition(cusip="BBB", issuer_name="CLOSED CO", total_shares=5_000, total_value_usd=50_000),
    ]
    current = [
        AggregatedPosition(cusip="AAA", issuer_name="TINY CHANGE CO", total_shares=100_500, total_value_usd=1_005_000),  # +0.5%
        AggregatedPosition(cusip="CCC", issuer_name="NEW CO", total_shares=2_000, total_value_usd=20_000),
    ]

    changes = detect_position_changes(prior, current, min_pct_change=0.01)  # 1% threshold

    change_types = {c.cusip: c.change_type for c in changes}
    assert "AAA" not in change_types, "0.5% change should be filtered out by a 1% threshold"
    assert change_types.get("BBB") == "closed"
    assert change_types.get("CCC") == "new"


def test_an_untouched_position_produces_no_change_at_all() -> None:
    prior = [AggregatedPosition(cusip="037833100", issuer_name="APPLE INC", total_shares=100_000, total_value_usd=25_000_000)]
    current = [AggregatedPosition(cusip="037833100", issuer_name="APPLE INC", total_shares=100_000, total_value_usd=25_000_000)]

    changes = detect_position_changes(prior, current)

    assert changes == []


def test_empty_portfolios_produce_no_changes() -> None:
    assert detect_position_changes([], []) == []


def test_handles_multiple_simultaneous_changes_of_different_types() -> None:
    prior = [
        AggregatedPosition(cusip="AAA", issuer_name="INCREASED CO", total_shares=1000, total_value_usd=10_000),
        AggregatedPosition(cusip="BBB", issuer_name="DECREASED CO", total_shares=1000, total_value_usd=10_000),
        AggregatedPosition(cusip="CCC", issuer_name="CLOSED CO", total_shares=1000, total_value_usd=10_000),
        AggregatedPosition(cusip="DDD", issuer_name="UNCHANGED CO", total_shares=1000, total_value_usd=10_000),
    ]
    current = [
        AggregatedPosition(cusip="AAA", issuer_name="INCREASED CO", total_shares=2000, total_value_usd=20_000),
        AggregatedPosition(cusip="BBB", issuer_name="DECREASED CO", total_shares=500, total_value_usd=5_000),
        AggregatedPosition(cusip="DDD", issuer_name="UNCHANGED CO", total_shares=1000, total_value_usd=10_000),
        AggregatedPosition(cusip="EEE", issuer_name="NEW CO", total_shares=1000, total_value_usd=10_000),
    ]

    changes = detect_position_changes(prior, current)

    change_types = {c.cusip: c.change_type for c in changes}
    assert change_types == {"AAA": "increased", "BBB": "decreased", "CCC": "closed", "EEE": "new"}
    assert "DDD" not in change_types


def test_prior_total_shares_of_exactly_zero_does_not_crash_and_counts_as_new() -> None:
    """Regression guard for a real, confirmed production bug: FMR LLC
    (Fidelity's parent company) genuinely has real positions where the
    prior quarter's aggregated share count sums to exactly zero, even
    though the cusip is present in that quarter's raw data (confirmed
    directly against real production data -- not hypothetical). The
    original code divided by prior.total_shares unconditionally,
    crashing with a real ZeroDivisionError the moment a real user
    asked about this real filer. Economically this IS a new position
    -- the filer effectively held zero of this security before."""
    prior = [AggregatedPosition(cusip="921935706", issuer_name="SOME ISSUER", total_shares=0, total_value_usd=5000)]
    current = [AggregatedPosition(cusip="921935706", issuer_name="SOME ISSUER", total_shares=10000, total_value_usd=2_500_000)]

    changes = detect_position_changes(prior, current)

    assert len(changes) == 1
    assert changes[0].change_type == "new"
    assert changes[0].prior_shares == 0
    assert changes[0].current_shares == 10000
    assert changes[0].pct_change is None


def test_both_periods_zero_shares_produces_no_change() -> None:
    prior = [AggregatedPosition(cusip="X", issuer_name="X CO", total_shares=0, total_value_usd=0)]
    current = [AggregatedPosition(cusip="X", issuer_name="X CO", total_shares=0, total_value_usd=0)]

    assert detect_position_changes(prior, current) == []


def test_current_total_shares_of_zero_with_nonzero_prior_is_a_clean_hundred_percent_decrease() -> None:
    """The mirror-image case: this one was already safe (dividing by a
    non-zero prior.total_shares), but worth a permanent regression test
    given how close it sits to the actual bug."""
    prior = [AggregatedPosition(cusip="Y", issuer_name="Y CO", total_shares=5000, total_value_usd=1_000_000)]
    current = [AggregatedPosition(cusip="Y", issuer_name="Y CO", total_shares=0, total_value_usd=0)]

    changes = detect_position_changes(prior, current)

    assert len(changes) == 1
    assert changes[0].change_type == "decreased"
    assert changes[0].pct_change == -1.0
