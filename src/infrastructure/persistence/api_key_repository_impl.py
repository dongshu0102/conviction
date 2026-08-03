from __future__ import annotations

from sqlalchemy import select

from src.domain.entities.api_key import ApiKey
from src.domain.repositories.api_key_repository import ApiKeyRepository
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import ApiKeyModel


def _to_domain(row: ApiKeyModel) -> ApiKey:
    return ApiKey(
        key_hash=row.key_hash, key_prefix=row.key_prefix, user_id=row.user_id,
        name=row.name, created_at=row.created_at, is_active=row.is_active,
    )


class SqlAlchemyApiKeyRepository(ApiKeyRepository):
    def save(self, api_key: ApiKey) -> None:
        with session_scope() as session:
            session.add(
                ApiKeyModel(
                    key_hash=api_key.key_hash, key_prefix=api_key.key_prefix,
                    user_id=api_key.user_id, name=api_key.name,
                    is_active=api_key.is_active, created_at=api_key.created_at,
                )
            )

    def get_by_hash(self, key_hash: str) -> ApiKey | None:
        with session_scope() as session:
            row = session.get(ApiKeyModel, key_hash)
            return _to_domain(row) if row else None

    def list_for_user(self, user_id: str) -> list[ApiKey]:
        with session_scope() as session:
            rows = session.execute(
                select(ApiKeyModel).where(ApiKeyModel.user_id == user_id)
            ).scalars().all()
            return [_to_domain(row) for row in rows]

    def deactivate_all_for_user(self, user_id: str) -> int:
        with session_scope() as session:
            rows = session.execute(
                select(ApiKeyModel).where(
                    ApiKeyModel.user_id == user_id, ApiKeyModel.is_active.is_(True)
                )
            ).scalars().all()
            for row in rows:
                row.is_active = False
            return len(rows)
