from datetime import date

from src.domain.services.form_13f_freshness import latest_expected_complete_period


def test_on_the_exact_deadline_date_that_quarter_counts_as_complete() -> None:
    """Real, confirmed scenario: today (per this session) is exactly
    August 14, 2026, the real Q2 2026 13F deadline. Deadline day is
    inclusive -- the quarter counts as expected-complete on the
    deadline itself, not only the day after."""
    assert latest_expected_complete_period(date(2026, 8, 14)) == date(2026, 6, 30)


def test_the_day_before_a_deadline_the_prior_quarter_is_still_the_latest() -> None:
    assert latest_expected_complete_period(date(2026, 8, 13)) == date(2026, 3, 31)


def test_the_day_after_a_deadline_that_quarter_is_the_latest() -> None:
    assert latest_expected_complete_period(date(2026, 8, 15)) == date(2026, 6, 30)


def test_before_any_known_deadline_returns_none_honestly() -> None:
    assert latest_expected_complete_period(date(2026, 1, 1)) is None


def test_past_the_last_known_deadline_returns_the_last_known_period() -> None:
    assert latest_expected_complete_period(date(2029, 3, 1)) == date(2028, 12, 31)


def test_crossing_a_year_boundary_deadline_works_correctly() -> None:
    """4Q deadlines land in February of the following year -- a real
    case worth its own explicit check given the year rollover."""
    assert latest_expected_complete_period(date(2027, 2, 16)) == date(2026, 12, 31)
    assert latest_expected_complete_period(date(2027, 2, 15)) == date(2026, 9, 30)
