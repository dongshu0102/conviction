"""Downloads and unzips SEC's quarterly Form 13F bulk data set.

Deliberately just one HTTP call per quarter (the whole zip), not many
small per-filing requests — SEC's own guidance explicitly prefers this:
"Do not make 10,000 API calls when a single zip download exists."
SEC's 10-requests-per-second rate limit is a non-issue here for
exactly that reason.
"""
from __future__ import annotations

import io
import zipfile

import httpx

from src.infrastructure.config import Settings

# SEC's own confirmed URL pattern, verified directly against the real
# download links on sec.gov/data-research/sec-markets-data/form-13f-data-sets —
# not guessed. period_label examples: "2026q1", "01mar2026-31may2026".
_BASE_URL = "https://www.sec.gov/files/structureddata/data/form-13f-data-sets"

# The 3 files this pipeline actually needs, out of the 7-8 SEC ships
# per quarter (the others -- e.g. SUMMARYPAGE, RENDERING -- aren't
# needed for holdings data).
_REQUIRED_FILES = ("SUBMISSION.tsv", "COVERPAGE.tsv", "INFOTABLE.tsv")


class Form13FDownloadError(Exception):
    """A real, visible failure to download or unzip the SEC data
    set — never silently swallowed."""


class SecForm13FDownloader:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        # Injectable for tests — the real client always carries the
        # required User-Agent header on every request, never left to
        # an ad-hoc per-call header that's easy to forget.
        self._client = client or httpx.Client(
            headers={"User-Agent": settings.sec_edgar_user_agent}, timeout=120.0,
        )

    def download_quarter(self, period_label: str) -> dict[str, str]:
        """period_label matches SEC's own file-naming convention, e.g.
        "2026q1" or "01mar2026-31may2026" — see the real download
        links at sec.gov/data-research/sec-markets-data/form-13f-data-sets
        for the exact label to use for a given quarter. Returns each
        required file's raw text content, keyed by filename."""
        url = f"{_BASE_URL}/{period_label}_form13f.zip"
        try:
            response = self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise Form13FDownloadError(f"Failed to download {url}: {exc}") from exc

        try:
            archive = zipfile.ZipFile(io.BytesIO(response.content))
        except zipfile.BadZipFile as exc:
            raise Form13FDownloadError(f"{url} did not return a valid zip file") from exc

        names_in_archive = {n.upper(): n for n in archive.namelist()}
        result: dict[str, str] = {}
        for required in _REQUIRED_FILES:
            actual_name = names_in_archive.get(required.upper())
            if actual_name is None:
                raise Form13FDownloadError(
                    f"{url}: expected file {required} not found in archive "
                    f"(archive contains: {archive.namelist()})"
                )
            result[required] = archive.read(actual_name).decode("utf-8", errors="replace")

        return result
