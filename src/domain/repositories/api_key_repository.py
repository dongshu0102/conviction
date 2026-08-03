from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.api_key import ApiKey


class ApiKeyRepository(ABC):
    @abstractmethod
    def save(self, api_key: ApiKey) -> None: ...

    @abstractmethod
    def get_by_hash(self, key_hash: str) -> ApiKey | None: ...

    @abstractmethod
    def list_for_user(self, user_id: str) -> list[ApiKey]: ...

    @abstractmethod
    def deactivate_all_for_user(self, user_id: str) -> int:
        """Revokes every active key for this user. Returns the count
        actually revoked. A real UPDATE, not save() re-called — save()
        is insert-only (a fresh INSERT with no existence check), so
        re-calling it on an existing key_hash would raise a duplicate-
        primary-key error rather than updating it."""
        ...
