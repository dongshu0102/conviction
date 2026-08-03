"""Use cases: request and complete a password reset.

Same account-enumeration defense as SignUpUseCase/LogInUseCase in
manage_auth.py — RequestPasswordResetUseCase does the identical thing
whether or not the email is registered, so a caller (or an attacker)
can never tell which. A password reset completing successfully also
revokes every previously-issued API key for that account — the real
point of resetting a password at all is "something may have been
compromised," so any key issued before that moment shouldn't be
trusted afterward either.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from src.application.interfaces.email_sender import EmailSendError, EmailSender
from src.application.use_cases.manage_api_keys import CreateApiKeyUseCase
from src.application.use_cases.manage_auth import MIN_PASSWORD_LENGTH, WeakPasswordError
from src.domain.entities.password_reset_token import PasswordResetToken
from src.domain.repositories.api_key_repository import ApiKeyRepository
from src.domain.repositories.password_reset_token_repository import (
    PasswordResetTokenRepository,
)
from src.domain.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

TOKEN_VALIDITY = timedelta(hours=1)


def _hash_token(plaintext: str) -> str:
    # Plain SHA-256, not bcrypt — same reasoning as API keys: a
    # machine-generated, high-entropy token isn't brute-forceable by
    # guessing, so a fast hash is the right tool here.
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def _default_hash_password(password: str) -> str:
    import bcrypt

    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


class InvalidOrExpiredTokenError(Exception):
    def __init__(self) -> None:
        super().__init__("This password reset link is invalid or has expired.")


class RequestPasswordResetUseCase:
    def __init__(
        self,
        user_repo: UserRepository,
        token_repo: PasswordResetTokenRepository,
        email_sender: EmailSender,
        frontend_base_url: str,
    ) -> None:
        self._user_repo = user_repo
        self._token_repo = token_repo
        self._email_sender = email_sender
        self._frontend_base_url = frontend_base_url

    def execute(self, email: str) -> None:
        """Always completes the same way regardless of whether the
        email is registered — never raises, never returns a signal the
        caller could use to distinguish the two cases."""
        user_id = email.strip().lower()
        user = self._user_repo.get_by_user_id(user_id)
        if user is None:
            return  # deliberately silent — same account as a real one, from the caller's view

        plaintext_token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        self._token_repo.save(
            PasswordResetToken(
                token_hash=_hash_token(plaintext_token), user_id=user_id,
                expires_at=now + TOKEN_VALIDITY, created_at=now, used=False,
            )
        )

        reset_link = f"{self._frontend_base_url}/reset-password?token={plaintext_token}"
        body = (
            f"A password reset was requested for your FinInsight account.\n\n"
            f"Reset your password: {reset_link}\n\n"
            f"This link expires in 1 hour. If you didn't request this, "
            f"you can safely ignore this email."
        )
        try:
            self._email_sender.send(user_id, "Reset your FinInsight password", body)
        except EmailSendError:
            # Logged, never raised further — the caller must never
            # learn whether this succeeded, same reasoning as never
            # revealing whether the account existed in the first place.
            logger.exception("Password reset email failed to send for %s", user_id)


class ResetPasswordUseCase:
    def __init__(
        self,
        user_repo: UserRepository,
        token_repo: PasswordResetTokenRepository,
        api_key_repo: ApiKeyRepository,
        hash_password=_default_hash_password,
    ) -> None:
        self._user_repo = user_repo
        self._token_repo = token_repo
        self._api_key_repo = api_key_repo
        self._hash_password = hash_password

    def execute(self, plaintext_token: str, new_password: str) -> str:
        """Returns the user_id whose password was reset."""
        if len(new_password) < MIN_PASSWORD_LENGTH:
            raise WeakPasswordError()

        token_hash = _hash_token(plaintext_token)
        token = self._token_repo.get_by_hash(token_hash)
        if token is None or token.used or token.expires_at < datetime.now(timezone.utc):
            raise InvalidOrExpiredTokenError()

        user = self._user_repo.get_by_user_id(token.user_id)
        if user is None:
            raise InvalidOrExpiredTokenError()  # same generic error, never leak more

        self._user_repo.save(replace(user, password_hash=self._hash_password(new_password)))
        self._token_repo.mark_used(token_hash)
        revoked = self._api_key_repo.deactivate_all_for_user(token.user_id)
        logger.info("Password reset for %s, revoked %d prior API key(s)", token.user_id, revoked)

        return token.user_id
