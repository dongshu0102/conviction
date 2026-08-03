"""Contract for sending an email. The application layer depends on
this abstraction only — never on boto3/SES directly, same principle as
every other external integration in this codebase (data providers,
LLM providers, options data). Swapping SES for a different provider
later means writing one new adapter, touching nothing upstream of it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class EmailSendError(Exception):
    pass


class EmailSender(ABC):
    @abstractmethod
    def send(self, to: str, subject: str, body_text: str) -> None:
        """Raises EmailSendError on failure — never silently drops a
        send. Callers decide what "email failed" should mean for their
        flow (e.g. password reset still returns a generic success
        message regardless, to avoid account enumeration — but the
        failure is still logged, not swallowed silently)."""
