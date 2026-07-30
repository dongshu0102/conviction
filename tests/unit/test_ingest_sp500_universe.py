from __future__ import annotations

from unittest.mock import patch

from src.application.interfaces.data_provider import DataProviderError
from src.application.use_cases.ingest_company_data import IngestCompanyDataUseCase
from src.application.use_cases.ingest_sp500_universe import IngestSP500UniverseUseCase
from src.domain.entities.company import Company, Sector
from tests.unit.fakes import (
    FakeCompanyRepository,
    FakeFinancialStatementRepository,
    ScriptedFailureDataProvider,
)


def _sample_company() -> Company:
    return Company(
        ticker="X", name="Test Co", sector=Sector.TECHNOLOGY,
        industry="Software", exchange="NASDAQ", country="US",
    )


def _build_use_case(provider: ScriptedFailureDataProvider) -> IngestSP500UniverseUseCase:
    ingest_company = IngestCompanyDataUseCase(
        provider, FakeCompanyRepository(), FakeFinancialStatementRepository()
    )
    # No real sleeping in tests — patch time.sleep for the whole module.
    return IngestSP500UniverseUseCase(
        provider, ingest_company, max_retries=3, base_backoff_seconds=0.01,
        request_delay_seconds=0.0,
    )


@patch("src.application.use_cases.ingest_sp500_universe.time.sleep")
def test_one_bad_ticker_does_not_abort_the_batch(mock_sleep) -> None:
    provider = ScriptedFailureDataProvider(
        company=_sample_company(),
        behaviors={
            "AAPL": [None],
            "BADTICKER": [DataProviderError("404 Not Found")],
            "MSFT": [None],
        },
    )
    use_case = _build_use_case(provider)

    result = use_case.execute(years=1)

    assert result.total_tickers == 3
    assert result.success_count == 2
    assert result.failure_count == 1
    assert result.failed[0].ticker == "BADTICKER"


@patch("src.application.use_cases.ingest_sp500_universe.time.sleep")
def test_transient_failure_is_retried_and_eventually_succeeds(mock_sleep) -> None:
    provider = ScriptedFailureDataProvider(
        company=_sample_company(),
        behaviors={
            # Fails twice with a transient-looking error, succeeds on 3rd try
            "FLAKY": [
                DataProviderError("timeout"),
                DataProviderError("timeout"),
                None,
            ],
        },
    )
    use_case = _build_use_case(provider)

    result = use_case.execute(years=1)

    assert result.success_count == 1
    assert result.failure_count == 0
    assert provider.call_counts["FLAKY"] == 3


@patch("src.application.use_cases.ingest_sp500_universe.time.sleep")
def test_402_error_is_not_retried(mock_sleep) -> None:
    provider = ScriptedFailureDataProvider(
        company=_sample_company(),
        behaviors={
            "PLANLOCKED": [DataProviderError("402 Payment Required")],
        },
    )
    use_case = _build_use_case(provider)

    result = use_case.execute(years=1)

    assert result.failure_count == 1
    # Only ONE call — a plan restriction will never succeed on retry,
    # so retrying would just waste quota against the daily call limit.
    assert provider.call_counts["PLANLOCKED"] == 1


@patch("src.application.use_cases.ingest_sp500_universe.time.sleep")
def test_explicit_ticker_list_overrides_live_universe_fetch(mock_sleep) -> None:
    provider = ScriptedFailureDataProvider(
        company=_sample_company(),
        behaviors={"AAPL": [None], "MSFT": [None], "IGNORED": [None]},
    )
    use_case = _build_use_case(provider)

    result = use_case.execute(years=1, tickers=["AAPL", "MSFT"])

    assert result.total_tickers == 2
    assert "IGNORED" not in provider.call_counts or provider.call_counts["IGNORED"] == 0
