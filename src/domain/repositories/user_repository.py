"""Repository interface for User accounts."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.user import User


class UserRepository(ABC):
    @abstractmethod
    def save(self, user: User) -> None: ...

    @abstractmethod
    def get_by_user_id(self, user_id: str) -> User | None: ...

    @abstractmethod
    def list_all(self) -> list[User]: ...
