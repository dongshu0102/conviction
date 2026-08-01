from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers import alerts, api_keys, brief, chat, companies, portfolios, research, universe, watchlist
from src.infrastructure.config import get_settings

settings = get_settings()
logging.basicConfig(level=settings.log_level)

app = FastAPI(
    title="FinInsight API",
    description="AI Financial Intelligence Platform — Phase 1: financial data foundation",
    version="0.1.0",
)

# Allows the browser-based frontend (a different origin/domain) to call this
# API directly. Wide open ("*") is a deliberate MVP simplification — there's
# no cookie-based session to protect (auth is a bearer-style X-Api-Key header,
# which CORS wildcarding doesn't expose), but this should be tightened to the
# frontend's real domain once that's stable, rather than left open forever.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(companies.router)
app.include_router(research.router)
app.include_router(watchlist.router)
app.include_router(portfolios.router)
app.include_router(alerts.router)
app.include_router(api_keys.router)
app.include_router(brief.router)
app.include_router(chat.router)
app.include_router(universe.router)


@app.on_event("startup")
def on_startup() -> None:
    # Deliberately NOT calling init_db()/create_all() here anymore.
    # Now that Alembic manages the schema, letting the app silently
    # create tables on every startup causes exactly the kind of
    # stamp/upgrade mismatches we hit during development: a new column
    # or table shows up via create_all() before a migration for it
    # exists, and `alembic upgrade` then fails with "already exists."
    # Schema changes go through `alembic upgrade head` — run that as an
    # explicit step (locally, or as a deploy step in CI) before starting
    # the app, not implicitly on every process start.
    pass


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
