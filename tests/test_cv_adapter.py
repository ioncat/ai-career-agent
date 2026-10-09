"""
tests/test_cv_adapter.py — Contract tests for CVAdapter (HTTP version).

Mocks httpx.AsyncClient — no real pdf-service needed.
Verifies: happy path, error paths (4xx/5xx, connect error, timeout).
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from adapters.cv_adapter import CVAdapter, CVAdapterError


# ── Helpers ───────────────────────────────────────────────────────────────────

def _adapter(url: str = "http://localhost:8002") -> CVAdapter:
    return CVAdapter(pdf_service_url=url)


VALID_PDF = b"%PDF-1.4\n" + b"0" * 400   # the adapter rejects a header-only response


def _mock_response(status_code: int = 200, content: bytes = VALID_PDF) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    resp.text = content.decode("utf-8", errors="replace")
    return resp


def _mock_client(response: MagicMock) -> MagicMock:
    """Build a mock httpx.AsyncClient context manager returning the given response."""
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ── generate_pdf — happy path ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_pdf_returns_pdf_path(tmp_path):
    md = tmp_path / "CV.md"
    md.write_text("# CV\nContent.", encoding="utf-8")
    pdf = tmp_path / "CV.pdf"

    ctx = _mock_client(_mock_response(200, VALID_PDF))
    with patch("adapters.cv_adapter.httpx.AsyncClient", return_value=ctx):
        result = await _adapter().generate_pdf(md, pdf)

    assert result == pdf
    assert pdf.exists()
    assert pdf.read_bytes() == VALID_PDF


@pytest.mark.asyncio
async def test_generate_pdf_default_output_path(tmp_path):
    """When pdf_path=None, output defaults to md_path.with_suffix('.pdf')."""
    md = tmp_path / "Name_CV.md"
    md.write_text("# CV", encoding="utf-8")

    ctx = _mock_client(_mock_response(200, VALID_PDF))
    with patch("adapters.cv_adapter.httpx.AsyncClient", return_value=ctx):
        result = await _adapter().generate_pdf(md)

    assert result == tmp_path / "Name_CV.pdf"
    assert result.exists()


@pytest.mark.asyncio
async def test_generate_pdf_posts_markdown_text(tmp_path):
    """CVAdapter reads md_path and sends its text as markdown field."""
    md = tmp_path / "CV.md"
    md.write_text("# My CV\nGreat experience.", encoding="utf-8")

    mock_resp = _mock_response(200, VALID_PDF)
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_client)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("adapters.cv_adapter.httpx.AsyncClient", return_value=ctx):
        await _adapter().generate_pdf(md)

    mock_client.post.assert_awaited_once()
    call_kwargs = mock_client.post.call_args.kwargs
    assert call_kwargs["json"]["markdown"] == "# My CV\nGreat experience."


# ── generate_pdf — error paths ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_pdf_md_not_found_raises(tmp_path):
    adapter = _adapter()
    md = tmp_path / "nonexistent.md"
    with pytest.raises(FileNotFoundError, match="Markdown file not found"):
        await adapter.generate_pdf(md)


@pytest.mark.asyncio
async def test_generate_pdf_service_500_raises(tmp_path):
    md = tmp_path / "CV.md"
    md.write_text("# CV", encoding="utf-8")

    ctx = _mock_client(_mock_response(500, b"Internal Server Error"))
    with patch("adapters.cv_adapter.httpx.AsyncClient", return_value=ctx):
        with pytest.raises(CVAdapterError, match="500"):
            await _adapter().generate_pdf(md)


@pytest.mark.asyncio
async def test_generate_pdf_service_422_raises(tmp_path):
    md = tmp_path / "CV.md"
    md.write_text("   ", encoding="utf-8")  # whitespace-only

    ctx = _mock_client(_mock_response(422, b'{"detail":"markdown field is empty"}'))
    with patch("adapters.cv_adapter.httpx.AsyncClient", return_value=ctx):
        with pytest.raises(CVAdapterError, match="422"):
            await _adapter().generate_pdf(md)


@pytest.mark.asyncio
async def test_generate_pdf_connect_error_raises(tmp_path):
    md = tmp_path / "CV.md"
    md.write_text("# CV", encoding="utf-8")

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_client)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("adapters.cv_adapter.httpx.AsyncClient", return_value=ctx):
        with pytest.raises(CVAdapterError, match="unreachable"):
            await _adapter().generate_pdf(md)


@pytest.mark.asyncio
async def test_generate_pdf_timeout_raises(tmp_path):
    md = tmp_path / "CV.md"
    md.write_text("# CV", encoding="utf-8")

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_client)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("adapters.cv_adapter.httpx.AsyncClient", return_value=ctx):
        with pytest.raises(CVAdapterError, match="timed out"):
            await _adapter().generate_pdf(md)


@pytest.mark.asyncio
async def test_generate_pdf_generic_http_error_raises(tmp_path):
    md = tmp_path / "CV.md"
    md.write_text("# CV", encoding="utf-8")

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.HTTPError("generic"))
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_client)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("adapters.cv_adapter.httpx.AsyncClient", return_value=ctx):
        with pytest.raises(CVAdapterError, match="HTTP error"):
            await _adapter().generate_pdf(md)


# ── CVAdapter construction ────────────────────────────────────────────────────

def test_trailing_slash_stripped():
    adapter = CVAdapter(pdf_service_url="http://localhost:8002/")
    assert adapter._url == "http://localhost:8002"


def test_default_url_contains_port():
    adapter = CVAdapter()
    assert "8002" in adapter._url


# ── generate_pdf - the response must be a real PDF, not just HTTP 200 ─────────

@pytest.mark.asyncio
@pytest.mark.parametrize("content", [
    b"",                                     # empty body
    b"%PDF-1.4",                             # header only: an empty render
    b"<html>Internal Server Error</html>" + b"0" * 400,   # an error page served as 200
])
async def test_generate_pdf_rejects_a_200_that_is_not_a_real_pdf(tmp_path, content):
    md = tmp_path / "CV.md"
    md.write_text("# CV", encoding="utf-8")

    ctx = _mock_client(_mock_response(200, content))
    with patch("adapters.cv_adapter.httpx.AsyncClient", return_value=ctx):
        with pytest.raises(CVAdapterError):
            await _adapter().generate_pdf(md)

    assert not md.with_suffix(".pdf").exists()      # nothing broken is left on disk


@pytest.mark.asyncio
async def test_generate_pdf_write_failure_is_an_adapter_error(tmp_path):
    md = tmp_path / "CV.md"
    md.write_text("# CV", encoding="utf-8")

    ctx = _mock_client(_mock_response(200, VALID_PDF))
    with patch("adapters.cv_adapter.httpx.AsyncClient", return_value=ctx):
        with pytest.raises(CVAdapterError):
            await _adapter().generate_pdf(md, tmp_path / "missing_dir" / "CV.pdf")
