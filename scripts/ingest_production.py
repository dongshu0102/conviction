"""Bulk-ingest scripts/sp500_tickers.txt into a running Conviction API.

Unlike scripts/ingest_sp500.py (which talks to the database directly and
is meant for local/CI use against a reachable DATABASE_URL), this script
talks to the API over HTTP — the only safe way to seed data into
production, since RDS is deliberately not publicly reachable and
shouldn't be reopened just to run a seeding script.

Uses only the Python standard library (urllib) — no dependency install
needed, so this runs the same way in any environment with just Python 3.

Usage:
    CONVICTION_API_KEY=fi_live_... python3 scripts/ingest_production.py
    CONVICTION_API_KEY=fi_live_... python3 scripts/ingest_production.py \
        --api-url http://localhost:8000  # to target local dev instead
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    import certifi

    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    # Fall back to system defaults if certifi isn't installed — on most
    # Linux environments (including CI) this works fine; it's specifically
    # macOS's system Python that tends to need certifi's bundle explicitly.
    _SSL_CONTEXT = None

DEFAULT_API_URL = "https://p8xpcshdn9.us-east-1.awsapprunner.com"
DEFAULT_TICKERS_FILE = Path(__file__).resolve().parent / "sp500_tickers.txt"
REQUEST_DELAY_SECONDS = 1.0  # be gentle on FMP's rate limit across ~175 * 4 calls


def load_tickers(path: Path) -> list[str]:
    return [
        line.strip().upper()
        for line in path.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def ingest_one(api_url: str, api_key: str, ticker: str, years: int) -> tuple[bool, str]:
    url = f"{api_url}/companies/{ticker}/ingest?years={years}"
    req = urllib.request.Request(url, method="POST", headers={"X-Api-Key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=60, context=_SSL_CONTEXT) as resp:
            body = json.loads(resp.read().decode())
            return True, (
                f"income={body.get('income_statements_ingested')} "
                f"balance={body.get('balance_sheets_ingested')} "
                f"cashflow={body.get('cash_flow_statements_ingested')}"
            )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:200]
        return False, f"HTTP {exc.code}: {detail}"
    except urllib.error.URLError as exc:
        return False, f"Connection error: {exc.reason}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--tickers-file", default=str(DEFAULT_TICKERS_FILE))
    parser.add_argument("--years", type=int, default=5)
    args = parser.parse_args()

    api_key = os.environ.get("CONVICTION_API_KEY")
    if not api_key:
        print("ERROR: set CONVICTION_API_KEY environment variable first.", file=sys.stderr)
        return 1

    tickers = load_tickers(Path(args.tickers_file))
    print(f"Ingesting {len(tickers)} tickers into {args.api_url} ...\n")

    succeeded, failed = [], []
    for i, ticker in enumerate(tickers, start=1):
        ok, detail = ingest_one(args.api_url, api_key, ticker, args.years)
        status = "OK  " if ok else "FAIL"
        print(f"[{i}/{len(tickers)}] {status} {ticker}: {detail}")
        (succeeded if ok else failed).append(ticker)
        time.sleep(REQUEST_DELAY_SECONDS)

    print(f"\n{'='*60}")
    print(f"DONE: {len(succeeded)} succeeded, {len(failed)} failed")
    if failed:
        print(f"\nFailed tickers: {', '.join(failed)}")
        print(
            "\nRe-run just these with a trimmed tickers file, or investigate "
            "individually — a handful of failures (delisted/renamed tickers) "
            "is normal and not worth blocking on."
        )
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
