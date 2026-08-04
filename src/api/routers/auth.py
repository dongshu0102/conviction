"""Real authentication: signup and login.

Both return a genuine, standard API key — the same ApiKeyCreatedSchema
shape as POST /api-keys, deliberately. See manage_auth.py for the full
reasoning: this is the ONLY place a brand-new identity is ever created
now (previously POST /api-keys accepted an arbitrary user_id from
anyone, with zero proof of ownership — closed as part of this change).
"""
from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request

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
from src.infrastructure.rate_limit.in_memory_rate_limiter import InMemoryRateLimiter
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


@lru_cache
def get_email_rate_limiter() -> InMemoryRateLimiter:
    # Max 3 requests per email per 15 minutes — protects a specific
    # inbox from being bombed with reset emails.
    return InMemoryRateLimiter(max_requests=3, window_seconds=15 * 60)


@lru_cache
def get_ip_rate_limiter() -> InMemoryRateLimiter:
    # Looser: max 10 requests per IP per 15 minutes — protects against
    # one caller sweeping many different email addresses.
    #
    # Real limitation, confirmed live: behind a reverse proxy (App
    # Runner here), request.client.host is the PROXY's address, not
    # the real caller's — every request looks like the same IP unless
    # X-Forwarded-For is read instead. See forgot_password below.
    return InMemoryRateLimiter(max_requests=10, window_seconds=15 * 60)


@router.post("/forgot-password", response_model=GenericMessageSchema)
def forgot_password(
    body: ForgotPasswordRequestSchema,
    request: Request,
    use_case: RequestPasswordResetUseCase = Depends(get_request_reset_use_case),
    email_limiter: InMemoryRateLimiter = Depends(get_email_rate_limiter),
    ip_limiter: InMemoryRateLimiter = Depends(get_ip_rate_limiter),
) -> GenericMessageSchema:
    """Always returns the same message regardless of whether the email
    is registered — see manage_password_reset.py for the full
    reasoning. Never raises for a nonexistent email or a failed send;
    both are handled silently by the use case itself.

    Rate limiting follows the same principle: a limited request still
    gets the identical generic message, not a 429 — a distinguishable
    response would itself leak information (that something about this
    request tripped a threshold), the exact thing this endpoint is
    built to avoid everywhere else."""
    email_key = body.email.strip().lower()
    # X-Forwarded-For first — request.client.host is App Runner's own
    # internal proxy address behind a reverse proxy, not the real
    # caller's IP; every request would otherwise look identical.
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        ip_key = forwarded_for.split(",")[0].strip()
    elif request.client:
        ip_key = request.client.host
    else:
        ip_key = "unknown"

    if email_limiter.allow(email_key) and ip_limiter.allow(ip_key):
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
