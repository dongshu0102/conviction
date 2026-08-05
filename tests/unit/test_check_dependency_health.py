"""Tests for CheckDependencyHealthUseCase — the real fix for the gap
that let the Anthropic key sit silently invalid: nothing checked
whether it actually worked, only whether the process was alive.
"""
from __future__ import annotations

from contextlib import contextmanager

from src.application.use_cases.check_dependency_health import (
    CheckDependencyHealthUseCase,
    DependencyHealthReport,
)


class FakeAnthropicMessages:
    def __init__(self, exception: Exception | None = None) -> None:
        self._exception = exception
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._exception:
            raise self._exception
        return {"id": "fake-msg"}


class FakeAnthropicClient:
    def __init__(self, exception: Exception | None = None) -> None:
        self.messages = FakeAnthropicMessages(exception)


class FakeSession:
    def __init__(self, exception: Exception | None = None) -> None:
        self._exception = exception
        self.executed = []

    def execute(self, statement):
        self.executed.append(statement)
        if self._exception:
            raise self._exception


def _db_factory_ok():
    @contextmanager
    def factory():
        yield FakeSession()
    return factory


def _db_factory_broken():
    @contextmanager
    def factory():
        yield FakeSession(exception=RuntimeError("connection refused"))
    return factory


def test_reports_all_healthy_when_everything_works() -> None:
    use_case = CheckDependencyHealthUseCase(
        anthropic_client=FakeAnthropicClient(),
        anthropic_model="claude-sonnet-5",
        db_session_factory=_db_factory_ok(),
    )

    report = use_case.execute()

    assert report.all_healthy is True
    assert {c.name for c in report.checks} == {"anthropic", "database"}
    assert all(c.healthy for c in report.checks)


def test_reports_unhealthy_when_anthropic_call_fails_for_any_reason() -> None:
    """The generic-exception path — doesn't require the real anthropic
    package to be importable, since RuntimeError isn't its
    AuthenticationError specifically. Confirms the use case fails
    closed (unhealthy) rather than silently swallowing an error."""
    use_case = CheckDependencyHealthUseCase(
        anthropic_client=FakeAnthropicClient(exception=RuntimeError("connection timed out")),
        anthropic_model="claude-sonnet-5",
        db_session_factory=_db_factory_ok(),
    )

    report = use_case.execute()

    assert report.all_healthy is False
    anthropic_check = next(c for c in report.checks if c.name == "anthropic")
    assert anthropic_check.healthy is False
    assert "connection timed out" in anthropic_check.detail


def test_reports_unhealthy_when_database_is_unreachable() -> None:
    use_case = CheckDependencyHealthUseCase(
        anthropic_client=FakeAnthropicClient(),
        anthropic_model="claude-sonnet-5",
        db_session_factory=_db_factory_broken(),
    )

    report = use_case.execute()

    assert report.all_healthy is False
    db_check = next(c for c in report.checks if c.name == "database")
    assert db_check.healthy is False
    assert "connection refused" in db_check.detail


def test_one_unhealthy_dependency_does_not_mask_the_other_being_checked() -> None:
    """Both checks should always run and be reported, even if the
    first one fails — a broken Anthropic key shouldn't prevent the
    database check from also running."""
    use_case = CheckDependencyHealthUseCase(
        anthropic_client=FakeAnthropicClient(exception=RuntimeError("bad key")),
        anthropic_model="claude-sonnet-5",
        db_session_factory=_db_factory_ok(),
    )

    report = use_case.execute()

    assert len(report.checks) == 2
    db_check = next(c for c in report.checks if c.name == "database")
    assert db_check.healthy is True


class AuthenticationError(Exception):
    """Deliberately named to match anthropic.AuthenticationError's class
    name exactly — the use case checks by name, not by importing the
    real anthropic package (see check_dependency_health.py's own
    comment on why). This fake lets the test exercise that exact path
    without needing the real package installed. The name itself is
    load-bearing here, not cosmetic — type(exc).__name__ is what the
    production code actually checks."""


def test_authentication_error_gets_the_specific_readable_message() -> None:
    use_case = CheckDependencyHealthUseCase(
        anthropic_client=FakeAnthropicClient(exception=AuthenticationError("API key is invalid.")),
        anthropic_model="claude-sonnet-5",
        db_session_factory=_db_factory_ok(),
    )

    report = use_case.execute()

    anthropic_check = next(c for c in report.checks if c.name == "anthropic")
    assert anthropic_check.healthy is False
    assert anthropic_check.detail == "API key is invalid or revoked"
