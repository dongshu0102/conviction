"""Postgres-backed PasswordResetTokenRepository implementation."""
from __future__ import annotations

from src.domain.entities.password_reset_token import PasswordResetToken
from src.domain.repositories.password_reset_token_repository import (
    PasswordResetTokenRepository,
)
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import PasswordResetTokenModel


def _to_domain(row: PasswordResetTokenModel) -> PasswordResetToken:
    return PasswordResetToken(
        token_hash=row.token_hash, user_id=row.user_id, expires_at=row.expires_at,
        created_at=row.created_at, used=row.used,
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
