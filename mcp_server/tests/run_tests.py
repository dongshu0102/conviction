"""Standalone test runner for the MCP server — no pytest required,
same "plain function + assert" philosophy as the main backend's test
suite. Tests run against fake httpx/mcp stubs (see fake_deps.py), so
they're fast, offline, and deterministic regardless of whether the
real dependencies are installed.

Usage:
    cd mcp_server
    FININSIGHT_API_KEY=test_key python3 tests/run_tests.py

(Also fully compatible with plain `pytest tests/` if you have pytest
installed — every test is a normal sync function, no special plugin
needed, since each one handles its own asyncio.run() internally.)
"""
from __future__ import annotations

import importlib
import sys
import traceback

sys.path.insert(0, ".")


def main() -> int:
    module = importlib.import_module("tests.test_server")
    passed = failed = 0
    failures = []

    for name in sorted(dir(module)):
        if name.startswith("test_"):
            try:
                getattr(module, name)()
                passed += 1
            except Exception:
                failed += 1
                failures.append((name, traceback.format_exc()))

    print(f"\n{passed} passed, {failed} failed")
    for name, tb in failures:
        print(f"\n--- {name} ---\n{tb}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
