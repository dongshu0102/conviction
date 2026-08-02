"""Postgres-backed UserRepository implementation."""
from __future__ import annotations

from src.domain.entities.user import User
from src.domain.repositories.user_repository import UserRepository
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import UserModel


def _to_domain(row: UserModel) -> User:
    return User(user_id=row.user_id, password_hash=row.password_hash, created_at=row.created_at)


class SqlAlchemyUserRepository(UserRepository):
    def save(self, user: User) -> None:
        with session_scope() as session:
            existing = session.get(UserModel, user.user_id)
            if existing is None:
                session.add(
                    UserModel(
                        user_id=user.user_id,
                        password_hash=user.password_hash,
                        created_at=user.created_at,
                    )
                )
            else:
                existing.password_hash = user.password_hash

    def get_by_user_id(self, user_id: str) -> User | None:
        with session_scope() as session:
            row = session.get(UserModel, user_id.strip().lower())
            return _to_domain(row) if row else None
