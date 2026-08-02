"""Tests for SuggestThemeUseCase — the grounding guarantee (no LLM
call without real headlines), the already_ingested flag correctness
(the structural safety net against ticker hallucination), and error
paths for an unsupported/failing provider."""
from __future__ import annotations

from datetime import datetime, timezone

from src.application.interfaces.data_provider import DataProviderError
from src.application.use_cases.suggest_theme import (
    GeneralNewsUnavailableError,
    NoNewsAvailableError,
    SuggestThemeUseCase,
)
from src.domain.entities.company import Company, Sector
from src.domain.entities.general_news import GeneralNewsHeadline
from tests.unit.fakes import (
    FakeCompanyRepository,
    FakeDataProvider,
    FakeThemeSuggestionGenerator,
)

NOW = datetime.now(timezone.utc)


def _headline(title: str) -> GeneralNewsHeadline:
    return GeneralNewsHeadline(title=title, published_at=NOW, publisher="Test", url=None, snippet=None)


class _NewsProvider(FakeDataProvider):
    def __init__(self, *args, headlines=None, fail=False, **kwargs):
        super().__init__(*args, **kwargs)
        self._headlines = headlines if headlines is not None else [_headline("Real headline")]
        self._fail = fail

    def get_general_news(self, limit=20):
        if self._fail:
            raise DataProviderError("news down")
        return self._headlines


def test_grounding_llm_never_called_without_real_headlines() -> None:
    """The exact production-safety guarantee: an empty news result
    must never reach the generator at all."""
    company_repo = FakeCompanyRepository()
    provider = _NewsProvider(company=None, headlines=[])
    generator = FakeThemeSuggestionGenerator()
    use_case = SuggestThemeUseCase(provider, company_repo, generator)

    try:
        use_case.execute()
        raise AssertionError("expected NoNewsAvailableError")
    except NoNewsAvailableError:
        pass
    assert generator.received_headlines is None  # never called


def test_already_ingested_flag_reflects_real_company_repo_state() -> None:
    """The structural safety net: a suggested ticker already in the
    system is flagged True; one that isn't is flagged False, so the
    caller knows exactly which candidates need a real ingestion
    attempt (which would itself catch a hallucinated ticker)."""
    from src.application.interfaces.theme_suggestion_generator import (
        SuggestedTickerResult,
        ThemeSuggestionGenerationResult,
    )

    company_repo = FakeCompanyRepository()
    company_repo.save(Company(ticker="AAPL", name="Apple", sector=Sector.TECHNOLOGY,
                                industry="X", exchange="X", country="US"))
    provider = _NewsProvider(company=None, headlines=[_headline("Real headline")])
    generator = FakeThemeSuggestionGenerator(result=ThemeSuggestionGenerationResult(
        theme_name="Test", rationale="Test",
        candidate_tickers=[
            SuggestedTickerResult(ticker="AAPL", company_name="Apple", reasoning="Known"),
            SuggestedTickerResult(ticker="ZZZZ", company_name="Fake Co", reasoning="Unknown"),
        ],
        model_used="test", raw_response={},
    ))
    use_case = SuggestThemeUseCase(provider, company_repo, generator)

    result = use_case.execute()

    by_ticker = {c.ticker: c for c in result.candidate_tickers}
    assert by_ticker["AAPL"].already_ingested is True
    assert by_ticker["ZZZZ"].already_ingested is False


def test_user_hint_passed_through_to_generator() -> None:
    company_repo = FakeCompanyRepository()
    provider = _NewsProvider(company=None)
    generator = FakeThemeSuggestionGenerator()
    use_case = SuggestThemeUseCase(provider, company_repo, generator)

    use_case.execute(user_hint="reshoring")

    assert generator.received_user_hint == "reshoring"
    assert len(generator.received_headlines) == 1  # real headlines were passed


def test_provider_without_general_news_support_raises_clean_error() -> None:
    company_repo = FakeCompanyRepository()
    provider = FakeDataProvider(company=None)  # no get_general_news override
    generator = FakeThemeSuggestionGenerator()
    use_case = SuggestThemeUseCase(provider, company_repo, generator)

    try:
        use_case.execute()
        raise AssertionError("expected GeneralNewsUnavailableError")
    except GeneralNewsUnavailableError:
        pass
    assert generator.received_headlines is None


def test_provider_failure_raises_clean_error_not_crash() -> None:
    company_repo = FakeCompanyRepository()
    provider = _NewsProvider(company=None, fail=True)
    generator = FakeThemeSuggestionGenerator()
    use_case = SuggestThemeUseCase(provider, company_repo, generator)

    try:
        use_case.execute()
        raise AssertionError("expected GeneralNewsUnavailableError")
    except GeneralNewsUnavailableError:
        pass


def test_sourced_headlines_included_for_transparency() -> None:
    company_repo = FakeCompanyRepository()
    provider = _NewsProvider(company=None, headlines=[
        _headline("Headline one"), _headline("Headline two"),
    ])
    generator = FakeThemeSuggestionGenerator()
    use_case = SuggestThemeUseCase(provider, company_repo, generator)

    result = use_case.execute()

    assert "Headline one" in result.sourced_headlines
    assert "Headline two" in result.sourced_headlines
