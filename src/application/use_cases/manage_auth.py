"""Use cases: real signup and login.

Both produce a genuine, standard API key as their result — deliberately
NOT a separate session/JWT mechanism. Every existing piece of this
system (every REST endpoint's auth dependency, the frontend's request
helper, the MCP server) already knows how to use an API key; inventing
a second, parallel credential type here would mean touching all of
that for no real benefit. Signing up or logging in is simply now the
ONLY way to get a key stamped with a real, password-verified identity
— the plaintext key you get back afterward is functionally identical
to any other API key in this system, right down to how it's stored and
sent.

This is also what closes the impersonation gap that existed before
this: the OLD POST /api-keys endpoint accepted user_id as a bare query
param from anyone, with zero proof they owned that identity. Signup now
requires a password no one else can guess, and login requires knowing
it — see ManageApiKeys' updated create endpoint for how creating
ADDITIONAL keys is now gated on already holding a valid one.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from src.application.use_cases.manage_api_keys import CreateApiKeyUseCase
from src.domain.entities.user import User
from src.domain.repositories.user_repository import UserRepository

MIN_PASSWORD_LENGTH = 8


def _default_hash_password(password: str) -> str:
    import bcrypt

    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _default_verify_password(password: str, password_hash: str) -> bool:
    import bcrypt

    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _normalize_email(email: str) -> str:
    return email.strip().lower()


class UserAlreadyExistsError(Exception):
    def __init__(self) -> None:
        super().__init__("An account with this email already exists — log in instead.")


class WeakPasswordError(Exception):
    def __init__(self) -> None:
        super().__init__(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")


class InvalidCredentialsError(Exception):
    def __init__(self) -> None:
        # Deliberately vague — never confirm whether the email exists
        # or the password was wrong specifically. Standard defense
        # against account enumeration.
        super().__init__("Invalid email or password.")


class SignUpUseCase:
    def __init__(
        self,
        user_repo: UserRepository,
        create_api_key: CreateApiKeyUseCase,
        hash_password: Callable[[str], str] = _default_hash_password,
    ) -> None:
        self._user_repo = user_repo
        self._create_api_key = create_api_key
        self._hash_password = hash_password

    def execute(self, email: str, password: str) -> tuple:
        """Returns (ApiKey record, plaintext_api_key) — same convention
        as CreateApiKeyUseCase itself, so the REST layer has everything
        needed for a full response without a second lookup."""
        user_id = _normalize_email(email)

        if len(password) < MIN_PASSWORD_LENGTH:
            raise WeakPasswordError()
        if self._user_repo.get_by_user_id(user_id) is not None:
            raise UserAlreadyExistsError()

        password_hash = self._hash_password(password)
        self._user_repo.save(
            User(user_id=user_id, password_hash=password_hash, created_at=datetime.now(timezone.utc))
        )

        return self._create_api_key.execute(user_id, "signup")


class LogInUseCase:
    def __init__(
        self,
        user_repo: UserRepository,
        create_api_key: CreateApiKeyUseCase,
        verify_password: Callable[[str, str], bool] = _default_verify_password,
    ) -> None:
        self._user_repo = user_repo
        self._create_api_key = create_api_key
        self._verify_password = verify_password

    def execute(self, email: str, password: str) -> tuple:
        """Returns (ApiKey record, plaintext_api_key) — a FRESH key is
        minted on every login, same convention as multiple named keys
        already coexisting per user (e.g. one for the web session, one
        for MCP)."""
        user_id = _normalize_email(email)
        user = self._user_repo.get_by_user_id(user_id)
        if user is None:
            raise InvalidCredentialsError()

        if not self._verify_password(password, user.password_hash):
            raise InvalidCredentialsError()

        return self._create_api_key.execute(user_id, "login")
