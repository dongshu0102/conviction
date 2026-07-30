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
