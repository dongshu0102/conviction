"""Real authentication: signup and login.

Both return a genuine, standard API key — the same ApiKeyCreatedSchema
shape as POST /api-keys, deliberately. See manage_auth.py for the full
reasoning: this is the ONLY place a brand-new identity is ever created
now (previously POST /api-keys accepted an arbitrary user_id from
anyone, with zero proof of ownership — closed as part of this change).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.api.schemas import ApiKeyCreatedSchema, LogInRequestSchema, SignUpRequestSchema
from src.application.use_cases.manage_api_keys import CreateApiKeyUseCase
from src.application.use_cases.manage_auth import (
    InvalidCredentialsError,
    LogInUseCase,
    SignUpUseCase,
    UserAlreadyExistsError,
    WeakPasswordError,
)
from src.infrastructure.persistence.api_key_repository_impl import SqlAlchemyApiKeyRepository
from src.infrastructure.persistence.user_repository_impl import SqlAlchemyUserRepository

router = APIRouter(prefix="/auth", tags=["auth"])


def get_user_repository() -> SqlAlchemyUserRepository:
    return SqlAlchemyUserRepository()


def get_signup_use_case(
    user_repo: SqlAlchemyUserRepository = Depends(get_user_repository),
) -> SignUpUseCase:
    create_api_key = CreateApiKeyUseCase(SqlAlchemyApiKeyRepository())
    return SignUpUseCase(user_repo, create_api_key)


def get_login_use_case(
    user_repo: SqlAlchemyUserRepository = Depends(get_user_repository),
) -> LogInUseCase:
    create_api_key = CreateApiKeyUseCase(SqlAlchemyApiKeyRepository())
    return LogInUseCase(user_repo, create_api_key)


@router.post("/signup", response_model=ApiKeyCreatedSchema)
def signup(
    body: SignUpRequestSchema,
    use_case: SignUpUseCase = Depends(get_signup_use_case),
) -> ApiKeyCreatedSchema:
    try:
        record, plaintext_key = use_case.execute(body.email, body.password)
    except (WeakPasswordError, UserAlreadyExistsError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ApiKeyCreatedSchema(
        plaintext_key=plaintext_key, key_prefix=record.key_prefix,
        user_id=record.user_id, name=record.name, created_at=record.created_at,
    )


@router.post("/login", response_model=ApiKeyCreatedSchema)
def login(
    body: LogInRequestSchema,
    use_case: LogInUseCase = Depends(get_login_use_case),
) -> ApiKeyCreatedSchema:
    try:
        record, plaintext_key = use_case.execute(body.email, body.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return ApiKeyCreatedSchema(
        plaintext_key=plaintext_key, key_prefix=record.key_prefix,
        user_id=record.user_id, name=record.name, created_at=record.created_at,
    )
