"""
tests/test_cv_fetch_jd.py — tests for tools/cv_fetch_jd.py.

Mocks: ParserAdapter, database functions, filesystem (tmp_path).
No real jd-parser service or DB needed.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adapters.parser_adapter import ParserError
from contracts.parsed_document import ParsedDocument
from tools.cv_fetch_jd import _detect_site, _url_slug, cv_fetch_jd


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_ctx(tmp_path: Path, parser_adapter=None, user_id: int = 1) -> MagicMock:
    """Build a mock RunContext[AgentDeps]."""
    if parser_adapter is None:
        parser_adapter = AsyncMock()
    ctx = MagicMock()
    ctx.deps.parser_adapter = parser_adapter
    ctx.deps.vacancies_path = tmp_path / "vacancies"
    ctx.deps.user_id = user_id
    return ctx


def _make_doc(title="Backend Dev", markdown="## Job\nGreat role.") -> ParsedDocument:
    return ParsedDocument(
        title=title,
        markdown=markdown,
        source_url="https://djinni.co/jobs/123-backend/",
    )


# ── _detect_site ──────────────────────────────────────────────────────────────

def test_detect_site_djinni():
    assert _detect_site("https://djinni.co/jobs/123/") == "djinni"


def test_detect_site_dou():
    assert _detect_site("https://jobs.dou.ua/vacancies/123/") == "dou"


def test_detect_site_linkedin():
    assert _detect_site("https://www.linkedin.com/jobs/view/123/") == "linkedin"


def test_detect_site_other():
    assert _detect_site("https://example.com/jobs/123/") == "other"


# ── _url_slug ─────────────────────────────────────────────────────────────────

def test_url_slug_djinni():
    slug = _url_slug("https://djinni.co/jobs/123-backend-python/")
    assert slug == "123-backend-python"


def test_url_slug_strips_trailing_slash():
    slug = _url_slug("https://djinni.co/jobs/123-test/")
    assert slug == "123-test"


def test_url_slug_sanitizes_chars():
    slug = _url_slug("https://example.com/jobs/My Job (2024)/")
    # spaces/parens → hyphens, consecutive hyphens collapsed, trailing stripped
    assert slug == "my-job-2024"


def test_url_slug_max_length():
    long_url = "https://example.com/jobs/" + "a" * 100
    slug = _url_slug(long_url)
    assert len(slug) <= 60


def test_url_slug_empty_path():
    slug = _url_slug("https://example.com")
    assert slug == "vacancy"


# ── cv_fetch_jd — happy path ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_jd_saves_file(tmp_path):
    doc = _make_doc()
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    ctx = _make_ctx(tmp_path, parser)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)
        mock_db.insert_vacancy = AsyncMock(return_value=42)
        mock_db.update_vacancy_fields = AsyncMock()

        result = await cv_fetch_jd(ctx, "https://djinni.co/jobs/123-backend/")

    assert "✅" in result
    assert "Backend Dev" in result
    assert "42" in result

    # File actually written
    saved = list(ctx.deps.vacancies_path.rglob("JD.md"))
    assert len(saved) == 1
    content = saved[0].read_text()
    assert "Backend Dev" in content
    assert "Great role." in content


@pytest.mark.asyncio
async def test_fetch_jd_correct_folder_structure(tmp_path):
    doc = _make_doc()
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    ctx = _make_ctx(tmp_path, parser)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)
        mock_db.insert_vacancy = AsyncMock(return_value=1)
        mock_db.update_vacancy_fields = AsyncMock()

        await cv_fetch_jd(ctx, "https://djinni.co/jobs/123-backend/")

    saved = list(ctx.deps.vacancies_path.rglob("JD.md"))
    path_parts = saved[0].parts
    # path: vacancies/inbox/{user_id}/{id} — {title}/JD.md
    assert "inbox" in path_parts
    assert "1" in path_parts        # user_id segment
    assert any("Backend Dev" in p for p in path_parts)  # title in folder name


@pytest.mark.asyncio
async def test_fetch_jd_calls_db_insert(tmp_path):
    doc = _make_doc(title="Python Dev")
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    ctx = _make_ctx(tmp_path, parser)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)
        mock_db.insert_vacancy = AsyncMock(return_value=5)
        mock_db.update_vacancy_fields = AsyncMock()

        await cv_fetch_jd(ctx, "https://djinni.co/jobs/456-python/")

    mock_db.insert_vacancy.assert_awaited_once()
    call_kwargs = mock_db.insert_vacancy.call_args.kwargs
    assert call_kwargs["url"] == "https://djinni.co/jobs/456-python/"
    assert call_kwargs["title"] == "Python Dev"
    assert call_kwargs["site"] == "djinni"
    assert call_kwargs["user_id"] == 1


# ── cv_fetch_jd — duplicate URL ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_jd_duplicate_returns_existing(tmp_path):
    ctx = _make_ctx(tmp_path)
    existing_row = MagicMock()
    existing_row.__getitem__ = lambda self, key: {
        "id": 7,
        "title": "Existing Job",
        "markdown_path": "/vacancies/djinni/2026-05/old/JD.md",
        "status": "analyzed",
    }[key]

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=existing_row)

        result = await cv_fetch_jd(ctx, "https://djinni.co/jobs/123/")

    assert "ℹ️" in result
    assert "уже в базе" in result
    ctx.deps.parser_adapter.fetch_markdown.assert_not_called()


# ── cv_fetch_jd — parser error ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_jd_parser_error_returns_message(tmp_path):
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(
        side_effect=ParserError("fetch failed", url="https://djinni.co/jobs/999/", status_code=503)
    )
    ctx = _make_ctx(tmp_path, parser)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)

        result = await cv_fetch_jd(ctx, "https://djinni.co/jobs/999/")

    assert "⚠️" in result
    assert "fetch failed" in result


# ── cv_fetch_jd — empty markdown ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_jd_empty_markdown_returns_warning(tmp_path):
    doc = ParsedDocument(title="Job", markdown="   ", source_url="https://djinni.co/jobs/1/")
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    ctx = _make_ctx(tmp_path, parser)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)

        result = await cv_fetch_jd(ctx, "https://djinni.co/jobs/1/")

    assert "⚠️" in result
    assert "извлечь текст" in result


# ── cv_fetch_jd — user-scoped filesystem path ─────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_jd_path_scoped_to_user_id(tmp_path):
    """Vacancy folder must be under vacancies/{user_id}/..."""
    doc = _make_doc()
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    ctx = _make_ctx(tmp_path, parser, user_id=7)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)
        mock_db.insert_vacancy = AsyncMock(return_value=10)
        mock_db.update_vacancy_fields = AsyncMock()

        await cv_fetch_jd(ctx, "https://djinni.co/jobs/777-senior/")

    saved = list(ctx.deps.vacancies_path.rglob("JD.md"))
    assert len(saved) == 1
    # path: inbox/{user_id}/{slug}/JD.md — first part is "inbox", second is user_id
    relative = saved[0].relative_to(ctx.deps.vacancies_path)
    assert relative.parts[0] == "inbox"
    assert relative.parts[1] == "7"


@pytest.mark.asyncio
async def test_fetch_jd_passes_user_id_to_db(tmp_path):
    """insert_vacancy must receive user_id from AgentDeps."""
    doc = _make_doc()
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    ctx = _make_ctx(tmp_path, parser, user_id=42)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)
        mock_db.insert_vacancy = AsyncMock(return_value=99)
        mock_db.update_vacancy_fields = AsyncMock()

        await cv_fetch_jd(ctx, "https://djinni.co/jobs/999-test/")

    call_kwargs = mock_db.insert_vacancy.call_args.kwargs
    assert call_kwargs["user_id"] == 42


# ── cv_fetch_jd — queued status (webhook pre-created) ────────────────────────

@pytest.mark.asyncio
async def test_fetch_jd_processes_queued_vacancy(tmp_path):
    """When existing vacancy has status='queued', proceed with fetch and update fields."""
    doc = _make_doc(title="Queued PM Role")
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    ctx = _make_ctx(tmp_path, parser, user_id=1)

    queued_row = MagicMock()
    queued_row.__getitem__ = lambda self, key: {
        "id": 55,
        "title": "Senior PM",  # pre-populated from RSS feed
        "markdown_path": None,
        "status": "queued",
    }[key]

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=queued_row)
        mock_db.update_vacancy_fields = AsyncMock()
        mock_db.update_vacancy_status = AsyncMock()

        result = await cv_fetch_jd(ctx, "https://djinni.co/jobs/555/")

    # Should NOT have inserted a new record — updates existing
    mock_db.insert_vacancy.assert_not_called()
    mock_db.update_vacancy_fields.assert_awaited_once()
    call_kwargs = mock_db.update_vacancy_fields.call_args
    assert call_kwargs.args[0] == 55  # vacancy_id
    assert "✅" in result


@pytest.mark.asyncio
async def test_fetch_jd_non_queued_duplicate_skips_fetch(tmp_path):
    """When existing vacancy has status != 'queued', return early without fetching."""
    ctx = _make_ctx(tmp_path)
    existing_row = MagicMock()
    existing_row.__getitem__ = lambda self, key: {
        "id": 10,
        "title": "Old PM",
        "markdown_path": "/some/path/JD.md",
        "status": "analyzed",
    }[key]

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=existing_row)

        result = await cv_fetch_jd(ctx, "https://djinni.co/jobs/10/")

    assert "ℹ️" in result
    ctx.deps.parser_adapter.fetch_markdown.assert_not_called()
