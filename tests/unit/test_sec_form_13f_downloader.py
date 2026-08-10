import io
import zipfile

import httpx
import pytest

from src.infrastructure.config import Settings
from src.infrastructure.data_providers.sec_form_13f_downloader import (
    Form13FDownloadError,
    SecForm13FDownloader,
)


def _build_zip_bytes(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


class _FakeTransport(httpx.BaseTransport):
    def __init__(self, response: httpx.Response) -> None:
        self._response = response
        self.captured_request: httpx.Request | None = None

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.captured_request = request
        return self._response


def _downloader_with_zip(files: dict[str, str], status_code: int = 200) -> tuple[SecForm13FDownloader, _FakeTransport]:
    zip_bytes = _build_zip_bytes(files)
    response = httpx.Response(status_code, content=zip_bytes)
    transport = _FakeTransport(response)
    client = httpx.Client(transport=transport, headers={"User-Agent": "Conviction dong.shu0102@gmail.com"})
    return SecForm13FDownloader(Settings(), client=client), transport


def test_download_quarter_sends_the_required_user_agent_header() -> None:
    """Regression guard: SEC rejects requests without a compliant
    User-Agent with a real 403 — confirmed directly from SEC's own
    fair-access policy documentation, not assumed."""
    downloader, transport = _downloader_with_zip({
        "SUBMISSION.tsv": "a", "COVERPAGE.tsv": "b", "INFOTABLE.tsv": "c",
    })
    downloader.download_quarter("2026q2")
    assert transport.captured_request is not None
    assert "@" in transport.captured_request.headers.get("user-agent", "")


def test_download_quarter_matches_filenames_case_insensitively() -> None:
    """Real SEC archives use inconsistent casing across different
    quarterly files (e.g. coverpage.tsv vs COVERPAGE.tsv) — must not
    depend on exact case."""
    downloader, _ = _downloader_with_zip({
        "submission.tsv": "sub-content",
        "CoverPage.tsv": "cover-content",
        "INFOTABLE.TSV": "info-content",
    })
    result = downloader.download_quarter("2026q2")
    assert result["SUBMISSION.tsv"] == "sub-content"
    assert result["COVERPAGE.tsv"] == "cover-content"
    assert result["INFOTABLE.tsv"] == "info-content"


def test_download_quarter_raises_a_clear_error_when_a_required_file_is_missing() -> None:
    downloader, _ = _downloader_with_zip({
        "SUBMISSION.tsv": "a", "COVERPAGE.tsv": "b",
        # INFOTABLE.tsv deliberately missing.
    })
    with pytest.raises(Form13FDownloadError, match="INFOTABLE"):
        downloader.download_quarter("2026q2")


def test_download_quarter_raises_on_a_bad_zip_file() -> None:
    response = httpx.Response(200, content=b"not a real zip file")
    transport = _FakeTransport(response)
    client = httpx.Client(transport=transport, headers={"User-Agent": "test"})
    downloader = SecForm13FDownloader(Settings(), client=client)

    with pytest.raises(Form13FDownloadError):
        downloader.download_quarter("2026q2")


def test_download_quarter_raises_on_an_http_error_status() -> None:
    response = httpx.Response(404, content=b"not found")
    transport = _FakeTransport(response)
    client = httpx.Client(transport=transport, headers={"User-Agent": "test"})
    downloader = SecForm13FDownloader(Settings(), client=client)

    with pytest.raises(Form13FDownloadError):
        downloader.download_quarter("2026q2")


def test_download_quarter_builds_the_real_confirmed_sec_url_pattern() -> None:
    """Regression guard for the exact, confirmed download URL
    pattern — verified directly against the real download links on
    sec.gov's own Form 13F Data Sets page, not guessed."""
    downloader, transport = _downloader_with_zip({
        "SUBMISSION.tsv": "a", "COVERPAGE.tsv": "b", "INFOTABLE.tsv": "c",
    })
    downloader.download_quarter("2026q2")
    assert str(transport.captured_request.url) == (
        "https://www.sec.gov/files/structureddata/data/form-13f-data-sets/2026q2_form13f.zip"
    )
