"""
tests/test_parser_adapter.py — Contract tests for ParserAdapter.

Mocks httpx.AsyncClient — no real jd-parser service needed.
Verifies: happy path, all error paths, health check, _extract_detail.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from adapters.parser_adapter import ParserAdapter, ParserError, _extract_detail
from contracts.parsed_document import ParsedDocument

_URL = "https://djinni.co/jobs/123-backend/"
_BASE = "http://jd-parser:8001"

_GOOD_BODY = {
    "title": "Backend Engineer",
    "markdown": "## Requirements\n- Python 3.12",
    "source_url": _URL,
}


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _adapter() -> ParserAdapter:
    return ParserAdapter(base_url=_BASE)


def _mock_client(status: int, body: object = None, *, text: str = "") -> tuple:
    """Return (MockClient class, mock response) for patching httpx.AsyncClient."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.text = text or (json.dumps(body) if body is not None else "")
    resp.json.return_value = body if body is not None else {}

    async_client = AsyncMock()
    async_client.post.return_value = resp
    async_client.get.return_value = resp

    MockClient = MagicMock()
    MockClient.return_value.__aenter__ = AsyncMock(return_value=async_client)
    MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
    return MockClient, resp


# ── fetch_markdown — happy path ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_markdown_returns_parsed_document():
    MockClient, _ = _mock_client(200, _GOOD_BODY)
    with patch("adapters.parser_adapter.httpx.AsyncClient", MockClient):
        doc = await _adapter().fetch_markdown(_URL)
    assert isinstance(doc, ParsedDocument)
    assert doc.title == "Backend Engineer"
    assert doc.source_url == _URL
    assert "Python" in doc.markdown


@pytest.mark.asyncio
async def test_fetch_markdown_posts_to_correct_endpoint():
    MockClient, _ = _mock_client(200, _GOOD_BODY)
    with patch("adapters.parser_adapter.httpx.AsyncClient", MockClient):
        await _adapter().fetch_markdown(_URL)
    call_args = MockClient.return_value.__aenter__.return_value.post.call_args
    assert call_args[0][0] == f"{_BASE}/parse"
    assert call_args[1]["json"] == {"url": _URL}


@pytest.mark.asyncio
async def test_fetch_markdown_strips_trailing_slash_from_base():
    adapter = ParserAdapter(base_url=f"{_BASE}/")
    MockClient, _ = _mock_client(200, _GOOD_BODY)
    with patch("adapters.parser_adapter.httpx.AsyncClient", MockClient):
        await adapter.fetch_markdown(_URL)
    call_args = MockClient.return_value.__aenter__.return_value.post.call_args
    assert call_args[0][0] == f"{_BASE}/parse"


# ── fetch_markdown — error paths ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_markdown_503_json_detail_raises_parser_error():
    body = {"detail": "parse_failed"}
    MockClient, _ = _mock_client(503, body)
    with patch("adapters.parser_adapter.httpx.AsyncClient", MockClient):
        with pytest.raises(ParserError) as exc_info:
            await _adapter().fetch_markdown(_URL)
    assert exc_info.value.status_code == 503
    assert exc_info.value.url == _URL
    assert "503" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_markdown_404_raises_parser_error():
    MockClient, _ = _mock_client(404, {"detail": "not found"})
    with patch("adapters.parser_adapter.httpx.AsyncClient", MockClient):
        with pytest.raises(ParserError) as exc_info:
            await _adapter().fetch_markdown(_URL)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_fetch_markdown_503_non_json_body_raises_parser_error():
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 503
    resp.text = "Service Unavailable"
    resp.json.side_effect = ValueError("not json")

    async_client = AsyncMock()
    async_client.post.return_value = resp
    MockClient = MagicMock()
    MockClient.return_value.__aenter__ = AsyncMock(return_value=async_client)
    MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("adapters.parser_adapter.httpx.AsyncClient", MockClient):
        with pytest.raises(ParserError) as exc_info:
            await _adapter().fetch_markdown(_URL)
    assert "Service Unavailable" in str(exc_info.value)
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_fetch_markdown_transport_error_raises_parser_error_no_status():
    async_client = AsyncMock()
    async_client.post.side_effect = httpx.ConnectError("connection refused")
    MockClient = MagicMock()
    MockClient.return_value.__aenter__ = AsyncMock(return_value=async_client)
    MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("adapters.parser_adapter.httpx.AsyncClient", MockClient):
        with pytest.raises(ParserError) as exc_info:
            await _adapter().fetch_markdown(_URL)
    assert exc_info.value.status_code is None
    assert exc_info.value.url == _URL


@pytest.mark.asyncio
async def test_fetch_markdown_timeout_error_raises_parser_error():
    async_client = AsyncMock()
    async_client.post.side_effect = httpx.TimeoutException("timed out")
    MockClient = MagicMock()
    MockClient.return_value.__aenter__ = AsyncMock(return_value=async_client)
    MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("adapters.parser_adapter.httpx.AsyncClient", MockClient):
        with pytest.raises(ParserError):
            await _adapter().fetch_markdown(_URL)


# ── fetch_company_website (2026-08-12) ───────────────────────────────────────

_COMPANY_URL = "https://djinni.co/jobs/company-gypsy-collective/"


@pytest.mark.asyncio
async def test_fetch_company_website_returns_url():
    MockClient, _ = _mock_client(200, {"website": "https://www.gypsy.co/"})
    with patch("adapters.parser_adapter.httpx.AsyncClient", MockClient):
        result = await _adapter().fetch_company_website(_COMPANY_URL)
    assert result == "https://www.gypsy.co/"


@pytest.mark.asyncio
async def test_fetch_company_website_none_is_not_an_error():
    """website=null (page fetched fine, just no field) must return None,
    not raise — a company without a listed site is a normal outcome."""
    MockClient, _ = _mock_client(200, {"website": None})
    with patch("adapters.parser_adapter.httpx.AsyncClient", MockClient):
        result = await _adapter().fetch_company_website(_COMPANY_URL)
    assert result is None


@pytest.mark.asyncio
async def test_fetch_company_website_posts_to_correct_endpoint():
    MockClient, _ = _mock_client(200, {"website": None})
    with patch("adapters.parser_adapter.httpx.AsyncClient", MockClient):
        await _adapter().fetch_company_website(_COMPANY_URL)
    call_args = MockClient.return_value.__aenter__.return_value.post.call_args
    assert call_args[0][0] == f"{_BASE}/company-website"
    assert call_args[1]["json"] == {"url": _COMPANY_URL}


@pytest.mark.asyncio
async def test_fetch_company_website_503_raises_parser_error():
    MockClient, _ = _mock_client(503, {"detail": "fetch_failed"})
    with patch("adapters.parser_adapter.httpx.AsyncClient", MockClient):
        with pytest.raises(ParserError) as exc_info:
            await _adapter().fetch_company_website(_COMPANY_URL)
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_fetch_company_website_transport_error_raises_parser_error():
    async_client = AsyncMock()
    async_client.post.side_effect = httpx.ConnectError("refused")
    MockClient = MagicMock()
    MockClient.return_value.__aenter__ = AsyncMock(return_value=async_client)
    MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("adapters.parser_adapter.httpx.AsyncClient", MockClient):
        with pytest.raises(ParserError):
            await _adapter().fetch_company_website(_COMPANY_URL)


# ── health ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_returns_true_on_200():
    MockClient, _ = _mock_client(200, {"status": "ok"})
    with patch("adapters.parser_adapter.httpx.AsyncClient", MockClient):
        assert await _adapter().health() is True


@pytest.mark.asyncio
async def test_health_returns_false_on_non_200():
    MockClient, _ = _mock_client(500)
    with patch("adapters.parser_adapter.httpx.AsyncClient", MockClient):
        assert await _adapter().health() is False


@pytest.mark.asyncio
async def test_health_returns_false_on_transport_error():
    async_client = AsyncMock()
    async_client.get.side_effect = httpx.ConnectError("refused")
    MockClient = MagicMock()
    MockClient.return_value.__aenter__ = AsyncMock(return_value=async_client)
    MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("adapters.parser_adapter.httpx.AsyncClient", MockClient):
        assert await _adapter().health() is False


# ── _extract_detail ───────────────────────────────────────────────────────────

def test_extract_detail_uses_detail_key():
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = {"detail": "parse_failed", "url": "http://x"}
    assert _extract_detail(resp) == "parse_failed"


def test_extract_detail_falls_back_to_error_key():
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = {"error": "fetch_failed"}
    assert _extract_detail(resp) == "fetch_failed"


def test_extract_detail_falls_back_to_str_of_dict():
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = {"other": "value"}
    result = _extract_detail(resp)
    assert "other" in result


def test_extract_detail_non_dict_json():
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = ["error1", "error2"]
    result = _extract_detail(resp)
    assert "error1" in result


def test_extract_detail_non_json_body():
    resp = MagicMock(spec=httpx.Response)
    resp.json.side_effect = ValueError("not json")
    resp.text = "Internal Server Error"
    assert _extract_detail(resp) == "Internal Server Error"


def test_extract_detail_truncates_long_text():
    resp = MagicMock(spec=httpx.Response)
    resp.json.side_effect = ValueError("not json")
    resp.text = "x" * 500
    result = _extract_detail(resp)
    assert len(result) <= 200
