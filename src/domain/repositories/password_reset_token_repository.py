"""Repository interface for password reset tokens."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.password_reset_token import PasswordResetToken


class PasswordResetTokenRepository(ABC):
    @abstractmethod
    def save(self, token: PasswordResetToken) -> None: ...

    @abstractmethod
    def get_by_hash(self, token_hash: str) -> PasswordResetToken | None: ...

    @abstractmethod
    def mark_used(self, token_hash: str) -> None: ...
