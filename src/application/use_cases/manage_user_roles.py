"""Use cases: admin listing all users, and changing a user's role.

Deliberately separate from manage_auth.py — these are cross-user admin
operations, a genuinely different concern from a user managing their
own account, and REST-layer authorization for these two use cases is
strictly get_admin_user_id, never the ordinary authenticated-user
dependency.
"""
from __future__ import annotations

from dataclasses import replace

from src.domain.entities.user import Role, User
from src.domain.repositories.user_repository import UserRepository


class UserNotFoundError(Exception):
    def __init__(self, user_id: str) -> None:
        super().__init__(f"No account found for '{user_id}'.")


class LastAdminError(Exception):
    def __init__(self) -> None:
        super().__init__(
            "Refusing to remove the last remaining admin — this would lock "
            "every admin-only endpoint out until a new admin is bootstrapped "
            "via the BOOTSTRAP_ADMIN_EMAIL setting and a redeploy. Promote "
            "someone else to admin first if you really want to demote this "
            "account."
        )


class ListUsersUseCase:
    def __init__(self, user_repo: UserRepository) -> None:
        self._user_repo = user_repo

    def execute(self) -> list[User]:
        return self._user_repo.list_all()


class ChangeUserRoleUseCase:
    def __init__(self, user_repo: UserRepository) -> None:
        self._user_repo = user_repo

    def execute(self, target_user_id: str, new_role: Role) -> User:
        target_user_id = target_user_id.strip().lower()
        user = self._user_repo.get_by_user_id(target_user_id)
        if user is None:
            raise UserNotFoundError(target_user_id)

        if user.role == Role.ADMIN and new_role != Role.ADMIN:
            admins = [u for u in self._user_repo.list_all() if u.role == Role.ADMIN]
            if len(admins) <= 1:
                raise LastAdminError()

        updated = replace(user, role=new_role)
        self._user_repo.save(updated)
        return updated
