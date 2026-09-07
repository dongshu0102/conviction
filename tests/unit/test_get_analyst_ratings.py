from __future__ import annotations

from datetime import date

from src.application.use_cases.get_analyst_ratings import GetAnalystRatingsUseCase
from src.domain.entities.analyst_ratings import AnalystGrade, AnalystRatings


class _FakeAnalystRatingsProvider:
    def __init__(self, ratings: AnalystRatings | None = None) -> None:
        self._ratings = ratings
        self.last_ticker_called: str | None = None

    def get_analyst_ratings(self, ticker: str) -> AnalystRatings | None:
        self.last_ticker_called = ticker
        return self._ratings


def _ratings(ticker: str = "AAPL") -> AnalystRatings:
    return AnalystRatings(
        ticker=ticker,
        recent_grades=[
            AnalystGrade(
                grading_company="DA Davidson", date=date(2026, 9, 2),
                previous_grade="Neutral", new_grade="Neutral", action="maintain",
            ),
        ],
        last_month_avg_price_target=331.83, last_month_count=2,
        last_quarter_avg_price_target=331.69, last_quarter_count=17,
        last_year_avg_price_target=309.56, last_year_count=69,
    )


def test_returns_real_ratings_from_the_provider() -> None:
    provider = _FakeAnalystRatingsProvider(_ratings())
    use_case = GetAnalystRatingsUseCase(provider)

    result = use_case.execute("AAPL")

    assert result is not None
    assert result.recent_grades[0].grading_company == "DA Davidson"


def test_normalizes_ticker_case_and_whitespace() -> None:
    provider = _FakeAnalystRatingsProvider(_ratings())
    use_case = GetAnalystRatingsUseCase(provider)

    use_case.execute(" aapl ")

    assert provider.last_ticker_called == "AAPL"


def test_returns_honestly_none_for_a_ticker_with_no_real_coverage() -> None:
    provider = _FakeAnalystRatingsProvider(ratings=None)
    use_case = GetAnalystRatingsUseCase(provider)

    result = use_case.execute("OBSCURETICKER")

    assert result is None
