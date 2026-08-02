"""API key management routes.

POST /api-keys now requires an already-authenticated caller (a valid
existing key) rather than accepting an arbitrary user_id from anyone —
this is what closes the impersonation gap that existed before real
auth (see manage_auth.py): previously, anyone could mint a key for ANY
user_id string with zero proof of ownership. The FIRST key for a new
identity now only ever comes from POST /auth/signup, which requires a
real password no one else knows. This endpoint is for creating
ADDITIONAL keys for an identity you already hold (e.g. one for the web
session, a separate one for MCP/CLI use).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.auth import get_authenticated_user_id
from src.api.schemas import ApiKeyCreatedSchema, ApiKeySummarySchema
from src.application.use_cases.manage_api_keys import CreateApiKeyUseCase, ListApiKeysUseCase
from src.infrastructure.persistence.api_key_repository_impl import SqlAlchemyApiKeyRepository

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


def get_api_key_repository() -> SqlAlchemyApiKeyRepository:
    return SqlAlchemyApiKeyRepository()


def get_create_use_case(
    repo: SqlAlchemyApiKeyRepository = Depends(get_api_key_repository),
) -> CreateApiKeyUseCase:
    return CreateApiKeyUseCase(repo)


def get_list_use_case(
    repo: SqlAlchemyApiKeyRepository = Depends(get_api_key_repository),
) -> ListApiKeysUseCase:
    return ListApiKeysUseCase(repo)


@router.post("", response_model=ApiKeyCreatedSchema)
def create_api_key(
    name: str,
    user_id: str = Depends(get_authenticated_user_id),
    use_case: CreateApiKeyUseCase = Depends(get_create_use_case),
) -> ApiKeyCreatedSchema:
    record, plaintext_key = use_case.execute(user_id, name)
    return ApiKeyCreatedSchema(
        plaintext_key=plaintext_key, key_prefix=record.key_prefix,
        user_id=record.user_id, name=record.name, created_at=record.created_at,
    )


@router.get("", response_model=list[ApiKeySummarySchema])
def list_api_keys(
    user_id: str = Depends(get_authenticated_user_id),
    use_case: ListApiKeysUseCase = Depends(get_list_use_case),
) -> list[ApiKeySummarySchema]:
    """Lists key metadata only — never the plaintext, which is
    unrecoverable by design after creation. Now scoped to the
    authenticated caller's own keys, not an arbitrary user_id."""
    return [
        ApiKeySummarySchema(
            key_prefix=k.key_prefix, user_id=k.user_id, name=k.name,
            is_active=k.is_active, created_at=k.created_at,
        )
        for k in use_case.execute(user_id)
    ]
