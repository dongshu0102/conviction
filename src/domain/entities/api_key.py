"""Domain entity for API key authentication.

Only key_hash is ever persisted — the plaintext key is generated once,
returned to the caller exactly one time, and never stored or logged
anywhere. This is standard API key hygiene: if the database is ever
compromised, no usable credentials leak from it.

key_prefix (first 8 chars of the plaintext) is stored purely so a user
can identify which key is which in a list ("which key starts with
fi_a1b2...") without the full secret ever being retrievable again.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ApiKey:
    key_hash: str
    key_prefix: str
    user_id: str
    name: str
    created_at: datetime
    is_active: bool = True
