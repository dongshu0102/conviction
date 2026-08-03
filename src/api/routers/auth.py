"""Real authentication: signup and login.

Both return a genuine, standard API key — the same ApiKeyCreatedSchema
shape as POST /api-keys, deliberately. See manage_auth.py for the full
reasoning: this is the ONLY place a brand-new identity is ever created
now (previously POST /api-keys accepted an arbitrary user_id from
anyone, with zero proof of ownership — closed as part of this change).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.api.schemas import (
    ApiKeyCreatedSchema,
    ForgotPasswordRequestSchema,
    GenericMessageSchema,
    LogInRequestSchema,
    ResetPasswordRequestSchema,
    SignUpRequestSchema,
)
from src.application.use_cases.manage_api_keys import CreateApiKeyUseCase
from src.application.use_cases.manage_auth import (
    InvalidCredentialsError,
    LogInUseCase,
    SignUpUseCase,
    UserAlreadyExistsError,
    WeakPasswordError,
)
from src.application.use_cases.manage_password_reset import (
    InvalidOrExpiredTokenError,
    RequestPasswordResetUseCase,
    ResetPasswordUseCase,
)
from src.infrastructure.config import get_settings
from src.infrastructure.email.ses_email_sender import SesEmailSender
from src.infrastructure.persistence.api_key_repository_impl import SqlAlchemyApiKeyRepository
from src.infrastructure.persistence.password_reset_token_repository_impl import (
    SqlAlchemyPasswordResetTokenRepository,
)
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


# --- Password reset -----------------------------------------------------------

def get_token_repository() -> SqlAlchemyPasswordResetTokenRepository:
    return SqlAlchemyPasswordResetTokenRepository()


def get_request_reset_use_case(
    user_repo: SqlAlchemyUserRepository = Depends(get_user_repository),
    token_repo: SqlAlchemyPasswordResetTokenRepository = Depends(get_token_repository),
) -> RequestPasswordResetUseCase:
    settings = get_settings()
    return RequestPasswordResetUseCase(
        user_repo, token_repo, SesEmailSender(settings), settings.frontend_base_url
    )


def get_reset_password_use_case(
    user_repo: SqlAlchemyUserRepository = Depends(get_user_repository),
    token_repo: SqlAlchemyPasswordResetTokenRepository = Depends(get_token_repository),
) -> ResetPasswordUseCase:
    return ResetPasswordUseCase(user_repo, token_repo, SqlAlchemyApiKeyRepository())


def get_create_api_key_use_case_for_reset() -> CreateApiKeyUseCase:
    return CreateApiKeyUseCase(SqlAlchemyApiKeyRepository())


_GENERIC_RESET_MESSAGE = (
    "If an account exists for that email, a password reset link has been sent."
)


@router.post("/forgot-password", response_model=GenericMessageSchema)
def forgot_password(
    body: ForgotPasswordRequestSchema,
    use_case: RequestPasswordResetUseCase = Depends(get_request_reset_use_case),
) -> GenericMessageSchema:
    """Always returns the same message regardless of whether the email
    is registered — see manage_password_reset.py for the full
    reasoning. Never raises for a nonexistent email or a failed send;
    both are handled silently by the use case itself."""
    use_case.execute(body.email)
    return GenericMessageSchema(message=_GENERIC_RESET_MESSAGE)


@router.post("/reset-password", response_model=ApiKeyCreatedSchema)
def reset_password(
    body: ResetPasswordRequestSchema,
    reset_use_case: ResetPasswordUseCase = Depends(get_reset_password_use_case),
    create_api_key: CreateApiKeyUseCase = Depends(get_create_api_key_use_case_for_reset),
) -> ApiKeyCreatedSchema:
    """On success, also mints a fresh API key — every key issued
    before the reset was just revoked (see the use case), so the
    caller needs a new one to keep using the account, same as
    signup/login already do."""
    try:
        user_id = reset_use_case.execute(body.token, body.new_password)
    except (InvalidOrExpiredTokenError, WeakPasswordError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    record, plaintext_key = create_api_key.execute(user_id, "password-reset")
    return ApiKeyCreatedSchema(
        plaintext_key=plaintext_key, key_prefix=record.key_prefix,
        user_id=record.user_id, name=record.name, created_at=record.created_at,
    )
