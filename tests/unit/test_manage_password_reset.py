"""Tests for RequestPasswordResetUseCase / ResetPasswordUseCase.

Real logic verified with fakes, same pattern as test_manage_auth.py —
a fake password hasher (bcrypt unavailable in this sandbox) and a fake
email sender (proving the account-enumeration defense holds even when
sending genuinely fails).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.application.use_cases.manage_api_keys import CreateApiKeyUseCase
from src.application.use_cases.manage_password_reset import (
    InvalidOrExpiredTokenError,
    RequestPasswordResetUseCase,
    ResetPasswordUseCase,
    TOKEN_VALIDITY,
    _hash_token,
)
from src.domain.entities.password_reset_token import PasswordResetToken
from src.domain.entities.user import User
from tests.unit.fakes import (
    FakeApiKeyRepository,
    FakeEmailSender,
    FakePasswordResetTokenRepository,
    FakeUserRepository,
)

FRONTEND_URL = "https://example.com"


def _fake_hash(password: str) -> str:
    return f"HASHED:{password[::-1]}"


def _seed_user(user_repo, email="alice@example.com", password_hash="OLDHASH") -> str:
    user_id = email.strip().lower()
    user_repo.save(User(user_id=user_id, password_hash=password_hash, created_at=datetime.now(timezone.utc)))
    return user_id


def _build_request_use_case(user_repo, token_repo, email_sender):
    return RequestPasswordResetUseCase(user_repo, token_repo, email_sender, FRONTEND_URL)


def _build_reset_use_case(user_repo, token_repo, api_key_repo):
    return ResetPasswordUseCase(user_repo, token_repo, api_key_repo, hash_password=_fake_hash)


# --- RequestPasswordResetUseCase ---------------------------------------------

def test_request_reset_for_existing_user_sends_email_with_working_link() -> None:
    user_repo = FakeUserRepository()
    token_repo = FakePasswordResetTokenRepository()
    email_sender = FakeEmailSender()
    user_id = _seed_user(user_repo)

    _build_request_use_case(user_repo, token_repo, email_sender).execute("Alice@Example.com")

    assert len(email_sender.sent) == 1
    to, subject, body = email_sender.sent[0]
    assert to == user_id
    assert "Reset your" in subject
    assert f"{FRONTEND_URL}/reset-password?token=" in body


def test_request_reset_for_nonexistent_user_sends_no_email_but_does_not_error() -> None:
    """The actual security property: silently does nothing, never
    raises, never signals anything different from the real-user case."""
    user_repo = FakeUserRepository()
    token_repo = FakePasswordResetTokenRepository()
    email_sender = FakeEmailSender()

    _build_request_use_case(user_repo, token_repo, email_sender).execute("nobody@example.com")

    assert email_sender.sent == []


def test_request_reset_email_failure_does_not_raise() -> None:
    """Even when the email genuinely fails to send, the use case must
    not raise — the caller can never distinguish 'account doesn't
    exist' from 'email failed to send' by catching an exception."""
    user_repo = FakeUserRepository()
    token_repo = FakePasswordResetTokenRepository()
    email_sender = FakeEmailSender(fail=True)
    _seed_user(user_repo)

    _build_request_use_case(user_repo, token_repo, email_sender).execute("alice@example.com")
    # No exception raised — that's the entire assertion.


def test_request_reset_creates_a_token_valid_for_one_hour() -> None:
    user_repo = FakeUserRepository()
    token_repo = FakePasswordResetTokenRepository()
    email_sender = FakeEmailSender()
    user_id = _seed_user(user_repo)

    before = datetime.now(timezone.utc)
    _build_request_use_case(user_repo, token_repo, email_sender).execute("alice@example.com")

    to, subject, body = email_sender.sent[0]
    plaintext_token = body.split("token=")[1].split("\n")[0].strip()
    token = token_repo.get_by_hash(_hash_token(plaintext_token))
    assert token is not None
    assert token.user_id == user_id
    assert token.used is False
    assert token.expires_at - before >= TOKEN_VALIDITY - timedelta(seconds=5)


# --- ResetPasswordUseCase ----------------------------------------------------

def test_reset_password_with_valid_token_updates_password_and_revokes_keys() -> None:
    user_repo = FakeUserRepository()
    token_repo = FakePasswordResetTokenRepository()
    api_key_repo = FakeApiKeyRepository()
    user_id = _seed_user(user_repo)
    CreateApiKeyUseCase(api_key_repo).execute(user_id, "old-key")
    plaintext_token = "real-token-abc123"
    token_repo.save(PasswordResetToken(
        token_hash=_hash_token(plaintext_token), user_id=user_id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        created_at=datetime.now(timezone.utc), used=False,
    ))

    result_user_id = _build_reset_use_case(user_repo, token_repo, api_key_repo).execute(
        plaintext_token, "newpassword123"
    )

    assert result_user_id == user_id
    updated_user = user_repo.get_by_user_id(user_id)
    assert updated_user.password_hash == _fake_hash("newpassword123")
    assert all(not k.is_active for k in api_key_repo.list_for_user(user_id))


def test_reset_password_marks_token_used_so_it_cannot_be_reused() -> None:
    user_repo = FakeUserRepository()
    token_repo = FakePasswordResetTokenRepository()
    api_key_repo = FakeApiKeyRepository()
    user_id = _seed_user(user_repo)
    plaintext_token = "one-time-token"
    token_repo.save(PasswordResetToken(
        token_hash=_hash_token(plaintext_token), user_id=user_id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        created_at=datetime.now(timezone.utc), used=False,
    ))
    use_case = _build_reset_use_case(user_repo, token_repo, api_key_repo)

    use_case.execute(plaintext_token, "newpassword123")

    try:
        use_case.execute(plaintext_token, "anotherpassword456")
        raise AssertionError("expected InvalidOrExpiredTokenError on reuse")
    except InvalidOrExpiredTokenError:
        pass


def test_reset_password_rejects_expired_token() -> None:
    user_repo = FakeUserRepository()
    token_repo = FakePasswordResetTokenRepository()
    api_key_repo = FakeApiKeyRepository()
    user_id = _seed_user(user_repo)
    plaintext_token = "expired-token"
    token_repo.save(PasswordResetToken(
        token_hash=_hash_token(plaintext_token), user_id=user_id,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),  # already expired
        created_at=datetime.now(timezone.utc) - timedelta(hours=2), used=False,
    ))

    try:
        _build_reset_use_case(user_repo, token_repo, api_key_repo).execute(
            plaintext_token, "newpassword123"
        )
        raise AssertionError("expected InvalidOrExpiredTokenError")
    except InvalidOrExpiredTokenError:
        pass


def test_reset_password_rejects_unknown_token() -> None:
    user_repo = FakeUserRepository()
    token_repo = FakePasswordResetTokenRepository()
    api_key_repo = FakeApiKeyRepository()

    try:
        _build_reset_use_case(user_repo, token_repo, api_key_repo).execute(
            "never-issued-token", "newpassword123"
        )
        raise AssertionError("expected InvalidOrExpiredTokenError")
    except InvalidOrExpiredTokenError:
        pass


def test_reset_password_rejects_weak_new_password() -> None:
    from src.application.use_cases.manage_auth import WeakPasswordError

    user_repo = FakeUserRepository()
    token_repo = FakePasswordResetTokenRepository()
    api_key_repo = FakeApiKeyRepository()
    user_id = _seed_user(user_repo)
    plaintext_token = "some-token"
    token_repo.save(PasswordResetToken(
        token_hash=_hash_token(plaintext_token), user_id=user_id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        created_at=datetime.now(timezone.utc), used=False,
    ))

    try:
        _build_reset_use_case(user_repo, token_repo, api_key_repo).execute(plaintext_token, "short")
        raise AssertionError("expected WeakPasswordError")
    except WeakPasswordError:
        pass
