from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers import admin, alerts, api_keys, auth, beneficial_ownership, brief, brokerage, capital_flow, capital_flow_monitor, chat, companies, conviction_summary, growth_candidates, insider_transactions, institutional_holdings, market_structure, master_lens, portfolios, research, universe, watchlist
from src.infrastructure.config import get_settings

settings = get_settings()
logging.basicConfig(level=settings.log_level)

app = FastAPI(
    title="Conviction API",
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
app.include_router(auth.router)
app.include_router(brief.router)
app.include_router(chat.router)
app.include_router(universe.router)
app.include_router(admin.router)
app.include_router(growth_candidates.router)
app.include_router(capital_flow.router)
app.include_router(capital_flow_monitor.router)
app.include_router(institutional_holdings.router)
app.include_router(beneficial_ownership.router)
app.include_router(insider_transactions.router)
app.include_router(brokerage.router)
app.include_router(conviction_summary.router)
app.include_router(master_lens.router)
app.include_router(market_structure.router)


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

    # This IS a data operation, not a schema one — safe here. Bootstraps
    # the very first admin: if bootstrap_admin_email is configured and
    # a matching account already exists, ensure it has the admin role.
    # Idempotent (checks before writing), does nothing if the account
    # hasn't signed up yet (promotion happens on the next startup after
    # they do), and never touches any other account.
    if settings.bootstrap_admin_email:
        from dataclasses import replace

        from src.domain.entities.user import Role
        from src.infrastructure.persistence.user_repository_impl import (
            SqlAlchemyUserRepository,
        )

        user_repo = SqlAlchemyUserRepository()
        user_id = settings.bootstrap_admin_email.strip().lower()
        user = user_repo.get_by_user_id(user_id)
        if user is not None and user.role != Role.ADMIN:
            user_repo.save(replace(user, role=Role.ADMIN))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/dependencies")
def health_dependencies():
    """Actually verifies critical external dependencies work — not
    just that this process is alive. Deliberately separate from
    GET /health above: that one drives App Runner's own decision about
    whether to keep routing traffic here, and making it depend on a
    third party's uptime would let a temporary Anthropic hiccup cause
    App Runner to start cycling an otherwise-healthy container.

    This endpoint exists for real, external monitoring — poll it from
    an uptime-checking tool on its own schedule, independent of
    container lifecycle. This is the direct fix for the incident where
    the Anthropic key went invalid and sat silently broken (chat,
    daily briefs, theme suggestion, research all down) until someone
    happened to manually test an unrelated new feature.

    Returns 200 if every dependency is healthy, 503 if any aren't —
    matters because most uptime tools alert on status code, not body
    content."""
    import anthropic
    from fastapi.responses import JSONResponse

    from src.application.use_cases.check_dependency_health import (
        CheckDependencyHealthUseCase,
    )
    from src.infrastructure.persistence.database import session_scope

    use_case = CheckDependencyHealthUseCase(
        anthropic_client=anthropic.Anthropic(api_key=settings.anthropic_api_key),
        anthropic_model=settings.anthropic_model,
        db_session_factory=session_scope,
    )
    report = use_case.execute()

    return JSONResponse(
        status_code=200 if report.all_healthy else 503,
        content={
            "all_healthy": report.all_healthy,
            "checks": [
                {"name": c.name, "healthy": c.healthy, "detail": c.detail} for c in report.checks
            ],
        },
    )
