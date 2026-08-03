"""Domain entity for a password-reset token.

Deliberately mirrors the API key convention: the token itself is a
high-entropy random string, hashed with plain SHA-256 (not bcrypt) —
same reasoning as API keys, not passwords: this is machine-generated,
never brute-forceable by guessing, so a fast hash is the right tool,
not a slow salted one.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class PasswordResetToken:
    token_hash: str
    user_id: str
    expires_at: datetime
    created_at: datetime
    used: bool = False
