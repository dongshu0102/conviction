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


@pytest.mark.asyncio
async def test_delete_theme_uses_delete_and_the_bare_theme_path():
    """Same easy mistake risk as remove_ticker_from_theme — this one
    could accidentally hit the /tickers/{ticker} path instead of the
    bare theme path, deleting one membership instead of the theme."""
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.delete_theme("AI Infrastructure")
    mock_req.assert_called_once_with("DELETE", "/universe/themes/AI Infrastructure")


@pytest.mark.asyncio
async def test_add_growth_candidate_uses_post_and_the_ticker_path():
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.add_growth_candidate("NVDA")
    mock_req.assert_called_once_with("POST", "/growth-candidates/NVDA")


@pytest.mark.asyncio
async def test_remove_growth_candidate_uses_delete_not_post():
    """Same easy copy-paste risk as remove_ticker_from_theme — the
    add and remove tools share the same URL shape, differing only in
    HTTP method."""
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.remove_growth_candidate("NVDA")
    mock_req.assert_called_once_with("DELETE", "/growth-candidates/NVDA")


@pytest.mark.asyncio
async def test_list_growth_candidates_simple_get():
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.list_growth_candidates()
    mock_req.assert_called_once_with("GET", "/growth-candidates")


@pytest.mark.asyncio
async def test_check_growth_candidates_uses_the_dedicated_check_path():
    """The real risk here: /growth-candidates/check could collide with
    /growth-candidates/{ticker} if the REST route ordering were ever
    wrong — this test only covers the MCP tool hits the right path,
    the route-ordering fix itself lives in the REST router."""
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.check_growth_candidates()
    mock_req.assert_called_once_with("POST", "/growth-candidates/check")


@pytest.mark.asyncio
async def test_compute_dcf_omits_growth_rate_param_when_not_supplied():
    """growth_rate=None must not become the literal string 'None' in
    the query params — omitted entirely so the backend's own default
    (historical revenue CAGR) applies."""
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.compute_dcf("NVDA")
    mock_req.assert_called_once_with(
        "GET", "/companies/NVDA/dcf",
        params={"discount_rate": 0.10, "terminal_growth_rate": 0.025, "years": 5},
    )


@pytest.mark.asyncio
async def test_compute_dcf_includes_growth_rate_param_when_explicitly_supplied():
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.compute_dcf("NVDA", growth_rate=0.15)
    mock_req.assert_called_once_with(
        "GET", "/companies/NVDA/dcf",
        params={"discount_rate": 0.10, "terminal_growth_rate": 0.025, "years": 5, "growth_rate": 0.15},
    )


@pytest.mark.asyncio
async def test_compute_reverse_dcf_uses_get_and_the_correct_path():
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.compute_reverse_dcf("NVDA")
    mock_req.assert_called_once_with(
        "GET", "/companies/NVDA/reverse-dcf",
        params={"discount_rate": 0.10, "terminal_growth_rate": 0.025, "years": 5},
    )


@pytest.mark.asyncio
async def test_compute_irr_requires_ticker_in_the_path_matching_the_real_rest_constraint():
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.compute_irr("NVDA", exit_price=150.0, years=3)
    mock_req.assert_called_once_with(
        "GET", "/companies/NVDA/irr",
        params={"exit_price": 150.0, "years": 3, "annual_dividend_per_share": 0.0},
    )


@pytest.mark.asyncio
async def test_compute_comps_defaults_to_pe_metric():
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.compute_comps("NVDA")
    mock_req.assert_called_once_with("GET", "/companies/NVDA/comps", params={"metric": "pe"})


@pytest.mark.asyncio
async def test_get_treasury_rates_uses_get_and_the_correct_path():
    """The real risk here, same as sp500-constituents in the REST
    router: this static path could be swallowed by /companies/{ticker}
    if it were ever registered after the dynamic route — this test
    only covers the MCP tool hits the right path, the actual
    route-ordering fix lives in the REST router itself."""
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.get_treasury_rates()
    mock_req.assert_called_once_with("GET", "/companies/treasury-rates")


# --- The 11 tools added to close the MCP gap (options, screening, --------
# recommendations, rebalancing, watchlist extras) — none of these had any
# test coverage until now, despite three of them sending a JSON body, the
# exact request shape that already caused one real production bug this
# session (construct_risk_parity_portfolio, tested above).

@pytest.mark.asyncio
async def test_add_option_holding_sends_json_body_with_uppercased_ticker():
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.add_option_holding(
            "port-1", "nvda", 500.0, "2026-12-18", "call", 2.0, 15.5
        )
    mock_req.assert_called_once_with(
        "POST", "/portfolios/port-1/options",
        json={
            "underlying_ticker": "NVDA", "strike": 500.0, "expiration": "2026-12-18",
            "option_type": "call", "contracts_held": 2.0, "cost_basis_per_contract": 15.5,
        },
    )


@pytest.mark.asyncio
async def test_remove_option_holding_sends_json_body_not_query_params():
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.remove_option_holding("port-1", "nvda", 500.0, "2026-12-18", "call")
    mock_req.assert_called_once_with(
        "DELETE", "/portfolios/port-1/options",
        json={
            "underlying_ticker": "NVDA", "strike": 500.0,
            "expiration": "2026-12-18", "option_type": "call",
        },
    )


@pytest.mark.asyncio
async def test_compute_portfolio_greeks_simple_get():
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.compute_portfolio_greeks("port-1")
    mock_req.assert_called_once_with("GET", "/portfolios/port-1/options/greeks")


@pytest.mark.asyncio
async def test_compute_option_portfolio_valuation_simple_get():
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.compute_option_portfolio_valuation("port-1")
    mock_req.assert_called_once_with("GET", "/portfolios/port-1/options/valuation")


@pytest.mark.asyncio
async def test_suggest_hedging_simple_get():
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.suggest_hedging("port-1")
    mock_req.assert_called_once_with("GET", "/portfolios/port-1/options/hedging-suggestion")


@pytest.mark.asyncio
async def test_screen_stocks_sends_json_body_with_tickers_and_theme_name():
    """The exact request shape (list[str] in a JSON body, not query
    params) that broke construct_risk_parity_portfolio in the REST
    layer earlier this session — proving it wasn't repeated here."""
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.screen_stocks(tickers=["aapl", "msft"], theme_name=None)
    mock_req.assert_called_once_with(
        "POST", "/companies/screen",
        json={"tickers": ["aapl", "msft"], "theme_name": None},
    )


@pytest.mark.asyncio
async def test_screen_stocks_defaults_to_none_for_both_when_omitted():
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.screen_stocks()
    mock_req.assert_called_once_with(
        "POST", "/companies/screen", json={"tickers": None, "theme_name": None}
    )


@pytest.mark.asyncio
async def test_recommend_stocks_query_param_default():
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.recommend_stocks("port-1")
    mock_req.assert_called_once_with(
        "GET", "/portfolios/port-1/recommendations", params={"max_recommendations": 5}
    )


@pytest.mark.asyncio
async def test_recommend_stocks_query_param_explicit():
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.recommend_stocks("port-1", max_recommendations=10)
    mock_req.assert_called_once_with(
        "GET", "/portfolios/port-1/recommendations", params={"max_recommendations": 10}
    )


@pytest.mark.asyncio
async def test_suggest_rebalancing_query_param_default():
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.suggest_rebalancing("port-1")
    mock_req.assert_called_once_with(
        "GET", "/portfolios/port-1/rebalance-suggestion", params={"target_max_weight": 0.30}
    )


@pytest.mark.asyncio
async def test_list_watchlists_simple_get():
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.list_watchlists()
    mock_req.assert_called_once_with("GET", "/watchlist/lists")


@pytest.mark.asyncio
async def test_update_watchlist_item_only_includes_explicitly_passed_fields():
    """The subtle correctness requirement: an omitted field must NOT
    appear in the body at all (so the backend's model_fields_set
    distinction between 'omitted' and 'explicitly null' works) — only
    list_name is always present."""
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.update_watchlist_item("aapl", notes="watching earnings")
    mock_req.assert_called_once_with(
        "PATCH", "/watchlist/AAPL",
        json={"list_name": "Default", "notes": "watching earnings"},
    )


@pytest.mark.asyncio
async def test_update_watchlist_item_all_fields_given():
    with patch("server._request", new=AsyncMock(return_value="{}")) as mock_req:
        await server.update_watchlist_item(
            "aapl", list_name="Growth", notes="hold", target_price=200.0, alert_threshold_pct=0.05
        )
    mock_req.assert_called_once_with(
        "PATCH", "/watchlist/AAPL",
        json={
            "list_name": "Growth", "notes": "hold",
            "target_price": 200.0, "alert_threshold_pct": 0.05,
        },
    )


@pytest.mark.asyncio
async def test_get_stock_news_uppercases_ticker_and_passes_limit():
    with patch("server._request", new=AsyncMock(return_value="[]")) as mock_req:
        await server.get_stock_news("aapl", limit=5)
    mock_req.assert_called_once_with("GET", "/companies/AAPL/news", params={"limit": 5})
