from datetime import date

from src.domain.entities.institutional_holding import InstitutionalHolding
from src.domain.services.institutional_holding_aggregation import aggregate_holdings_by_cusip


def _holding(cusip, issuer_name, shares, value) -> InstitutionalHolding:
    return InstitutionalHolding(
        accession_number="0001-26-000001", filer_cik="0001067983", filer_name="Berkshire Hathaway Inc",
        period_of_report=date(2026, 3, 31), issuer_name=issuer_name, title_of_class="COM",
        cusip=cusip, value_usd=value, shares_or_principal_amount=shares, share_type="SH",
        put_call=None, investment_discretion="SOLE", voting_authority_sole=shares,
        voting_authority_shared=0, voting_authority_none=0,
    )


def test_sums_shares_and_value_across_multiple_line_items_for_the_same_cusip() -> None:
    """Real, confirmed scenario: a single filing can legitimately split
    the same security across multiple line items (different
    voting-authority categories for different subsidiary managers)."""
    holdings = [
        _holding("037833100", "APPLE INC", 30_000_000, 20_000_000_000),
        _holding("037833100", "APPLE INC", 20_000_000, 15_000_000_000),
    ]

    result = aggregate_holdings_by_cusip(holdings)

    assert len(result) == 1
    assert result[0].cusip == "037833100"
    assert result[0].total_shares == 50_000_000
    assert result[0].total_value_usd == 35_000_000_000


def test_keeps_different_cusips_separate() -> None:
    holdings = [
        _holding("037833100", "APPLE INC", 100, 1000),
        _holding("594918104", "MICROSOFT CORP", 200, 2000),
    ]

    result = aggregate_holdings_by_cusip(holdings)

    by_cusip = {r.cusip: r for r in result}
    assert len(result) == 2
    assert by_cusip["037833100"].total_shares == 100
    assert by_cusip["594918104"].total_shares == 200


def test_empty_list_returns_empty_list() -> None:
    assert aggregate_holdings_by_cusip([]) == []


def test_single_holding_passes_through_unchanged() -> None:
    holdings = [_holding("037833100", "APPLE INC", 500, 50_000)]

    result = aggregate_holdings_by_cusip(holdings)

    assert len(result) == 1
    assert result[0].total_shares == 500
    assert result[0].total_value_usd == 50_000
