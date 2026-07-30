from __future__ import annotations

from src.application.use_cases.manage_api_keys import (
    CreateApiKeyUseCase,
    ValidateApiKeyUseCase,
)
from src.domain.entities.api_key import ApiKey


class FakeApiKeyRepository:
    def __init__(self) -> None:
        self._keys: dict[str, ApiKey] = {}  # key_hash -> ApiKey

    def save(self, api_key) -> None:
        self._keys[api_key.key_hash] = api_key

    def get_by_hash(self, key_hash: str):
        return self._keys.get(key_hash)

    def list_for_user(self, user_id: str) -> list:
        return [k for k in self._keys.values() if k.user_id == user_id]


def test_generated_key_validates_successfully() -> None:
    repo = FakeApiKeyRepository()
    create_use_case = CreateApiKeyUseCase(repo)
    validate_use_case = ValidateApiKeyUseCase(repo)

    _, plaintext_key = create_use_case.execute("alice", "My CLI key")

    assert validate_use_case.execute(plaintext_key) == "alice"


def test_wrong_key_does_not_validate() -> None:
    repo = FakeApiKeyRepository()
    create_use_case = CreateApiKeyUseCase(repo)
    validate_use_case = ValidateApiKeyUseCase(repo)

    create_use_case.execute("alice", "My CLI key")

    assert validate_use_case.execute("fi_live_totally_made_up_key") is None


def test_empty_key_does_not_validate() -> None:
    repo = FakeApiKeyRepository()
    validate_use_case = ValidateApiKeyUseCase(repo)

    assert validate_use_case.execute("") is None


def test_plaintext_key_is_never_equal_to_stored_hash() -> None:
    """The whole point of hashing — confirms we're not accidentally
    storing the plaintext somewhere and calling it a hash."""
    repo = FakeApiKeyRepository()
    create_use_case = CreateApiKeyUseCase(repo)

    stored_record, plaintext_key = create_use_case.execute("alice", "test")

    assert stored_record.key_hash != plaintext_key
    assert plaintext_key not in stored_record.key_hash


def test_two_generated_keys_are_never_the_same() -> None:
    repo = FakeApiKeyRepository()
    create_use_case = CreateApiKeyUseCase(repo)

    _, key1 = create_use_case.execute("alice", "key one")
    _, key2 = create_use_case.execute("alice", "key two")

    assert key1 != key2


def test_different_users_keys_are_isolated() -> None:
    repo = FakeApiKeyRepository()
    create_use_case = CreateApiKeyUseCase(repo)
    validate_use_case = ValidateApiKeyUseCase(repo)

    _, alice_key = create_use_case.execute("alice", "key")
    _, bob_key = create_use_case.execute("bob", "key")

    assert validate_use_case.execute(alice_key) == "alice"
    assert validate_use_case.execute(bob_key) == "bob"
