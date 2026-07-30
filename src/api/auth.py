"""Authentication dependency, shared across routers.

Replaces the `user_id: str = Query(default="default")` pattern used in
watchlist/portfolio/alert routes through Phase 3 and 4 — that was always
documented as an unauthenticated MVP placeholder, and this is what
closes that gap for the routes where it actually matters (user-owned
data). Company data routes (research, analysis, valuation) stay public
on purpose — they're not user-owned, there's nothing to protect.
"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException

from src.application.use_cases.manage_api_keys import ValidateApiKeyUseCase
from src.infrastructure.persistence.api_key_repository_impl import SqlAlchemyApiKeyRepository


def get_api_key_repository() -> SqlAlchemyApiKeyRepository:
    return SqlAlchemyApiKeyRepository()


def get_validate_api_key_use_case(
    repo: SqlAlchemyApiKeyRepository = Depends(get_api_key_repository),
) -> ValidateApiKeyUseCase:
    return ValidateApiKeyUseCase(repo)


def get_authenticated_user_id(
    x_api_key: str = Header(default="", description="Your API key, e.g. fi_live_..."),
    use_case: ValidateApiKeyUseCase = Depends(get_validate_api_key_use_case),
) -> str:
    user_id = use_case.execute(x_api_key)
    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid API key. Pass it in the X-Api-Key header. "
            "Create one via POST /api-keys.",
        )
    return user_id
