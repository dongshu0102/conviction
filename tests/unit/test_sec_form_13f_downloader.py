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
    """A persistent 404 (bad period_label, wrong URL) must eventually
    raise -- but see the next test for confirming it does NOT retry
    first, since a 404 won't be fixed by retrying."""
    response = httpx.Response(404, content=b"not found")
    transport = _FakeTransport(response)
    client = httpx.Client(transport=transport, headers={"User-Agent": "test"})
    downloader = SecForm13FDownloader(Settings(), client=client)

    with pytest.raises(Form13FDownloadError):
        downloader.download_quarter("2026q2")


def test_download_quarter_does_not_retry_a_4xx_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression guard: a 4xx means the request itself is wrong (bad
    period_label, genuinely nonexistent URL) -- retrying wastes real
    time waiting on something that will never succeed. Confirmed via
    a request counter, not just that it eventually raises."""
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    call_count = {"n": 0}

    class _CountingTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            return httpx.Response(404, content=b"not found")

    client = httpx.Client(transport=_CountingTransport(), headers={"User-Agent": "test"})
    downloader = SecForm13FDownloader(Settings(), client=client)

    with pytest.raises(Form13FDownloadError):
        downloader.download_quarter("2026q2")

    assert call_count["n"] == 1


def test_download_quarter_retries_a_transient_connection_error_and_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test for a real, confirmed production failure: the
    ~95MB download was cut off partway through mid-stream (peer closed
    connection without sending the complete body) even though a
    parallel curl download of the exact same URL succeeded cleanly
    every time. Must retry a transient transport-level failure and
    succeed on a later attempt, not fail the whole ingestion on one
    bad mid-download interruption."""
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    zip_bytes = _build_zip_bytes({"SUBMISSION.tsv": "a", "COVERPAGE.tsv": "b", "INFOTABLE.tsv": "c"})
    call_count = {"n": 0}

    class _FlakyThenSucceedsTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise httpx.ReadError("peer closed connection without sending complete message body")
            return httpx.Response(200, content=zip_bytes)

    client = httpx.Client(transport=_FlakyThenSucceedsTransport(), headers={"User-Agent": "test"})
    downloader = SecForm13FDownloader(Settings(), client=client)

    result = downloader.download_quarter("2026q2")

    assert call_count["n"] == 3
    assert result["SUBMISSION.tsv"] == "a"


def test_download_quarter_raises_a_clear_error_after_exhausting_all_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    call_count = {"n": 0}

    class _AlwaysFlakyTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            raise httpx.ReadError("read operation timed out")

    client = httpx.Client(transport=_AlwaysFlakyTransport(), headers={"User-Agent": "test"})
    downloader = SecForm13FDownloader(Settings(), client=client)

    with pytest.raises(Form13FDownloadError, match="after 4 attempts"):
        downloader.download_quarter("2026q2")

    assert call_count["n"] == 4


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
