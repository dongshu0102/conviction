from datetime import date

from src.application.use_cases.get_beneficial_ownership_disclosures import (
    GetBeneficialOwnershipDisclosuresError,
    GetBeneficialOwnershipDisclosuresUseCase,
)
from src.domain.entities.beneficial_ownership_disclosure import BeneficialOwnershipDisclosure


def _disclosure(
    name_of_reporting_person, filing_date, form_type="13G",
    symbol="AAPL", cusip="037833100", percent_of_class=0.05,
) -> BeneficialOwnershipDisclosure:
    return BeneficialOwnershipDisclosure(
        cik="0000320193", symbol=symbol, filing_date=filing_date, accepted_date=filing_date,
        cusip=cusip, name_of_reporting_person=name_of_reporting_person,
        citizenship_or_place_of_organization="DELAWARE",
        sole_voting_power=0, shared_voting_power=0, sole_dispositive_power=0, shared_dispositive_power=0,
        amount_beneficially_owned=1000, percent_of_class=percent_of_class,
        type_of_reporting_person="IA", form_type=form_type,
        source_url=f"https://example.com/SCHEDULE_{form_type}/doc.xml",
    )


class FakeBeneficialOwnershipProvider:
    def __init__(self, disclosures_by_symbol: dict | None = None, raise_not_implemented: bool = False):
        self._disclosures_by_symbol = disclosures_by_symbol or {}
        self._raise_not_implemented = raise_not_implemented
        self.calls = []

    def get_beneficial_ownership_disclosures(self, symbol: str):
        self.calls.append(symbol)
        if self._raise_not_implemented:
            raise NotImplementedError("not supported")
        return self._disclosures_by_symbol.get(symbol, [])


def test_execute_uppercases_the_ticker_before_calling_the_provider() -> None:
    provider = FakeBeneficialOwnershipProvider()
    use_case = GetBeneficialOwnershipDisclosuresUseCase(provider)

    result = use_case.execute("aapl")

    assert result.ticker == "AAPL"
    assert provider.calls == ["AAPL"]


def test_execute_returns_disclosures_sorted_most_recent_first() -> None:
    provider = FakeBeneficialOwnershipProvider(disclosures_by_symbol={
        "AAPL": [
            _disclosure("Older Fund", date(2025, 7, 29)),
            _disclosure("Newest Fund", date(2026, 4, 29)),
            _disclosure("Middle Fund", date(2026, 3, 26)),
        ],
    })
    use_case = GetBeneficialOwnershipDisclosuresUseCase(provider)

    result = use_case.execute("AAPL")

    names = [d.name_of_reporting_person for d in result.disclosures]
    assert names == ["Newest Fund", "Middle Fund", "Older Fund"]


def test_execute_preserves_both_13d_and_13g_form_types_distinctly() -> None:
    """The single most important distinction this feature exists to
    surface honestly -- activist intent vs. passive accumulation."""
    provider = FakeBeneficialOwnershipProvider(disclosures_by_symbol={
        "ETWO": [
            _disclosure("Glazer Capital, LLC", date(2025, 8, 14), form_type="13G"),
            _disclosure("Temasek Capital (Private) Limited", date(2025, 8, 11), form_type="13D"),
        ],
    })
    use_case = GetBeneficialOwnershipDisclosuresUseCase(provider)

    result = use_case.execute("ETWO")

    form_types = {d.name_of_reporting_person: d.form_type for d in result.disclosures}
    assert form_types["Glazer Capital, LLC"] == "13G"
    assert form_types["Temasek Capital (Private) Limited"] == "13D"


def test_execute_returns_an_empty_result_honestly_when_no_disclosures_exist() -> None:
    provider = FakeBeneficialOwnershipProvider()
    use_case = GetBeneficialOwnershipDisclosuresUseCase(provider)

    result = use_case.execute("ZZZZ")

    assert result.disclosures == ()


def test_execute_raises_a_clear_error_when_the_provider_does_not_support_this() -> None:
    provider = FakeBeneficialOwnershipProvider(raise_not_implemented=True)
    use_case = GetBeneficialOwnershipDisclosuresUseCase(provider)

    try:
        use_case.execute("AAPL")
        assert False, "expected GetBeneficialOwnershipDisclosuresError"
    except GetBeneficialOwnershipDisclosuresError:
        pass


def test_execute_handles_a_null_citizenship_field_gracefully() -> None:
    """Regression guard for a real, confirmed production bug: a real,
    live e2open disclosure had citizenshipOrPlaceOfOrganization as a
    genuine null, not merely an empty string, crashing the response
    with a Pydantic validation error the moment a real user asked
    about this real, actual company. citizenship_or_place_of_organization
    is genuinely nullable on the entity, not defensively stringified,
    since forcing a fallback string would misrepresent data that was
    never actually disclosed."""
    disclosure = _disclosure("Some Reporting Person", date(2025, 8, 11))
    disclosure_with_null_citizenship = BeneficialOwnershipDisclosure(
        cik=disclosure.cik, symbol=disclosure.symbol, filing_date=disclosure.filing_date,
        accepted_date=disclosure.accepted_date, cusip=disclosure.cusip,
        name_of_reporting_person=disclosure.name_of_reporting_person,
        citizenship_or_place_of_organization=None,  # the exact real, confirmed null value
        sole_voting_power=0, shared_voting_power=0, sole_dispositive_power=0, shared_dispositive_power=0,
        amount_beneficially_owned=0, percent_of_class=0.0,
        type_of_reporting_person=None, form_type="13D", source_url=disclosure.source_url,
    )
    provider = FakeBeneficialOwnershipProvider(disclosures_by_symbol={
        "ETWO": [disclosure_with_null_citizenship],
    })
    use_case = GetBeneficialOwnershipDisclosuresUseCase(provider)

    result = use_case.execute("ETWO")  # must not raise

    assert result.disclosures[0].citizenship_or_place_of_organization is None
