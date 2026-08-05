"""Use case: actually verify critical external dependencies work, not
just that this process is alive.

Deliberately separate from the App Runner liveness check at GET
/health. That endpoint drives App Runner's own decision about whether
to keep routing traffic to this container — making it depend on a
third party's uptime would mean a temporary Anthropic hiccup could
cause App Runner to start cycling an otherwise-healthy container. This
use case exists for real, external monitoring instead: something an
operator (or an uptime-checking tool) polls on its own schedule,
independent of container lifecycle decisions.

This is exactly the gap that let the Anthropic key go invalid and sit
silently broken — chat, daily briefs, theme suggestion, and research
were all down, and nothing surfaced it until a person happened to
manually test a brand-new feature.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, ContextManager

from sqlalchemy import text


@dataclass(frozen=True, slots=True)
class DependencyCheckResult:
    name: str
    healthy: bool
    detail: str


@dataclass(frozen=True, slots=True)
class DependencyHealthReport:
    all_healthy: bool
    checks: list[DependencyCheckResult]


class CheckDependencyHealthUseCase:
    def __init__(
        self,
        anthropic_client: Any,
        anthropic_model: str,
        db_session_factory: Callable[[], ContextManager[Any]],
    ) -> None:
        # anthropic_client is injected, same pattern as
        # AnthropicChatAgent — real dependency injection, not
        # constructed inline, so this is genuinely testable with a
        # fake rather than needing to mock a third-party SDK.
        self._anthropic_client = anthropic_client
        self._anthropic_model = anthropic_model
        self._db_session_factory = db_session_factory

    def execute(self) -> DependencyHealthReport:
        checks = [self._check_anthropic(), self._check_database()]
        return DependencyHealthReport(
            all_healthy=all(c.healthy for c in checks), checks=checks
        )

    def _check_anthropic(self) -> DependencyCheckResult:
        try:
            # max_tokens=1 on a single-word prompt — the cheapest real
            # call that still genuinely exercises authentication, not
            # a free "check auth" endpoint (Anthropic doesn't have
            # one), so this is deliberately not polled constantly.
            self._anthropic_client.messages.create(
                model=self._anthropic_model,
                max_tokens=1,
                messages=[{"role": "user", "content": "hi"}],
            )
            return DependencyCheckResult("anthropic", True, "OK")
        except Exception as exc:
            # Checked by class name, not `except anthropic.AuthenticationError`
            # — this use case deliberately never imports the anthropic
            # package directly, matching every other use case in this
            # codebase (Anthropic-specific code stays isolated to the
            # infrastructure layer, e.g. anthropic_chat_agent.py).
            if type(exc).__name__ == "AuthenticationError":
                return DependencyCheckResult("anthropic", False, "API key is invalid or revoked")
            return DependencyCheckResult("anthropic", False, f"{type(exc).__name__}: {exc}")

    def _check_database(self) -> DependencyCheckResult:
        try:
            with self._db_session_factory() as session:
                session.execute(text("SELECT 1"))
            return DependencyCheckResult("database", True, "OK")
        except Exception as exc:
            return DependencyCheckResult("database", False, f"{type(exc).__name__}: {exc}")
