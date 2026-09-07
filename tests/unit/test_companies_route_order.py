"""Regression test for a real, confirmed routing-shadow bug: FastAPI
matches routes in registration order, so a literal path like
/companies/screen-market declared AFTER the generic GET /{ticker}
catch-all would be silently shadowed -- a request to it would be
matched as ticker="screen-market" and never reach the real route.

Same real routing-conflict discipline already applied to
/orders/history vs /orders/{order_id} earlier tonight, now with an
explicit, automated test rather than only a one-time manual check.
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://fake:fake@localhost:5432/fake")
os.environ.setdefault("ANTHROPIC_API_KEY", "fake")
os.environ.setdefault("FMP_API_KEY", "fake")

from starlette.routing import Route

from src.api.main import app


def test_screen_market_is_registered_before_the_generic_ticker_route() -> None:
    companies_get_paths = [
        r.path for r in app.routes
        if isinstance(r, Route) and r.path.startswith("/companies") and "GET" in r.methods
    ]

    screen_market_index = companies_get_paths.index("/companies/screen-market")
    ticker_catch_all_index = companies_get_paths.index("/companies/{ticker}")

    assert screen_market_index < ticker_catch_all_index, (
        "GET /companies/screen-market must be registered BEFORE GET /companies/{ticker} "
        "or it will be silently shadowed by the catch-all route."
    )
