from datetime import date

from src.application.use_cases.get_insider_transactions import (
    GetInsiderTransactionsError,
    GetInsiderTransactionsUseCase,
)
from src.domain.entities.insider_transaction import InsiderTransaction


def _transaction(
    reporting_name, filing_date, transaction_type="S-Sale",
    symbol="AAPL", price=100.0, acquisition_or_disposition="D",
) -> InsiderTransaction:
    return InsiderTransaction(
        symbol=symbol, filing_date=filing_date, transaction_date=filing_date,
        reporting_cik="0001780525", company_cik="0000320193",
        reporting_name=reporting_name, type_of_owner="officer",
        transaction_type=transaction_type, acquisition_or_disposition=acquisition_or_disposition,
        direct_or_indirect="D", security_name="Common Stock",
        securities_transacted=1000.0, securities_owned=5000.0, price=price,
        source_url="https://example.com/filing.htm",
    )


class FakeInsiderTransactionProvider:
    def __init__(self, transactions_by_symbol: dict | None = None, raise_not_implemented: bool = False):
        self._transactions_by_symbol = transactions_by_symbol or {}
        self._raise_not_implemented = raise_not_implemented
        self.calls = []

    def get_insider_transactions(self, symbol: str):
        self.calls.append(symbol)
        if self._raise_not_implemented:
            raise NotImplementedError("not supported")
        return self._transactions_by_symbol.get(symbol, [])


def test_execute_uppercases_the_ticker_before_calling_the_provider() -> None:
    provider = FakeInsiderTransactionProvider()
    use_case = GetInsiderTransactionsUseCase(provider)

    result = use_case.execute("aapl")

    assert result.ticker == "AAPL"
    assert provider.calls == ["AAPL"]


def test_execute_returns_transactions_sorted_most_recent_first() -> None:
    provider = FakeInsiderTransactionProvider(transactions_by_symbol={
        "AAPL": [
            _transaction("Older Insider", date(2026, 6, 17)),
            _transaction("Newest Insider", date(2026, 8, 13)),
            _transaction("Middle Insider", date(2026, 7, 1)),
        ],
    })
    use_case = GetInsiderTransactionsUseCase(provider)

    result = use_case.execute("AAPL")

    names = [t.reporting_name for t in result.transactions]
    assert names == ["Newest Insider", "Middle Insider", "Older Insider"]


def test_execute_preserves_a_genuine_zero_price_honestly() -> None:
    """Real, confirmed scenario: an M-Exempt option-exercise/RSU-vesting
    event has price=0, a real, honest reflection of a routine
    compensation event, not missing data -- must never be silently
    dropped or coerced into something else."""
    provider = FakeInsiderTransactionProvider(transactions_by_symbol={
        "AAPL": [_transaction("Some Officer", date(2026, 6, 17), transaction_type="M-Exempt", price=0.0)],
    })
    use_case = GetInsiderTransactionsUseCase(provider)

    result = use_case.execute("AAPL")

    assert result.transactions[0].price == 0.0
    assert result.transactions[0].transaction_type == "M-Exempt"


def test_execute_returns_an_empty_result_honestly_when_no_transactions_exist() -> None:
    provider = FakeInsiderTransactionProvider()
    use_case = GetInsiderTransactionsUseCase(provider)

    result = use_case.execute("ZZZZ")

    assert result.transactions == ()


def test_execute_raises_a_clear_error_when_the_provider_does_not_support_this() -> None:
    provider = FakeInsiderTransactionProvider(raise_not_implemented=True)
    use_case = GetInsiderTransactionsUseCase(provider)

    try:
        use_case.execute("AAPL")
        assert False, "expected GetInsiderTransactionsError"
    except GetInsiderTransactionsError:
        pass
