"""Domain entity for a real, password-authenticated user account.

user_id here is deliberately the SAME string type used as the join key
across every other table in this system (watchlists, portfolios,
alerts, api_keys) — specifically, the normalized email address. This
is the key design choice that keeps this addition low-risk: nothing
downstream of authentication (chat, portfolios, watchlist, factor
scoring, everything) needs to change at all, since it already just
receives a user_id string from the auth layer and has never cared
where that string came from.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Role(str, Enum):
    """A real enum, not a bare boolean — extensible if a third role
    (e.g. a support/read-only role) is ever genuinely needed, without
    another migration to change the column's shape."""

    USER = "user"
    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class User:
    user_id: str  # normalized (lowercased, stripped) email
    password_hash: str
    created_at: datetime
    role: Role = Role.USER
