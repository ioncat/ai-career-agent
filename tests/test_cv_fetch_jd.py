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
from tools.cv_fetch_jd import (
    FetchError,
    _detect_site,
    _safe_folder_name,
    _url_slug,
    cv_fetch_jd,
    fetch_jd,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_deps(tmp_path: Path, parser_adapter=None, user_id: int = 1) -> MagicMock:
    """Build a mock AgentDeps."""
    if parser_adapter is None:
        parser_adapter = AsyncMock()
    deps = MagicMock()
    deps.parser_adapter = parser_adapter
    deps.vacancies_path = tmp_path / "vacancies"
    deps.user_id = user_id
    return deps


def _make_ctx(tmp_path: Path, parser_adapter=None, user_id: int = 1) -> MagicMock:
    """Build a mock RunContext[AgentDeps]."""
    ctx = MagicMock()
    ctx.deps = _make_deps(tmp_path, parser_adapter, user_id)
    return ctx


def _make_doc(title="Backend Dev", markdown="## Job\nGreat role.", company=None) -> ParsedDocument:
    return ParsedDocument(
        title=title,
        markdown=markdown,
        source_url="https://djinni.co/jobs/123-backend/",
        company=company,
    )


def _mock_dedup(mock_db) -> None:
    """Add EPIC-26 dedup async mocks to a patched database mock."""
    mock_db.find_duplicate = AsyncMock(return_value=None)
    mock_db.set_content_hash = AsyncMock()
    mock_db.set_duplicate_of = AsyncMock()
    mock_db.update_vacancy_status = AsyncMock()


def _vacancy_row(
    vacancy_id: int = 42,
    title: str = "Backend Dev",
    site: str = "djinni",
    markdown_path: str = "/vacancies/inbox/1/42 — Backend Dev/JD.md",
    status: str = "fetched",
) -> MagicMock:
    row = MagicMock()
    data = {
        "id": vacancy_id,
        "title": title,
        "site": site,
        "markdown_path": markdown_path,
        "status": status,
    }
    row.__getitem__ = lambda self, key: data[key]
    return row


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
    assert slug == "my-job-2024"


def test_url_slug_max_length():
    long_url = "https://example.com/jobs/" + "a" * 100
    slug = _url_slug(long_url)
    assert len(slug) <= 60


def test_url_slug_empty_path():
    slug = _url_slug("https://example.com")
    assert slug == "vacancy"


# ── _safe_folder_name ─────────────────────────────────────────────────────────

def test_safe_folder_name_removes_forbidden_chars():
    assert _safe_folder_name('Role: "Lead" <PM>') == "Role Lead PM"


def test_safe_folder_name_strips_trailing_dot_space():
    assert _safe_folder_name("Company Inc. ") == "Company Inc"


def test_safe_folder_name_empty_falls_back():
    assert _safe_folder_name('""') == "vacancy"


def test_safe_folder_name_truncation_does_not_leave_trailing_space():
    # Regression: vacancy #889 — a title >80 chars whose 80th char landed on a
    # space produced a folder name ending in " ", which Windows silently trims
    # on mkdir but Path.write_text() does not — "No such file or directory".
    title = "889 — Product Owner (сервіси обліку та інтеграції, партнерські сервіси клієнтам, discovery)"
    result = _safe_folder_name(title)
    assert not result.endswith(" ")
    assert not result.endswith(".")
    assert len(result) <= 80


# ── fetch_jd — direct call (auto-pipeline path) ───────────────────────────────

@pytest.mark.asyncio
async def test_fetch_jd_returns_vacancy_id(tmp_path):
    doc = _make_doc()
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    deps = _make_deps(tmp_path, parser)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)
        mock_db.insert_vacancy = AsyncMock(return_value=77)
        mock_db.update_vacancy_fields = AsyncMock()
        _mock_dedup(mock_db)

        result = await fetch_jd(deps, "https://djinni.co/jobs/123/")

    assert result == 77


@pytest.mark.asyncio
async def test_fetch_jd_returns_existing_id_for_duplicate(tmp_path):
    deps = _make_deps(tmp_path)
    existing = _vacancy_row(vacancy_id=55, status="analyzed")

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=existing)

        result = await fetch_jd(deps, "https://djinni.co/jobs/999/")

    assert result == 55
    deps.parser_adapter.fetch_markdown.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_jd_raises_on_parser_error(tmp_path):
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(
        side_effect=ParserError("server error", url="https://djinni.co/jobs/1/", status_code=503)
    )
    deps = _make_deps(tmp_path, parser)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)

        with pytest.raises(FetchError, match="server error"):
            await fetch_jd(deps, "https://djinni.co/jobs/1/")


@pytest.mark.asyncio
async def test_fetch_jd_raises_on_empty_markdown(tmp_path):
    doc = ParsedDocument(title="Job", markdown="   ", source_url="https://djinni.co/jobs/1/")
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    deps = _make_deps(tmp_path, parser)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)

        with pytest.raises(FetchError, match="извлечь текст"):
            await fetch_jd(deps, "https://djinni.co/jobs/1/")


@pytest.mark.asyncio
async def test_fetch_jd_writes_jd_md(tmp_path):
    doc = _make_doc(title="Python Dev", markdown="## Details\nExcellent.")
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    deps = _make_deps(tmp_path, parser)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)
        mock_db.insert_vacancy = AsyncMock(return_value=5)
        mock_db.update_vacancy_fields = AsyncMock()
        _mock_dedup(mock_db)

        await fetch_jd(deps, "https://djinni.co/jobs/456/")

    saved = list(deps.vacancies_path.rglob("JD.md"))
    assert len(saved) == 1
    content = saved[0].read_text()
    assert "Python Dev" in content
    assert "Excellent." in content


@pytest.mark.asyncio
async def test_fetch_jd_processes_queued_vacancy(tmp_path):
    doc = _make_doc(title="Queued PM Role")
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    deps = _make_deps(tmp_path, parser)

    queued = _vacancy_row(vacancy_id=55, status="queued")

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=queued)
        mock_db.update_vacancy_fields = AsyncMock()
        _mock_dedup(mock_db)

        result = await fetch_jd(deps, "https://djinni.co/jobs/555/")

    assert result == 55
    mock_db.insert_vacancy.assert_not_called()
    mock_db.update_vacancy_fields.assert_awaited_once()


# ── cv_fetch_jd — PydanticAI tool (string return) ────────────────────────────

@pytest.mark.asyncio
async def test_cv_fetch_jd_happy_path_returns_string(tmp_path):
    doc = _make_doc()
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    ctx = _make_ctx(tmp_path, parser)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)
        mock_db.insert_vacancy = AsyncMock(return_value=42)
        mock_db.update_vacancy_fields = AsyncMock()
        mock_db.get_vacancy_by_id = AsyncMock(
            return_value=_vacancy_row(vacancy_id=42, title="Backend Dev")
        )
        _mock_dedup(mock_db)

        result = await cv_fetch_jd(ctx, "https://djinni.co/jobs/123-backend/")

    assert "✅" in result
    assert "Backend Dev" in result
    assert "42" in result


@pytest.mark.asyncio
async def test_cv_fetch_jd_saves_file(tmp_path):
    doc = _make_doc()
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    ctx = _make_ctx(tmp_path, parser)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)
        mock_db.insert_vacancy = AsyncMock(return_value=1)
        mock_db.update_vacancy_fields = AsyncMock()
        mock_db.get_vacancy_by_id = AsyncMock(
            return_value=_vacancy_row(vacancy_id=1, title="Backend Dev")
        )
        _mock_dedup(mock_db)

        await cv_fetch_jd(ctx, "https://djinni.co/jobs/123-backend/")

    saved = list(ctx.deps.vacancies_path.rglob("JD.md"))
    assert len(saved) == 1
    content = saved[0].read_text()
    assert "Backend Dev" in content
    assert "Great role." in content


@pytest.mark.asyncio
async def test_cv_fetch_jd_correct_folder_structure(tmp_path):
    doc = _make_doc()
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    ctx = _make_ctx(tmp_path, parser)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)
        mock_db.insert_vacancy = AsyncMock(return_value=1)
        mock_db.update_vacancy_fields = AsyncMock()
        mock_db.get_vacancy_by_id = AsyncMock(
            return_value=_vacancy_row(vacancy_id=1, title="Backend Dev")
        )
        _mock_dedup(mock_db)

        await cv_fetch_jd(ctx, "https://djinni.co/jobs/123-backend/")

    saved = list(ctx.deps.vacancies_path.rglob("JD.md"))
    path_parts = saved[0].parts
    assert "inbox" in path_parts
    assert "1" in path_parts
    assert any("Backend Dev" in p for p in path_parts)


@pytest.mark.asyncio
async def test_cv_fetch_jd_calls_db_insert(tmp_path):
    doc = _make_doc(title="Python Dev")
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    ctx = _make_ctx(tmp_path, parser)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)
        mock_db.insert_vacancy = AsyncMock(return_value=5)
        mock_db.update_vacancy_fields = AsyncMock()
        mock_db.get_vacancy_by_id = AsyncMock(
            return_value=_vacancy_row(vacancy_id=5, title="Python Dev")
        )
        _mock_dedup(mock_db)

        await cv_fetch_jd(ctx, "https://djinni.co/jobs/456-python/")

    mock_db.insert_vacancy.assert_awaited_once()
    call_kwargs = mock_db.insert_vacancy.call_args.kwargs
    assert call_kwargs["url"] == "https://djinni.co/jobs/456-python/"
    assert call_kwargs["title"] == "Python Dev"
    assert call_kwargs["site"] == "djinni"
    assert call_kwargs["user_id"] == 1


@pytest.mark.asyncio
async def test_cv_fetch_jd_duplicate_returns_info_string(tmp_path):
    ctx = _make_ctx(tmp_path)
    existing = _vacancy_row(vacancy_id=7, title="Existing Job", status="analyzed")

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=existing)

        result = await cv_fetch_jd(ctx, "https://djinni.co/jobs/123/")

    assert "ℹ️" in result
    assert "уже в базе" in result
    ctx.deps.parser_adapter.fetch_markdown.assert_not_called()


@pytest.mark.asyncio
async def test_cv_fetch_jd_parser_error_returns_warning(tmp_path):
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


@pytest.mark.asyncio
async def test_cv_fetch_jd_empty_markdown_returns_warning(tmp_path):
    doc = ParsedDocument(title="Job", markdown="   ", source_url="https://djinni.co/jobs/1/")
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    ctx = _make_ctx(tmp_path, parser)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)

        result = await cv_fetch_jd(ctx, "https://djinni.co/jobs/1/")

    assert "⚠️" in result
    assert "извлечь текст" in result


@pytest.mark.asyncio
async def test_cv_fetch_jd_path_scoped_to_user_id(tmp_path):
    doc = _make_doc()
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    ctx = _make_ctx(tmp_path, parser, user_id=7)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)
        mock_db.insert_vacancy = AsyncMock(return_value=10)
        mock_db.update_vacancy_fields = AsyncMock()
        mock_db.get_vacancy_by_id = AsyncMock(
            return_value=_vacancy_row(vacancy_id=10, title="Backend Dev")
        )
        _mock_dedup(mock_db)

        await cv_fetch_jd(ctx, "https://djinni.co/jobs/777-senior/")

    saved = list(ctx.deps.vacancies_path.rglob("JD.md"))
    assert len(saved) == 1
    relative = saved[0].relative_to(ctx.deps.vacancies_path)
    assert relative.parts[0] == "inbox"
    assert relative.parts[1] == "7"


@pytest.mark.asyncio
async def test_cv_fetch_jd_passes_user_id_to_db(tmp_path):
    doc = _make_doc()
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    ctx = _make_ctx(tmp_path, parser, user_id=42)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)
        mock_db.insert_vacancy = AsyncMock(return_value=99)
        mock_db.update_vacancy_fields = AsyncMock()
        mock_db.get_vacancy_by_id = AsyncMock(
            return_value=_vacancy_row(vacancy_id=99, title="Backend Dev")
        )
        _mock_dedup(mock_db)

        await cv_fetch_jd(ctx, "https://djinni.co/jobs/999-test/")

    call_kwargs = mock_db.insert_vacancy.call_args.kwargs
    assert call_kwargs["user_id"] == 42


@pytest.mark.asyncio
async def test_cv_fetch_jd_queued_vacancy_updates_not_inserts(tmp_path):
    doc = _make_doc(title="Queued PM Role", company="Real Company Name")
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    ctx = _make_ctx(tmp_path, parser, user_id=1)

    queued = _vacancy_row(vacancy_id=55, title="Senior PM", status="queued")

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=queued)
        mock_db.update_vacancy_fields = AsyncMock()
        mock_db.get_vacancy_by_id = AsyncMock(
            return_value=_vacancy_row(vacancy_id=55, title="Queued PM Role")
        )
        _mock_dedup(mock_db)

        result = await cv_fetch_jd(ctx, "https://djinni.co/jobs/555/")

    mock_db.insert_vacancy.assert_not_called()
    mock_db.update_vacancy_fields.assert_awaited_once()
    call_args = mock_db.update_vacancy_fields.call_args
    assert call_args is not None
    assert call_args.args[0] == 55
    # The correctly-parsed company (from ParsedDocument, not the RSS-ingest
    # guess) must be persisted — found live 2026-07-25 that it was computed
    # and used for folder naming / dedup but never written back to the DB,
    # leaving the original bad RSS-heuristic company value stuck forever.
    assert call_args.kwargs["company"] == "Real Company Name"
    assert "✅" in result


@pytest.mark.asyncio
async def test_cv_fetch_jd_non_queued_duplicate_skips_fetch(tmp_path):
    ctx = _make_ctx(tmp_path)
    existing = _vacancy_row(vacancy_id=10, title="Old PM", status="analyzed")

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=existing)

        result = await cv_fetch_jd(ctx, "https://djinni.co/jobs/10/")

    assert "ℹ️" in result
    ctx.deps.parser_adapter.fetch_markdown.assert_not_called()


# ── EPIC-26: dedup + content hash ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_jd_sets_content_hash(tmp_path):
    doc = _make_doc()
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    deps = _make_deps(tmp_path, parser)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)
        mock_db.insert_vacancy = AsyncMock(return_value=10)
        mock_db.update_vacancy_fields = AsyncMock()
        _mock_dedup(mock_db)

        await fetch_jd(deps, "https://djinni.co/jobs/123/")

    mock_db.set_content_hash.assert_awaited_once()
    call_args = mock_db.set_content_hash.call_args
    assert call_args.args[0] == 10
    assert isinstance(call_args.args[1], str)
    assert len(call_args.args[1]) == 64  # sha256 hex digest length


@pytest.mark.asyncio
async def test_fetch_jd_normalizes_title_with_company_before_dedup_lookup(tmp_path):
    """find_duplicate() must receive a company-suffix-stripped title.

    Found live 2026-07-25: the same real job posted on DOU (title gets a
    " — Company" suffix appended by the RSS parser) and Djinni (bare title,
    no suffix) never deduped, even when company data was correct, because
    the raw title strings differed. _normalize_title() strips a trailing
    "<dash> {company}" suffix — this asserts fetch_jd actually passes
    doc.company through to it, not just the bare title.
    """
    from db import database as real_database

    doc = _make_doc(
        title="Product Manager (Globalization) — Headway Inc",
        company="Headway Inc",
    )
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    deps = _make_deps(tmp_path, parser)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)
        mock_db.insert_vacancy = AsyncMock(return_value=11)
        mock_db.update_vacancy_fields = AsyncMock()
        mock_db._normalize_title = real_database._normalize_title
        _mock_dedup(mock_db)

        await fetch_jd(deps, "https://djinni.co/jobs/123/")

    mock_db.find_duplicate.assert_awaited_once()
    call_args = mock_db.find_duplicate.call_args
    normalized_title = call_args.args[2]
    assert normalized_title == "product manager (globalization)"


@pytest.mark.asyncio
async def test_fetch_jd_marks_duplicate_when_found(tmp_path):
    doc = _make_doc()
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    deps = _make_deps(tmp_path, parser)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)
        mock_db.insert_vacancy = AsyncMock(return_value=20)
        mock_db.update_vacancy_fields = AsyncMock()
        mock_db.find_duplicate = AsyncMock(return_value=5)  # original found
        mock_db.set_content_hash = AsyncMock()
        mock_db.set_duplicate_of = AsyncMock()
        mock_db.update_vacancy_status = AsyncMock()

        await fetch_jd(deps, "https://djinni.co/jobs/999/")

    mock_db.set_duplicate_of.assert_awaited_once_with(20, 5)


@pytest.mark.asyncio
async def test_fetch_jd_no_duplicate_call_when_none(tmp_path):
    doc = _make_doc()
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    deps = _make_deps(tmp_path, parser)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)
        mock_db.insert_vacancy = AsyncMock(return_value=30)
        mock_db.update_vacancy_fields = AsyncMock()
        _mock_dedup(mock_db)

        await fetch_jd(deps, "https://djinni.co/jobs/888/")

    mock_db.set_duplicate_of.assert_not_awaited()


# ── Stuck-row regression (2026-08-11, vacancy #106) ─────────────────────────
#
# Root cause: insert_vacancy() defaults status to 'fetched' (schema default)
# when no status kwarg is passed. A fresh-URL insert used to omit it, so the
# row was already "done" the instant it existed in the DB — even though
# markdown_path was still NULL. Any failure between that insert and the final
# markdown_path write (e.g. the dedup lookup) then left the row permanently
# orphaned: no retry mechanism ever revisits a 'fetched' row (only
# 'fetching'/'queued' are covered by RSSWatcher's retry loop and
# reset_stuck_statuses()). Flutter surfaced it as a raw "Failed to load JD:
# Exception: JD not found" that never resolved, even on refresh.

@pytest.mark.asyncio
async def test_fetch_jd_inserts_new_vacancy_as_fetching(tmp_path):
    doc = _make_doc()
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    deps = _make_deps(tmp_path, parser)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)
        mock_db.insert_vacancy = AsyncMock(return_value=200)
        mock_db.update_vacancy_fields = AsyncMock()
        _mock_dedup(mock_db)

        await fetch_jd(deps, "https://djinni.co/jobs/123/")

    call_kwargs = mock_db.insert_vacancy.call_args.kwargs
    assert call_kwargs["status"] == "fetching"


@pytest.mark.asyncio
async def test_fetch_jd_transitions_to_fetched_on_success(tmp_path):
    doc = _make_doc()
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    deps = _make_deps(tmp_path, parser)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)
        mock_db.insert_vacancy = AsyncMock(return_value=201)
        mock_db.update_vacancy_fields = AsyncMock()
        _mock_dedup(mock_db)

        await fetch_jd(deps, "https://djinni.co/jobs/123/")

    mock_db.update_vacancy_status.assert_awaited_once_with(201, "fetched")


@pytest.mark.asyncio
async def test_fetch_jd_markdown_path_saved_before_dedup_runs(tmp_path):
    """markdown_path must reach the DB even if the dedup step never runs —
    ordering regression, not just a mock-call-count check."""
    doc = _make_doc()
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    deps = _make_deps(tmp_path, parser)

    calls: list[str] = []

    async def _update_fields(*a, **kw):
        calls.append("update_vacancy_fields")

    async def _find_duplicate(*a, **kw):
        calls.append("find_duplicate")
        return None

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)
        mock_db.insert_vacancy = AsyncMock(return_value=202)
        mock_db.update_vacancy_fields = AsyncMock(side_effect=_update_fields)
        mock_db.find_duplicate = AsyncMock(side_effect=_find_duplicate)
        mock_db.set_content_hash = AsyncMock()
        mock_db.set_duplicate_of = AsyncMock()
        mock_db.update_vacancy_status = AsyncMock()

        await fetch_jd(deps, "https://djinni.co/jobs/123/")

    assert calls == ["update_vacancy_fields", "find_duplicate"]


@pytest.mark.asyncio
async def test_fetch_jd_dedup_failure_does_not_block_fetched_status(tmp_path):
    """Regression for vacancy #106: a dedup-step exception must not leave the
    vacancy stuck at an intermediate status with no retry path."""
    doc = _make_doc()
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    deps = _make_deps(tmp_path, parser)

    with patch("tools.cv_fetch_jd.database") as mock_db:
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)
        mock_db.insert_vacancy = AsyncMock(return_value=203)
        mock_db.update_vacancy_fields = AsyncMock()
        mock_db.find_duplicate = AsyncMock(side_effect=RuntimeError("db locked"))
        mock_db.update_vacancy_status = AsyncMock()

        result = await fetch_jd(deps, "https://djinni.co/jobs/123/")

    assert result == 203
    mock_db.update_vacancy_fields.assert_awaited_once()
    mock_db.update_vacancy_status.assert_awaited_once_with(203, "fetched")
