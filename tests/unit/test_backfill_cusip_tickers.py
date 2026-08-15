from datetime import date, datetime, timezone

from src.application.use_cases.backfill_cusip_tickers import BackfillCusipTickersUseCase
from src.application.use_cases.resolve_cusip_ticker import ResolveCusipTickerUseCase
from src.domain.entities.institutional_holding import InstitutionalHolding
from src.domain.entities.cusip_ticker_mapping import CusipTickerMapping
from src.domain.services.cusip_ticker_resolution import CusipSearchResult
from tests.unit.fakes import (
    FakeCusipSearchProvider,
    FakeCusipTickerMapRepository,
    FakeInstitutionalHoldingRepository,
)


def _holding(cusip) -> InstitutionalHolding:
    return InstitutionalHolding(
        accession_number="0001-26-000001", filer_cik="0001067983", filer_name="Berkshire Hathaway Inc",
        period_of_report=date(2026, 3, 31), issuer_name="SOME ISSUER", title_of_class="COM",
        cusip=cusip, value_usd=1000, shares_or_principal_amount=100, share_type="SH",
        put_call=None, investment_discretion="SOLE", voting_authority_sole=100,
        voting_authority_shared=0, voting_authority_none=0,
    )


def test_execute_resolves_every_unresolved_cusip_and_reports_correct_counts() -> None:
    holding_repo = FakeInstitutionalHoldingRepository()
    holding_repo.bulk_save([_holding("111111111"), _holding("222222222"), _holding("333333333")])

    ticker_map_repo = FakeCusipTickerMapRepository()
    search_provider = FakeCusipSearchProvider(results_by_cusip={
        "111111111": [CusipSearchResult(symbol="AAA", company_name="A Co", market_cap=1)],
        "222222222": [CusipSearchResult(symbol="BBB", company_name="B Co", market_cap=1)],
        "333333333": [],  # genuinely resolves to no US ticker
    })
    resolver = ResolveCusipTickerUseCase(ticker_map_repo, search_provider)
    use_case = BackfillCusipTickersUseCase(holding_repo, ticker_map_repo, resolver)

    result = use_case.execute()

    assert result.total_distinct_cusips == 3
    assert result.already_resolved == 0
    assert result.newly_attempted == 3
    assert result.newly_resolved_to_a_ticker == 2
    assert result.newly_resolved_to_no_ticker == 1
    assert result.errors == 0

    # And they're genuinely cached now, not just counted.
    assert ticker_map_repo.get("111111111").ticker == "AAA"
    assert ticker_map_repo.get("333333333").ticker is None


def test_execute_skips_already_resolved_cusips_without_calling_fmp_again() -> None:
    holding_repo = FakeInstitutionalHoldingRepository()
    holding_repo.bulk_save([_holding("111111111"), _holding("222222222")])

    ticker_map_repo = FakeCusipTickerMapRepository()
    ticker_map_repo.save(CusipTickerMapping(
        cusip="111111111", ticker="AAA", company_name="A Co", resolved_at=datetime.now(timezone.utc),
    ))
    search_provider = FakeCusipSearchProvider(results_by_cusip={
        "222222222": [CusipSearchResult(symbol="BBB", company_name="B Co", market_cap=1)],
    })
    resolver = ResolveCusipTickerUseCase(ticker_map_repo, search_provider)
    use_case = BackfillCusipTickersUseCase(holding_repo, ticker_map_repo, resolver)

    result = use_case.execute()

    assert result.total_distinct_cusips == 2
    assert result.already_resolved == 1
    assert result.newly_attempted == 1
    assert search_provider.search_cusip_calls == ["222222222"], "should never re-query an already-cached cusip"


def test_execute_counts_an_individual_resolution_error_without_aborting_the_rest() -> None:
    holding_repo = FakeInstitutionalHoldingRepository()
    holding_repo.bulk_save([_holding("111111111"), _holding("222222222")])

    class PartiallyFailingSearchProvider:
        def search_cusip(self, cusip):
            if cusip == "111111111":
                raise ConnectionError("network is down")
            return [CusipSearchResult(symbol="BBB", company_name="B Co", market_cap=1)]

    ticker_map_repo = FakeCusipTickerMapRepository()
    resolver = ResolveCusipTickerUseCase(ticker_map_repo, PartiallyFailingSearchProvider())
    use_case = BackfillCusipTickersUseCase(holding_repo, ticker_map_repo, resolver)

    result = use_case.execute()

    assert result.errors == 1
    assert result.newly_resolved_to_a_ticker == 1
    # The failed one must not be cached at all, so a future re-run retries it.
    assert ticker_map_repo.get("111111111") is None


def test_execute_calls_the_progress_callback_for_every_attempted_cusip() -> None:
    holding_repo = FakeInstitutionalHoldingRepository()
    holding_repo.bulk_save([_holding("111111111"), _holding("222222222")])

    ticker_map_repo = FakeCusipTickerMapRepository()
    search_provider = FakeCusipSearchProvider(results_by_cusip={})
    resolver = ResolveCusipTickerUseCase(ticker_map_repo, search_provider)
    use_case = BackfillCusipTickersUseCase(holding_repo, ticker_map_repo, resolver)

    progress_calls = []
    use_case.execute(on_progress=lambda i, total: progress_calls.append((i, total)))

    assert progress_calls == [(1, 2), (2, 2)]


def test_execute_with_nothing_ingested_returns_an_honest_all_zero_result() -> None:
    holding_repo = FakeInstitutionalHoldingRepository()
    ticker_map_repo = FakeCusipTickerMapRepository()
    resolver = ResolveCusipTickerUseCase(ticker_map_repo, FakeCusipSearchProvider())
    use_case = BackfillCusipTickersUseCase(holding_repo, ticker_map_repo, resolver)

    result = use_case.execute()

    assert result.total_distinct_cusips == 0
    assert result.newly_attempted == 0


def test_execute_with_limit_still_reports_the_true_already_resolved_count() -> None:
    """Regression guard for a real bug caught during self-review: the
    already_resolved count must reflect reality, not be distorted by
    limit truncating the work list -- limit is only meant to control
    how many NEW cusips get attempted this run, for a small test run
    before committing to the full backfill."""
    holding_repo = FakeInstitutionalHoldingRepository()
    holding_repo.bulk_save([
        _holding("111111111"), _holding("222222222"), _holding("333333333"), _holding("444444444"),
    ])

    ticker_map_repo = FakeCusipTickerMapRepository()
    ticker_map_repo.save(CusipTickerMapping(
        cusip="111111111", ticker="AAA", company_name="A Co", resolved_at=datetime.now(timezone.utc),
    ))
    search_provider = FakeCusipSearchProvider(results_by_cusip={
        "222222222": [CusipSearchResult(symbol="BBB", company_name="B Co", market_cap=1)],
    })
    resolver = ResolveCusipTickerUseCase(ticker_map_repo, search_provider)
    use_case = BackfillCusipTickersUseCase(holding_repo, ticker_map_repo, resolver)

    result = use_case.execute(limit=1)

    assert result.total_distinct_cusips == 4
    assert result.already_resolved == 1, "must reflect the real, true count, not be inflated by the limit"
    assert result.newly_attempted == 1, "limit correctly caps how many NEW cusips get attempted"
