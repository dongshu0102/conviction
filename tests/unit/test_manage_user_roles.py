"""Tests for ListUsersUseCase / ChangeUserRoleUseCase — real logic
verified with the fake, no mocks needed for the actual behavior being
tested (the last-admin safety check especially)."""
from __future__ import annotations

from datetime import datetime, timezone

from src.application.use_cases.manage_user_roles import (
    ChangeUserRoleUseCase,
    LastAdminError,
    ListUsersUseCase,
    UserNotFoundError,
)
from src.domain.entities.user import Role, User
from tests.unit.fakes import FakeUserRepository


def _seed(user_repo, email: str, role: Role = Role.USER) -> str:
    user_id = email.strip().lower()
    user_repo.save(User(user_id=user_id, password_hash="H", created_at=datetime.now(timezone.utc), role=role))
    return user_id


def test_list_users_returns_every_account() -> None:
    user_repo = FakeUserRepository()
    _seed(user_repo, "alice@example.com")
    _seed(user_repo, "bob@example.com", role=Role.ADMIN)

    users = ListUsersUseCase(user_repo).execute()

    assert {u.user_id for u in users} == {"alice@example.com", "bob@example.com"}
    bob = next(u for u in users if u.user_id == "bob@example.com")
    assert bob.role == Role.ADMIN


def test_change_role_promotes_a_user_to_admin() -> None:
    user_repo = FakeUserRepository()
    alice = _seed(user_repo, "alice@example.com")

    updated = ChangeUserRoleUseCase(user_repo).execute(alice, Role.ADMIN)

    assert updated.role == Role.ADMIN
    assert user_repo.get_by_user_id(alice).role == Role.ADMIN


def test_change_role_raises_for_unknown_user() -> None:
    user_repo = FakeUserRepository()
    try:
        ChangeUserRoleUseCase(user_repo).execute("nobody@example.com", Role.ADMIN)
        raise AssertionError("expected UserNotFoundError")
    except UserNotFoundError:
        pass


def test_demoting_an_admin_when_another_admin_exists_succeeds() -> None:
    user_repo = FakeUserRepository()
    alice = _seed(user_repo, "alice@example.com", role=Role.ADMIN)
    _seed(user_repo, "bob@example.com", role=Role.ADMIN)  # a second admin

    updated = ChangeUserRoleUseCase(user_repo).execute(alice, Role.USER)

    assert updated.role == Role.USER


def test_demoting_the_last_admin_is_refused() -> None:
    """The actual safety property: this must never be allowed to
    silently lock every admin endpoint out."""
    user_repo = FakeUserRepository()
    alice = _seed(user_repo, "alice@example.com", role=Role.ADMIN)
    _seed(user_repo, "bob@example.com", role=Role.USER)  # not an admin

    try:
        ChangeUserRoleUseCase(user_repo).execute(alice, Role.USER)
        raise AssertionError("expected LastAdminError")
    except LastAdminError:
        pass

    # Confirm the refusal actually held — role unchanged.
    assert user_repo.get_by_user_id(alice).role == Role.ADMIN


def test_promoting_a_user_to_admin_never_triggers_the_last_admin_check() -> None:
    """The check only applies when REMOVING admin status, never when
    granting it — promoting should always be allowed regardless of how
    many admins currently exist."""
    user_repo = FakeUserRepository()
    bob = _seed(user_repo, "bob@example.com", role=Role.USER)

    updated = ChangeUserRoleUseCase(user_repo).execute(bob, Role.ADMIN)

    assert updated.role == Role.ADMIN
