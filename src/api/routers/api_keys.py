"""API key management routes.

POST /api-keys is deliberately open (no auth required to call it) —
there is no login/signup system yet, so creating a key IS the closest
equivalent to signing up. This is a known, documented MVP shortcut: in
a real product, key creation would require an authenticated session
(you'd log in first, then generate API keys from your account
settings). Flagging this explicitly rather than pretending the auth
story is more complete than it is.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

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
    user_id: str = Query(..., description="Choose any identifier — this is your account id"),
    name: str = Query(..., description="A label to identify this key later, e.g. 'CLI key'"),
    use_case: CreateApiKeyUseCase = Depends(get_create_use_case),
) -> ApiKeyCreatedSchema:
    record, plaintext_key = use_case.execute(user_id, name)
    return ApiKeyCreatedSchema(
        plaintext_key=plaintext_key, key_prefix=record.key_prefix,
        user_id=record.user_id, name=record.name, created_at=record.created_at,
    )


@router.get("", response_model=list[ApiKeySummarySchema])
def list_api_keys(
    user_id: str = Query(...),
    use_case: ListApiKeysUseCase = Depends(get_list_use_case),
) -> list[ApiKeySummarySchema]:
    """Lists key metadata only — never the plaintext, which is
    unrecoverable by design after creation."""
    return [
        ApiKeySummarySchema(
            key_prefix=k.key_prefix, user_id=k.user_id, name=k.name,
            is_active=k.is_active, created_at=k.created_at,
        )
        for k in use_case.execute(user_id)
    ]
