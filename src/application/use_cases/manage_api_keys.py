"""API key creation and validation.

Uses stdlib hashlib (SHA-256) rather than a password-hashing library
like bcrypt/argon2 deliberately: API keys are high-entropy random
tokens (32 bytes from secrets.token_urlsafe), not human-chosen
passwords. The threat bcrypt/argon2 defend against — fast brute-force
of a low-entropy human password — doesn't apply here. A fast hash is
correct for this use case; using a slow hash would just add latency to
every authenticated request for no security benefit.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from src.domain.entities.api_key import ApiKey
from src.domain.repositories.api_key_repository import ApiKeyRepository

_KEY_PREFIX = "fi_live_"


def _hash_key(plaintext_key: str) -> str:
    return hashlib.sha256(plaintext_key.encode("utf-8")).hexdigest()


class CreateApiKeyUseCase:
    def __init__(self, api_key_repo: ApiKeyRepository) -> None:
        self._api_key_repo = api_key_repo

    def execute(self, user_id: str, name: str) -> tuple[ApiKey, str]:
        """Returns (stored_record, plaintext_key). The plaintext is
        returned exactly once here — the caller (API layer) must show it
        to the user immediately and never store it themselves either.
        """
        plaintext_key = _KEY_PREFIX + secrets.token_urlsafe(32)
        api_key = ApiKey(
            key_hash=_hash_key(plaintext_key),
            key_prefix=plaintext_key[: len(_KEY_PREFIX) + 8],
            user_id=user_id,
            name=name,
            created_at=datetime.now(timezone.utc),
        )
        self._api_key_repo.save(api_key)
        return api_key, plaintext_key


class ValidateApiKeyUseCase:
    def __init__(self, api_key_repo: ApiKeyRepository) -> None:
        self._api_key_repo = api_key_repo

    def execute(self, presented_key: str) -> str | None:
        """Returns the associated user_id if the key is valid and active,
        None otherwise. Callers must treat None as "reject the request" —
        this use case does not raise, since "invalid key" is an expected,
        routine outcome, not an exceptional one.
        """
        if not presented_key:
            return None
        record = self._api_key_repo.get_by_hash(_hash_key(presented_key))
        if record is None or not record.is_active:
            return None
        return record.user_id


class ListApiKeysUseCase:
    def __init__(self, api_key_repo: ApiKeyRepository) -> None:
        self._api_key_repo = api_key_repo

    def execute(self, user_id: str) -> list[ApiKey]:
        return self._api_key_repo.list_for_user(user_id)
