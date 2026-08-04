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
from src.domain.entities.user import Role
from src.infrastructure.persistence.api_key_repository_impl import SqlAlchemyApiKeyRepository
from src.infrastructure.persistence.user_repository_impl import SqlAlchemyUserRepository


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


def get_user_repository() -> SqlAlchemyUserRepository:
    return SqlAlchemyUserRepository()


def get_admin_user_id(
    user_id: str = Depends(get_authenticated_user_id),
    user_repo: SqlAlchemyUserRepository = Depends(get_user_repository),
) -> str:
    """Same as get_authenticated_user_id, plus a real role check. Fails
    closed: an API key with no corresponding users row (e.g. one that
    predates the role column) is denied, not silently treated as
    admin. Unlike password reset's deliberately vague errors, this is
    a genuine authorization boundary — a plain, honest 403 is correct
    here, not a security concern to hide."""
    user = user_repo.get_by_user_id(user_id)
    if user is None or user.role != Role.ADMIN:
        raise HTTPException(status_code=403, detail="This endpoint requires an admin account.")
    return user_id
