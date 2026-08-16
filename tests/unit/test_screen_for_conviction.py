from datetime import datetime, timezone

from src.application.use_cases.screen_for_conviction import ScreenForConvictionUseCase
from src.domain.entities.conviction_summary import ConvictionSummary


class FakeGetConvictionSummary:
    def __init__(self, summaries=None, raise_for=None):
        self._summaries = summaries or {}
        self._raise_for = raise_for or {}
        self.calls = []

    def execute(self, ticker):
        self.calls.append(ticker)
        if ticker in self._raise_for:
            raise self._raise_for[ticker]
        return self._summaries.get(ticker, ConvictionSummary(
            ticker=ticker, institutional_holders=(), institutional_signal=False,
            activist_disclosures_13d=(), activist_signal=False,
            insider_purchases=(), insider_signal=False, signal_count=0,
        ))


class FakeConvictionScreenerRepository:
    def __init__(self):
        self.saved_batches = []

    def save_batch(self, results):
        self.saved_batches.append(results)

    def get_latest_as_of(self):
        return None

    def get_all(self, min_signal_count=0):
        return []


def test_all_tickers_succeed_and_are_saved() -> None:
    summary_aapl = ConvictionSummary(
        ticker="AAPL", institutional_holders=(), institutional_signal=True,
        activist_disclosures_13d=(), activist_signal=False,
        insider_purchases=(), insider_signal=False, signal_count=1,
    )
    get_summary = FakeGetConvictionSummary(summaries={"AAPL": summary_aapl})
    repo = FakeConvictionScreenerRepository()
    use_case = ScreenForConvictionUseCase(get_summary, repo)

    result = use_case.execute(["AAPL", "MSFT"])

    assert result.total_tickers == 2
    assert result.succeeded == 2
    assert result.failed == ()
    assert len(repo.saved_batches) == 1
    saved = repo.saved_batches[0]
    assert len(saved) == 2
    aapl_result = next(r for r in saved if r.ticker == "AAPL")
    assert aapl_result.signal_count == 1
    assert aapl_result.institutional_signal is True


def test_one_tickers_failure_does_not_abort_the_others() -> None:
    """The single most important test for this use case: a genuine,
    unexpected failure on one ticker must never prevent the other
    tickers from being scanned and saved."""
    get_summary = FakeGetConvictionSummary(raise_for={"BROKEN": Exception("db timeout")})
    repo = FakeConvictionScreenerRepository()
    use_case = ScreenForConvictionUseCase(get_summary, repo)

    result = use_case.execute(["AAPL", "BROKEN", "MSFT"])

    assert result.total_tickers == 3
    assert result.succeeded == 2
    assert len(result.failed) == 1
    assert result.failed[0].ticker == "BROKEN"
    assert "db timeout" in result.failed[0].error
    # Confirms the two good tickers were genuinely still saved, not
    # silently dropped alongside the one that failed.
    saved_tickers = {r.ticker for r in repo.saved_batches[0]}
    assert saved_tickers == {"AAPL", "MSFT"}


def test_all_results_in_one_batch_share_the_same_as_of_timestamp() -> None:
    get_summary = FakeGetConvictionSummary()
    repo = FakeConvictionScreenerRepository()
    use_case = ScreenForConvictionUseCase(get_summary, repo)

    use_case.execute(["AAPL", "MSFT"])

    saved = repo.saved_batches[0]
    assert saved[0].as_of == saved[1].as_of
    assert saved[0].as_of.tzinfo is not None


def test_empty_ticker_list_still_saves_an_empty_batch() -> None:
    get_summary = FakeGetConvictionSummary()
    repo = FakeConvictionScreenerRepository()
    use_case = ScreenForConvictionUseCase(get_summary, repo)

    result = use_case.execute([])

    assert result.total_tickers == 0
    assert result.succeeded == 0
    assert repo.saved_batches == [[]]
