"""Pilot validation script — Phase 1, next step 1.

Ingests a sector-diverse pilot set of real S&P 500 tickers against the
running API, then reports which typed fields came back null across the
batch. This is the concrete gate before step 2 (bulk ingestion): if FMP's
free tier is silently missing fields we care about, we want to know now,
against 15 tickers, not after a 500-company batch job.

Usage:
    python scripts/validate_pilot_tickers.py [--base-url http://localhost:8000]

Requires the API to be running (docker run ... or uvicorn --reload) and a
valid FMP_API_KEY already configured in the app's environment.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict

import httpx

# One or two tickers per sector, deliberately not all mega-cap tech —
# international-flavored and smaller-cap names are more likely to reveal
# free-tier data gaps than AAPL/MSFT will.
PILOT_TICKERS = [
    "AAPL",  # Technology
    "MSFT",  # Technology
    "JPM",   # Financials
    "BRK-B", # Financials (also tests ticker punctuation handling)
    "XOM",   # Energy
    "JNJ",   # Healthcare
    "PG",    # Consumer Staples
    "HD",    # Consumer Discretionary
    "CAT",   # Industrials
    "NEE",   # Utilities
    "LIN",   # Materials
    "AMT",   # Real Estate
    "T",     # Communication Services
    "SMCI",  # smaller-cap tech, more likely to expose gaps
    "CZR",   # smaller-cap consumer disc, same reasoning
]

# Fields we actually rely on for Phase 2 analysis — a gap here matters.
# A gap in a field we don't use yet is noted but not flagged as critical.
CRITICAL_INCOME_FIELDS = ["revenue", "net_income", "operating_income", "eps_diluted"]
CRITICAL_BALANCE_FIELDS = ["total_assets", "total_liabilities", "total_equity"]
CRITICAL_CASHFLOW_FIELDS = ["operating_cash_flow", "free_cash_flow"]


def ingest_and_fetch(client: httpx.Client, ticker: str) -> dict | None:
    try:
        resp = client.post(f"/companies/{ticker}/ingest", params={"years": 3}, timeout=30)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        print(f"  INGEST FAILED  {ticker}: {exc.response.status_code} {exc.response.text[:200]}")
        return None
    except httpx.HTTPError as exc:
        print(f"  INGEST FAILED  {ticker}: {exc}")
        return None

    try:
        resp = client.get(f"/companies/{ticker}", timeout=30)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        print(f"  READ FAILED    {ticker}: {exc}")
        return None


def check_nulls(record: dict, fields: list[str]) -> list[str]:
    return [f for f in fields if record.get(f) is None]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    null_report: dict[str, list[str]] = defaultdict(list)
    failures: list[str] = []
    succeeded = 0

    with httpx.Client(base_url=args.base_url) as client:
        for ticker in PILOT_TICKERS:
            print(f"Ingesting {ticker}...")
            data = ingest_and_fetch(client, ticker)
            if data is None:
                failures.append(ticker)
                continue

            succeeded += 1
            if data["income_statements"]:
                gaps = check_nulls(data["income_statements"][0], CRITICAL_INCOME_FIELDS)
                if gaps:
                    null_report[ticker].extend(f"income.{g}" for g in gaps)
            else:
                null_report[ticker].append("income_statements: EMPTY")

            if data["balance_sheets"]:
                gaps = check_nulls(data["balance_sheets"][0], CRITICAL_BALANCE_FIELDS)
                if gaps:
                    null_report[ticker].extend(f"balance.{g}" for g in gaps)
            else:
                null_report[ticker].append("balance_sheets: EMPTY")

            if data["cash_flow_statements"]:
                gaps = check_nulls(data["cash_flow_statements"][0], CRITICAL_CASHFLOW_FIELDS)
                if gaps:
                    null_report[ticker].extend(f"cashflow.{g}" for g in gaps)
            else:
                null_report[ticker].append("cash_flow_statements: EMPTY")

            time.sleep(0.5)  # be polite to the free tier's rate limit

    print(f"\n{'='*60}")
    print(f"RESULT: {succeeded}/{len(PILOT_TICKERS)} ingested successfully")

    if failures:
        print(f"\nFAILED TICKERS ({len(failures)}):")
        for t in failures:
            print(f"  - {t}")

    if null_report:
        print(f"\nDATA GAPS FOUND ({len(null_report)} tickers affected):")
        for ticker, gaps in null_report.items():
            print(f"  {ticker}: {', '.join(gaps)}")
        print(
            "\n-> If gaps cluster on specific fields across many tickers, "
            "that field is likely unavailable on the free tier — decide "
            "whether to drop it, backfill from elsewhere, or upgrade the plan."
        )
    else:
        print("\nNo critical field gaps found in the pilot set.")

    if not failures and not null_report:
        print("\nPILOT VALIDATION: PASS — safe to proceed to bulk ingestion (step 2).")
        return 0

    print("\nPILOT VALIDATION: ISSUES FOUND — review before building bulk ingestion.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
