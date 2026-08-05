"""Poll GET /health/dependencies and alert if anything's actually
broken — the real, working fix for the incident where the Anthropic
key went invalid and sat silently broken (chat, daily briefs, theme
suggestion, research all down) until a person happened to manually
test an unrelated new feature.

Deliberately a standalone script polled by cron, not a background
task inside the app process — same reasoning as run_monitoring.py:
a cron-invoked script has no race-condition risk with multiple
workers, and matches the established pattern for every other
periodic job in this codebase.

Sends an alert email via the SAME SES setup already used for password
reset — real constraint, honestly documented: SES is still in
sandbox mode, so this can only email the one verified address
(settings.ses_sender_email itself). That's a real limit worth
revisiting once SES gets production access, not something to work
around here.

Usage:
    python scripts/check_health.py

Exits 0 if healthy, 1 if not — so this also works as a plain cron
job with mail-on-failure (most cron daemons already email output on
non-zero exit), independent of whether the SES alert itself succeeds.

Suggested cron entry (every 10 minutes):
    */10 * * * * cd /path/to/conviction && .venv/bin/python scripts/check_health.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from src.infrastructure.config import get_settings
from src.infrastructure.email.ses_email_sender import SesEmailSender

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> int:
    settings = get_settings()
    # No dedicated "backend base URL" setting exists in config.py yet —
    # using the known production URL directly, matching how it's
    # referenced elsewhere in this codebase (e.g. mcp_server/server.py's
    # own API_BASE_URL default).
    url = "https://p8xpcshdn9.us-east-1.awsapprunner.com/health/dependencies"

    try:
        response = httpx.get(url, timeout=30)
        report = response.json()
    except Exception as exc:
        logger.error("Couldn't even reach the health endpoint: %s", exc)
        _alert(settings, "Conviction backend unreachable", f"Couldn't reach {url} at all: {exc}")
        return 1

    if report.get("all_healthy"):
        logger.info("All dependencies healthy.")
        return 0

    unhealthy = [c for c in report.get("checks", []) if not c.get("healthy")]
    detail_lines = "\n".join(f"- {c['name']}: {c['detail']}" for c in unhealthy)
    logger.error("Unhealthy dependencies detected:\n%s", detail_lines)
    _alert(
        settings,
        "Conviction: a real dependency is down",
        f"health/dependencies reports a problem:\n\n{detail_lines}\n\nFull report: {report}",
    )
    return 1


def _alert(settings, subject: str, body: str) -> None:
    try:
        SesEmailSender(settings).send(settings.ses_sender_email, subject, body)
    except Exception as exc:
        # The alert itself failing shouldn't crash the check — the
        # non-zero exit code below is still the fallback signal, and
        # most cron setups already email a job's stderr on failure.
        logger.error("Alert email failed to send: %s", exc)


if __name__ == "__main__":
    sys.exit(main())
