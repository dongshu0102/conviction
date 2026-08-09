"""Tests for the capital-flow parsing functions, using the exact real
payloads confirmed directly against the live FMP API tonight — not
invented examples."""
from __future__ import annotations

from datetime import date

from src.domain.entities.capital_flow import CapitalFlowSource
from src.infrastructure.data_providers.fmp_parsing import (
    parse_latest_house_trades,
    parse_latest_insider_trades,
    parse_latest_senate_trades,
)

# Real payload confirmed directly against /stable/insider-trading/latest tonight.
_REAL_INSIDER_PAYLOAD = [
    {
        "symbol": "JEF", "filingDate": "2026-08-07", "transactionDate": "2026-08-07",
        "reportingCik": "0001275002", "companyCik": "0000096223", "transactionType": "G-Gift",
        "securitiesOwned": 2008247, "reportingName": "FRIEDMAN BRIAN P",
        "typeOfOwner": "director, officer: President", "acquisitionOrDisposition": "D",
        "directOrIndirect": "D", "formType": "4", "securitiesTransacted": 81734,
        "price": 0, "securityName": "Common Stock",
        "url": "https://www.sec.gov/Archives/edgar/data/96223/000121465926009794/0001214659-26-009794-index.htm",
    },
]

# Real payload confirmed directly against /stable/senate-latest tonight.
_REAL_SENATE_PAYLOAD = [
    {
        "symbol": "O", "senateID": "P000595", "disclosureDate": "2026-08-07",
        "transactionDate": "2026-07-23", "firstName": "Gary", "lastName": "Peters",
        "office": "Gary Peters", "district": "MI", "owner": "Self",
        "assetDescription": "Realty Income Corp", "assetType": "REIT", "type": "Purchase",
        "amount": "$1,001 - $15,000", "comment": "",
        "link": "https://efdsearch.senate.gov/search/view/ptr/328a9b36-1205-4117-bdc4-cd7c3ccbcbbc/",
    },
]

# Real payload confirmed directly against /stable/house-latest tonight —
# note the real, confirmed quirk: owner is genuinely an empty string,
# and the field is called "senateID" even though this is House data.
_REAL_HOUSE_PAYLOAD = [
    {
        "symbol": "GOOGL", "senateID": "T000490", "disclosureDate": "2026-08-07",
        "transactionDate": "2026-07-17", "firstName": "David", "lastName": "Taylor",
        "office": "David Taylor", "district": "OH02", "owner": "",
        "assetDescription": "Alphabet Inc", "assetType": "Stock", "type": "Purchase",
        "amount": "$1,001 - $15,000", "capitalGainsOver200USD": "False", "comment": "",
        "link": "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/20035146.pdf",
    },
]


def test_parse_latest_insider_trades_matches_real_response_shape() -> None:
    trades = parse_latest_insider_trades(_REAL_INSIDER_PAYLOAD)

    assert len(trades) == 1
    trade = trades[0]
    assert trade.symbol == "JEF"
    assert trade.filing_date == date(2026, 8, 7)
    assert trade.transaction_date == date(2026, 8, 7)
    assert trade.reporting_name == "FRIEDMAN BRIAN P"
    assert trade.transaction_type == "G-Gift"
    assert trade.acquisition_or_disposition == "D"
    assert trade.securities_transacted == 81734.0
    assert trade.price == 0.0  # confirmed real: gifts genuinely report price 0


def test_parse_latest_senate_trades_matches_real_response_shape() -> None:
    trades = parse_latest_senate_trades(_REAL_SENATE_PAYLOAD)

    assert len(trades) == 1
    trade = trades[0]
    assert trade.chamber == CapitalFlowSource.SENATE
    assert trade.symbol == "O"
    assert trade.person_name == "Gary Peters"  # built from firstName + lastName
    assert trade.owner == "Self"
    assert trade.transaction_type == "Purchase"
    assert trade.amount_range == "$1,001 - $15,000"  # never parsed to a number here


def test_parse_latest_house_trades_matches_real_response_shape() -> None:
    trades = parse_latest_house_trades(_REAL_HOUSE_PAYLOAD)

    assert len(trades) == 1
    trade = trades[0]
    assert trade.chamber == CapitalFlowSource.HOUSE
    assert trade.person_name == "David Taylor"
    # Regression test for a real, confirmed quirk: House data can
    # report owner as a genuine empty string, not "Self" — must be
    # preserved as-is, never silently defaulted.
    assert trade.owner == ""


def test_insider_and_politician_parsers_return_empty_list_not_error_for_bad_shape() -> None:
    assert parse_latest_insider_trades({"unexpected": "shape"}) == []
    assert parse_latest_senate_trades(None) == []
    assert parse_latest_house_trades("not a list") == []


def test_insider_parser_skips_malformed_row_without_crashing() -> None:
    broken = [
        dict(_REAL_INSIDER_PAYLOAD[0]),
        {"symbol": "X"},  # missing every other required field
    ]
    trades = parse_latest_insider_trades(broken)
    assert len(trades) == 1  # only the well-formed row survives


def test_politician_parser_skips_malformed_row_without_crashing() -> None:
    broken = [
        dict(_REAL_SENATE_PAYLOAD[0]),
        {"symbol": "X"},  # missing firstName, lastName, etc.
    ]
    trades = parse_latest_senate_trades(broken)
    assert len(trades) == 1
