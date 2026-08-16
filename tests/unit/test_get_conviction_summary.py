from datetime import date

from src.application.use_cases.get_conviction_summary import GetConvictionSummaryUseCase
from src.application.use_cases.get_institutional_holders import GetInstitutionalHoldersError
from src.application.use_cases.get_beneficial_ownership_disclosures import (
    GetBeneficialOwnershipDisclosuresError,
)
from src.application.use_cases.get_insider_transactions import GetInsiderTransactionsError
from src.application.use_cases.detect_position_changes import DetectPositionChangesError
from src.domain.entities.institutional_holding import InstitutionalHolding
from src.domain.entities.beneficial_ownership_disclosure import BeneficialOwnershipDisclosure
from src.domain.entities.insider_transaction import InsiderTransaction
from src.domain.entities.position_change import PositionChange
from src.domain.entities.company import Company, Sector
from tests.unit.fakes import FakeCompanyRepository


class _Result:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeGetInstitutionalHolders:
    def __init__(self, holders=None, raise_error=None):
        self._holders = holders or []
        self._raise_error = raise_error

    def execute(self, ticker, limit=20, as_of=None):
        if self._raise_error is not None:
            raise self._raise_error
        return _Result(issuer_query=ticker, holders=tuple(self._holders))


class FakeDetectPositionChanges:
    def __init__(self, changes_by_filer=None, raise_error=None):
        self._changes_by_filer = changes_by_filer or {}
        self._raise_error = raise_error

    def execute(self, filer_query, min_pct_change=0.0, as_of=None):
        if self._raise_error is not None:
            raise self._raise_error
        return _Result(changes=tuple(self._changes_by_filer.get(filer_query, [])))


class FakeGetBeneficialOwnershipDisclosures:
    def __init__(self, disclosures=None, raise_error=None):
        self._disclosures = disclosures or []
        self._raise_error = raise_error

    def execute(self, ticker):
        if self._raise_error is not None:
            raise self._raise_error
        return _Result(ticker=ticker, disclosures=tuple(self._disclosures))


class FakeGetInsiderTransactions:
    def __init__(self, transactions=None, raise_error=None):
        self._transactions = transactions or []
        self._raise_error = raise_error

    def execute(self, ticker):
        if self._raise_error is not None:
            raise self._raise_error
        return _Result(ticker=ticker, transactions=tuple(self._transactions))


def _holding(filer_name, cusip="037833100", shares=1000, value=150000) -> InstitutionalHolding:
    return InstitutionalHolding(
        accession_number="x", filer_cik="0001", filer_name=filer_name,
        period_of_report=date(2026, 3, 31), issuer_name="APPLE INC", title_of_class="COM",
        cusip=cusip, value_usd=value, shares_or_principal_amount=shares, share_type="SH",
        put_call=None, investment_discretion="SOLE", voting_authority_sole=shares,
        voting_authority_shared=0, voting_authority_none=0,
    )


def _change(cusip, change_type) -> PositionChange:
    return PositionChange(
        cusip=cusip, issuer_name="APPLE INC", change_type=change_type,
        prior_shares=500, current_shares=1000, prior_value_usd=75000, current_value_usd=150000,
        pct_change=1.0 if change_type == "increased" else None,
    )


def _disclosure(form_type) -> BeneficialOwnershipDisclosure:
    return BeneficialOwnershipDisclosure(
        cik="0001", symbol="AAPL", filing_date=date(2026, 6, 1), accepted_date=date(2026, 6, 1),
        cusip="037833100", name_of_reporting_person="Some Fund", citizenship_or_place_of_organization="DE",
        sole_voting_power=0, shared_voting_power=0, sole_dispositive_power=0, shared_dispositive_power=0,
        amount_beneficially_owned=1000, percent_of_class=0.06, type_of_reporting_person="IA",
        form_type=form_type, source_url="https://example.com",
    )


def _insider_txn(transaction_type, price) -> InsiderTransaction:
    return InsiderTransaction(
        symbol="AAPL", filing_date=date(2026, 6, 1), transaction_date=date(2026, 6, 1),
        reporting_cik="0001", company_cik="0001", reporting_name="Some Officer",
        type_of_owner="officer", transaction_type=transaction_type, acquisition_or_disposition="A",
        direct_or_indirect="D", security_name="Common Stock", securities_transacted=100,
        securities_owned=1000, price=price, source_url="https://example.com",
    )


def _use_case(
    holders=None, changes_by_filer=None, disclosures=None, transactions=None,
    holders_error=None, changes_error=None, disclosures_error=None, transactions_error=None,
    company_known=True,
) -> GetConvictionSummaryUseCase:
    company_repo = FakeCompanyRepository()
    if company_known:
        company_repo.save(Company(
            ticker="AAPL", name="APPLE INC", sector=Sector.TECHNOLOGY,
            industry="Consumer Electronics", exchange="NASDAQ", country="US",
        ))
    return GetConvictionSummaryUseCase(
        get_institutional_holders=FakeGetInstitutionalHolders(holders, holders_error),
        detect_position_changes=FakeDetectPositionChanges(changes_by_filer, changes_error),
        get_beneficial_ownership_disclosures=FakeGetBeneficialOwnershipDisclosures(disclosures, disclosures_error),
        get_insider_transactions=FakeGetInsiderTransactions(transactions, transactions_error),
        company_repository=company_repo,
    )


def test_all_three_signals_present_gives_signal_count_of_three() -> None:
    use_case = _use_case(
        holders=[_holding("Berkshire")],
        changes_by_filer={"Berkshire": [_change("037833100", "increased")]},
        disclosures=[_disclosure("13D")],
        transactions=[_insider_txn("P-Purchase", 150.0)],
    )

    result = use_case.execute("AAPL")

    assert result.institutional_signal is True
    assert result.activist_signal is True
    assert result.insider_signal is True
    assert result.signal_count == 3


def test_no_signals_present_gives_signal_count_of_zero() -> None:
    use_case = _use_case(
        holders=[_holding("BlackRock")],
        changes_by_filer={"BlackRock": [_change("037833100", "decreased")]},
        disclosures=[_disclosure("13G")],  # 13G, not 13D -- no activist signal
        transactions=[_insider_txn("M-Exempt", 0.0)],  # price=0, not a real purchase
    )

    result = use_case.execute("AAPL")

    assert result.institutional_signal is False
    assert result.activist_signal is False
    assert result.insider_signal is False
    assert result.signal_count == 0


def test_holder_with_no_matching_change_is_honestly_not_increasing() -> None:
    """Real, deliberate distinction: with min_pct_change=0.0, a
    holding genuinely absent from the changes list means no change was
    detected at all -- honestly false, not an unknown/None state."""
    use_case = _use_case(
        holders=[_holding("Vanguard", cusip="037833100")],
        changes_by_filer={"Vanguard": [_change("999999999", "increased")]},  # a different cusip entirely
    )

    result = use_case.execute("AAPL")

    assert result.institutional_holders[0].is_increasing is False
    assert result.institutional_signal is False


def test_a_real_error_checking_one_holders_changes_is_honestly_unknown_not_false() -> None:
    """Real, deliberate distinction from the test above: a genuine
    failure to check must never be silently treated the same as a
    confirmed "not increasing" -- None means genuinely couldn't
    determine, not "checked and found false"."""
    use_case = _use_case(
        holders=[_holding("Vanguard")],
        changes_error=DetectPositionChangesError("no data"),
    )

    result = use_case.execute("AAPL")

    assert result.institutional_holders[0].is_increasing is None
    assert result.institutional_signal is False


def test_institutional_holders_error_degrades_gracefully_without_crashing() -> None:
    use_case = _use_case(
        holders_error=GetInstitutionalHoldersError("no data"),
        disclosures=[_disclosure("13D")],
        transactions=[_insider_txn("P-Purchase", 100.0)],
    )

    result = use_case.execute("AAPL")

    assert result.institutional_holders == ()
    assert result.institutional_signal is False
    assert result.activist_signal is True  # other signals still work
    assert result.insider_signal is True


def test_activist_disclosures_error_degrades_gracefully_without_crashing() -> None:
    use_case = _use_case(disclosures_error=GetBeneficialOwnershipDisclosuresError("no data"))

    result = use_case.execute("AAPL")

    assert result.activist_disclosures_13d == ()
    assert result.activist_signal is False


def test_insider_transactions_error_degrades_gracefully_without_crashing() -> None:
    use_case = _use_case(transactions_error=GetInsiderTransactionsError("no data"))

    result = use_case.execute("AAPL")

    assert result.insider_purchases == ()
    assert result.insider_signal is False


def test_ticker_is_uppercased_in_the_result() -> None:
    use_case = _use_case()
    result = use_case.execute("aapl")
    assert result.ticker == "AAPL"


def test_institutional_signal_degrades_honestly_when_the_company_is_not_known_locally() -> None:
    """Real, confirmed bug caught before shipping: get_institutional_holders
    searches by company name, not ticker, since raw 13F data has no
    ticker field at all. A ticker this app hasn't ingested into its
    own companies table yet must degrade honestly to "not found",
    never fall back to searching for the raw ticker string itself
    (which would almost never match a real issuer_name)."""
    use_case = _use_case(
        company_known=False,
        holders=[_holding("Berkshire")],  # would show a false positive if the ticker were searched directly
        changes_by_filer={"Berkshire": [_change("037833100", "increased")]},
    )

    result = use_case.execute("AAPL")

    assert result.institutional_holders == ()
    assert result.institutional_signal is False
