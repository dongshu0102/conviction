"""Tests for SignUpUseCase / LogInUseCase — the actual logic (weak
passwords, duplicate accounts, wrong credentials, that a real key is
minted) verified for real with a fake hasher, since real bcrypt isn't
installed in this environment. The fake hasher is deliberately trivial
(reverses the string) — good enough to prove the CALLING logic is
correct; the real cryptographic strength of bcrypt itself is a
property of the bcrypt library, not something this test suite needs to
re-verify.
"""
from __future__ import annotations

from src.application.use_cases.manage_api_keys import CreateApiKeyUseCase
from src.application.use_cases.manage_auth import (
    InvalidCredentialsError,
    LogInUseCase,
    SignUpUseCase,
    UserAlreadyExistsError,
    WeakPasswordError,
)
from tests.unit.fakes import FakeApiKeyRepository, FakeUserRepository


def _fake_hash(password: str) -> str:
    return f"HASHED:{password[::-1]}"


def _fake_verify(password: str, password_hash: str) -> bool:
    return password_hash == _fake_hash(password)


def _build():
    user_repo = FakeUserRepository()
    api_key_repo = FakeApiKeyRepository()
    create_api_key = CreateApiKeyUseCase(api_key_repo)
    signup = SignUpUseCase(user_repo, create_api_key, hash_password=_fake_hash)
    login = LogInUseCase(user_repo, create_api_key, verify_password=_fake_verify)
    return user_repo, api_key_repo, signup, login


def test_signup_creates_user_and_returns_real_api_key() -> None:
    user_repo, api_key_repo, signup, _ = _build()

    record, plaintext_key = signup.execute("Alice@Example.com", "correcthorse")
    user_id = record.user_id

    assert user_id == "alice@example.com"  # normalized
    assert plaintext_key.startswith("fi_live_")  # a genuine, usable API key
    stored_user = user_repo.get_by_user_id("alice@example.com")
    assert stored_user is not None
    assert stored_user.password_hash == _fake_hash("correcthorse")  # never stored in plaintext
    assert len(api_key_repo.list_for_user("alice@example.com")) == 1


def test_signup_rejects_weak_password() -> None:
    _, _, signup, _ = _build()
    try:
        signup.execute("alice@example.com", "short")
        raise AssertionError("expected WeakPasswordError")
    except WeakPasswordError:
        pass


def test_signup_rejects_duplicate_email() -> None:
    _, _, signup, _ = _build()
    signup.execute("alice@example.com", "correcthorse")
    try:
        signup.execute("ALICE@example.com", "differentpassword")  # same email, different case
        raise AssertionError("expected UserAlreadyExistsError")
    except UserAlreadyExistsError:
        pass


def test_login_succeeds_with_correct_password_mints_fresh_key() -> None:
    user_repo, api_key_repo, signup, login = _build()
    signup.execute("alice@example.com", "correcthorse")

    record, plaintext_key = login.execute("alice@example.com", "correcthorse")
    user_id = record.user_id

    assert user_id == "alice@example.com"
    assert plaintext_key.startswith("fi_live_")
    # signup key + login key = 2 total, login didn't reuse the signup one
    assert len(api_key_repo.list_for_user("alice@example.com")) == 2


def test_login_fails_with_wrong_password() -> None:
    _, _, signup, login = _build()
    signup.execute("alice@example.com", "correcthorse")
    try:
        login.execute("alice@example.com", "wrongpassword")
        raise AssertionError("expected InvalidCredentialsError")
    except InvalidCredentialsError:
        pass


def test_login_fails_for_nonexistent_user_same_error_as_wrong_password() -> None:
    """Deliberately the SAME error/message as a wrong password — never
    reveal whether an email is registered."""
    _, _, _, login = _build()
    try:
        login.execute("nobody@example.com", "anypassword")
        raise AssertionError("expected InvalidCredentialsError")
    except InvalidCredentialsError as exc:
        assert "email or password" in str(exc).lower()
