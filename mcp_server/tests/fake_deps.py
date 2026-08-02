"""Fake stubs for `httpx` and `mcp`, registered into sys.modules before
server.py is imported — the ONLY way to test the real, unmodified
server.py in an environment with neither dependency actually
installed (no network to pip install either, in this sandbox).

This is the same "Fake" pattern used throughout the main backend
(FakeCompanyRepository, etc.), applied at the import level instead of
the object level: a minimal stand-in with just enough surface for the
real code to run against, so tests exercise the ACTUAL shipped code,
not a reimplementation of what it's assumed to do.

IMPORTANT: call install() before importing mcp_server.server anywhere,
including transitively.
"""
from __future__ import annotations

import sys
import types


class FakeResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            err = FakeHTTPStatusError(f"{self.status_code} error", response=self)
            raise err


class FakeHTTPError(Exception):
    pass


class FakeHTTPStatusError(FakeHTTPError):
    def __init__(self, message: str, response: FakeResponse) -> None:
        super().__init__(message)
        self.response = response


class RecordedCall:
    def __init__(self, method: str, path: str, params, json) -> None:
        self.method = method
        self.path = path
        self.params = params
        self.json = json


class FakeAsyncClient:
    """Records every call made through it (module-level list, shared
    across instances — mirrors how a real single-run test session only
    cares about "what got called", not per-client isolation) and
    returns a canned response configured via set_response()."""

    calls: list[RecordedCall] = []
    _response = FakeResponse(200, '{"ok": true}')

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def request(self, method: str, path: str, params=None, json=None):
        FakeAsyncClient.calls.append(RecordedCall(method, path, params, json))
        return FakeAsyncClient._response


def install() -> None:
    """Register fake httpx and mcp modules in sys.modules. Idempotent —
    safe to call multiple times (e.g. once per test module)."""
    FakeAsyncClient.calls = []
    FakeAsyncClient._response = FakeResponse(200, '{"ok": true}')

    fake_httpx = types.ModuleType("httpx")
    fake_httpx.AsyncClient = FakeAsyncClient
    fake_httpx.HTTPError = FakeHTTPError
    fake_httpx.HTTPStatusError = FakeHTTPStatusError
    sys.modules["httpx"] = fake_httpx

    fake_mcp_server_module = types.ModuleType("mcp.server")

    class FakeMCPServer:
        def __init__(self, name: str = "", description: str = "") -> None:
            self.name = name
            self.description = description

        def tool(self):
            # The real decorator presumably registers the function for
            # MCP's schema/dispatch machinery — for testing purposes,
            # the only thing that matters is that the decorated function
            # remains directly, normally callable, which returning it
            # unchanged guarantees.
            def decorator(fn):
                return fn
            return decorator

        def run(self) -> None:
            pass

    fake_mcp_server_module.MCPServer = FakeMCPServer

    fake_mcp_pkg = types.ModuleType("mcp")
    fake_mcp_pkg.server = fake_mcp_server_module
    sys.modules["mcp"] = fake_mcp_pkg
    sys.modules["mcp.server"] = fake_mcp_server_module


def set_response(status_code: int, text: str = "") -> None:
    FakeAsyncClient._response = FakeResponse(status_code, text)


def get_calls() -> list[RecordedCall]:
    return FakeAsyncClient.calls
