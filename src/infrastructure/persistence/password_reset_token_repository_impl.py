"""Postgres-backed PasswordResetTokenRepository implementation."""
from __future__ import annotations

from datetime import timezone

from src.domain.entities.password_reset_token import PasswordResetToken
from src.domain.repositories.password_reset_token_repository import (
    PasswordResetTokenRepository,
)
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import PasswordResetTokenModel


def _to_domain(row: PasswordResetTokenModel) -> PasswordResetToken:
    # Same Postgres-strips-tzinfo gap as factor_score_repository_impl.py
    # — a plain `timestamp` column returns a NAIVE datetime on read,
    # even though it was saved with datetime.now(timezone.utc).
    # Confirmed in production: comparing this against a fresh
    # datetime.now(timezone.utc) in ResetPasswordUseCase raised
    # "can't compare offset-naive and offset-aware datetimes" — this
    # bug class was already found and documented once this session
    # (see the README's operational-lessons section) and should have
    # been applied here from the start.
    expires_at = row.expires_at if row.expires_at.tzinfo is not None else row.expires_at.replace(tzinfo=timezone.utc)
    created_at = row.created_at if row.created_at.tzinfo is not None else row.created_at.replace(tzinfo=timezone.utc)
    return PasswordResetToken(
        token_hash=row.token_hash, user_id=row.user_id, expires_at=expires_at,
        created_at=created_at, used=row.used,
    )


class SqlAlchemyPasswordResetTokenRepository(PasswordResetTokenRepository):
    def save(self, token: PasswordResetToken) -> None:
        with session_scope() as session:
            session.add(
                PasswordResetTokenModel(
                    token_hash=token.token_hash, user_id=token.user_id,
                    expires_at=token.expires_at, created_at=token.created_at, used=token.used,
                )
            )

    def get_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        with session_scope() as session:
            row = session.get(PasswordResetTokenModel, token_hash)
            return _to_domain(row) if row else None

    def mark_used(self, token_hash: str) -> None:
        with session_scope() as session:
            row = session.get(PasswordResetTokenModel, token_hash)
            if row is not None:
                row.used = True
