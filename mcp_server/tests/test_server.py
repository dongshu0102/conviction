"""Tests for the MCP server's proxy logic.

Cannot be run in the environment that wrote them — no PyPI access to
install httpx/mcp/pytest-asyncio here. Written carefully against known-
correct pytest-asyncio + unittest.mock conventions and needs to be
verified by actually running it, same as every other frontend/MCP
change this session that needed a real environment this sandbox
doesn't have.

Strategy: mock at the httpx.AsyncClient level for _request() itself
(proving its error-handling contract), and mock _request() directly
when testing individual tools (proving each one builds the right
method/path/params/json — exactly the class of bug that broke
construct-risk-parity in the REST layer earlier this session: a tool
sending query params where the API expects a JSON body, or vice versa).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import server


# --- _request() itself: the shared error-handling contract -------------------

@pytest.mark.asyncio
async def test_request_returns_response_text_on_success():
    mock_response = MagicMock()
    mock_response.text = '{"ok": true}'
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("server.httpx.AsyncClient", return_value=mock_client):
        result = await server._request("GET", "/watchlist")

    assert result == '{"ok": true}'


@pytest.mark.asyncio
async def test_request_formats_http_status_error_not_raises():
    """An HTTP error must become a text result the model can react to
    — never an unhandled exception that crashes the MCP server
    process."""
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = '{"detail": "not found"}'

    def _raise(*a, **kw):
        raise httpx.HTTPStatusError("404", request=MagicMock(), response=mock_response)

    mock_response.raise_for_status = MagicMock(side_effect=_raise)

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("server.httpx.AsyncClient", return_value=mock_client):
        result = await server._request("GET", "/companies/NOTREAL")

    assert "Error 404" in result
    assert "not found" in result


@pytest.mark.asyncio
async def test_request_formats_connection_error_not_raises():
    import httpx

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("server.httpx.AsyncClient", return_value=mock_client):
        result = await server._request("GET", "/watchlist")

    assert "Request failed" in result


# --- Individual tools: correct method/path/params/json ------------------------
# Representative coverage across the shapes that actually broke something
# in this codebase this session, not an exhaustive per-tool listing.

@pytest.mark.asyncio
async def test_get_watchlist_simple_get():
    with patch("server._request", new=AsyncMock(return_value="[]")) as mock_req:
        await server.get_watchlist()
    mock_req.assert_called_once_with("GET", "/watchlist")


@pytest.mark.asyncio
async def test_add_to_watchlist_path_param_and_optional_query_param():
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.add_to_watchlist("aapl", notes="watching earnings")
    mock_req.assert_called_once_with(
        "POST", "/watchlist/aapl", params={"notes": "watching earnings"}
    )


@pytest.mark.asyncio
async def test_ingest_company_query_params():
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.ingest_company("AAPL", years=3)
    mock_req.assert_called_once_with("POST", "/companies/AAPL/ingest", params={"years": 3})


@pytest.mark.asyncio
async def test_construct_risk_parity_portfolio_sends_json_body_not_query_params():
    """The exact regression this codebase already hit once in the REST
    layer: FastAPI expects a JSON body for a list[str] param, not
    repeated query params. This proves the MCP tool sends it the right
    way from day one, rather than repeating that mistake here."""
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.construct_risk_parity_portfolio(["nvda", "amd"], 10000.0)
    mock_req.assert_called_once_with(
        "POST",
        "/portfolios/construct-risk-parity",
        json={"tickers": ["NVDA", "AMD"], "total_investment": 10000.0},
    )


@pytest.mark.asyncio
async def test_suggest_theme_omits_params_when_no_hint_given():
    """Empty-string default must NOT become a literal empty query
    param — omitted entirely, matching the REST endpoint's own
    optional-param convention."""
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.suggest_theme()
    mock_req.assert_called_once_with("POST", "/universe/suggest-theme", params=None)


@pytest.mark.asyncio
async def test_suggest_theme_includes_hint_when_given():
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.suggest_theme(user_hint="reshoring")
    mock_req.assert_called_once_with(
        "POST", "/universe/suggest-theme", params={"user_hint": "reshoring"}
    )


@pytest.mark.asyncio
async def test_ingest_etf_separate_path_from_ingest_company():
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.ingest_etf("spy")
    mock_req.assert_called_once_with("POST", "/companies/spy/ingest-etf")


@pytest.mark.asyncio
async def test_delete_portfolio_delete_method():
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.delete_portfolio("abc-123")
    mock_req.assert_called_once_with("DELETE", "/portfolios/abc-123")


@pytest.mark.asyncio
async def test_remove_ticker_from_theme_uses_delete_not_post():
    """The one easy mistake to make copy-pasting the add/remove pair —
    same URL shape, different HTTP method."""
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.remove_ticker_from_theme("AI Infrastructure", "NVDA")
    mock_req.assert_called_once_with(
        "DELETE", "/universe/themes/AI Infrastructure/tickers/NVDA"
    )
