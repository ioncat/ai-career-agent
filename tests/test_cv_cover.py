"""
tests/test_cv_cover.py — tests for tools/cv_cover.py.

Mocks: database, llm.complete, filesystem (tmp_path).
No real Claude API or DB needed.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.llm_client import LLMError
from tools.cv_cover import cv_cover


# ── Fixtures / helpers ────────────────────────────────────────────────────────

_COVER_OUTPUT = """Вітаю!

Кілька ключових моментів з мого досвіду, які найбільше стосуються вашої ролі:

- Вів продуктовий розвиток платформи з 0 до 500k MAU — повна відповідальність за discovery, roadmap та delivery.
- Координував 3 cross-functional команди (14 осіб), узгоджував пріоритети зі стейкхолдерами щоквартально.
- Скоротив time-to-market на 40% через впровадження dual-track agile та автоматизацію QA.

Буду радий поспілкуватися і дізнатися більше про продукт та команду.

Oleksii Bondarenko"""


def _make_ctx(tmp_path: Path, llm=None) -> MagicMock:
    ctx = MagicMock()
    ctx.deps.get_llm = AsyncMock(return_value=llm or _make_llm())
    ctx.deps.candidate_name = "Oleksii_Bondarenko"
    ctx.deps.vacancies_path = tmp_path / "vacancies"
    ctx.deps.skill_type = "pm"
    ctx.deps.user_id = 1
    return ctx


def _make_llm(side_effect=None, return_value: str = _COVER_OUTPUT) -> AsyncMock:
    llm = AsyncMock()
    llm.last_call_usage = None  # prevent **unpacking AsyncMock in insert_llm_usage
    if side_effect is not None:
        llm.complete = AsyncMock(side_effect=side_effect)
    else:
        llm.complete = AsyncMock(return_value=return_value)
    return llm


def _make_vacancy_row(
    jd_path: Path,
    vacancy_id: int = 1,
    title: str = "Product Manager",
    url: str = "https://djinni.co/jobs/456/",
) -> MagicMock:
    data = {
        "id": vacancy_id,
        "title": title,
        "markdown_path": str(jd_path),
        "url": url,
        "status": "cv_generated",
    }
    row = MagicMock()
    row.__getitem__ = lambda self, key: data[key]
    return row


def _write_vacancy_files(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create JD.md + JD_analysis.md + [Name]_CV.md.

    Returns (jd_path, analysis_path, cv_path).
    """
    jd_dir = tmp_path / "vacancies" / "djinni" / "2026-05" / "456"
    jd_dir.mkdir(parents=True)

    jd_path = jd_dir / "JD.md"
    jd_path.write_text("# Product Manager\n\nBuild great products.", encoding="utf-8")

    analysis_path = jd_dir / "JD_analysis.md"
    analysis_path.write_text("## Quick Scan\n\n**Fit score:** 8/10", encoding="utf-8")

    cv_path = jd_dir / "Oleksii_Bondarenko_CV.md"
    cv_path.write_text(
        "Oleksii Bondarenko\nProduct Manager\n\nSUMMARY\n\nStrong PM.",
        encoding="utf-8",
    )
    return jd_path, analysis_path, cv_path


def _mock_db(vacancy_row=None, run_id: int = 1) -> MagicMock:
    db = MagicMock()
    db.get_vacancy_by_id = AsyncMock(return_value=vacancy_row)
    db.insert_pipeline_run = AsyncMock(return_value=run_id)
    db.update_pipeline_run = AsyncMock()
    db.update_vacancy_status = AsyncMock()
    return db


# ── Happy path ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cover_happy_path(tmp_path):
    jd_path, _, _ = _write_vacancy_files(tmp_path)
    ctx = _make_ctx(tmp_path)
    mock_db = _mock_db(vacancy_row=_make_vacancy_row(jd_path))

    with patch("tools.cv_cover.database", mock_db):
        result = await cv_cover(ctx, 1)

    assert "✅" in result
    assert "Product Manager" in result


@pytest.mark.asyncio
async def test_cover_saves_cover_md(tmp_path):
    jd_path, _, _ = _write_vacancy_files(tmp_path)
    ctx = _make_ctx(tmp_path)
    mock_db = _mock_db(vacancy_row=_make_vacancy_row(jd_path))

    with patch("tools.cv_cover.database", mock_db):
        await cv_cover(ctx, 1)

    cover_path = jd_path.parent / "Oleksii_Bondarenko_Cover.md"
    assert cover_path.exists()
    content = cover_path.read_text(encoding="utf-8")
    assert "Вітаю" in content


@pytest.mark.asyncio
async def test_cover_returns_cover_text(tmp_path):
    jd_path, _, _ = _write_vacancy_files(tmp_path)
    ctx = _make_ctx(tmp_path)
    mock_db = _mock_db(vacancy_row=_make_vacancy_row(jd_path))

    with patch("tools.cv_cover.database", mock_db):
        result = await cv_cover(ctx, 1)

    assert "Вітаю" in result
    assert "Oleksii Bondarenko" in result


@pytest.mark.asyncio
async def test_cover_returns_file_path(tmp_path):
    jd_path, _, _ = _write_vacancy_files(tmp_path)
    ctx = _make_ctx(tmp_path)
    mock_db = _mock_db(vacancy_row=_make_vacancy_row(jd_path))

    with patch("tools.cv_cover.database", mock_db):
        result = await cv_cover(ctx, 1)

    assert "Cover.md" in result


@pytest.mark.asyncio
async def test_cover_updates_status(tmp_path):
    jd_path, _, _ = _write_vacancy_files(tmp_path)
    ctx = _make_ctx(tmp_path)
    mock_db = _mock_db(vacancy_row=_make_vacancy_row(jd_path))

    with patch("tools.cv_cover.database", mock_db):
        await cv_cover(ctx, 1)

    mock_db.update_vacancy_status.assert_awaited_once_with(1, "cover_generated")


@pytest.mark.asyncio
async def test_cover_calls_llm_once(tmp_path):
    jd_path, _, _ = _write_vacancy_files(tmp_path)
    llm = _make_llm()
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=_make_vacancy_row(jd_path))

    with patch("tools.cv_cover.database", mock_db):
        await cv_cover(ctx, 1)

    assert llm.complete.await_count == 1


@pytest.mark.asyncio
async def test_cover_phase4_input_contains_jd_analysis_and_cv(tmp_path):
    """Phase 4 user input must contain JD text, analysis, and CV text."""
    jd_path, _, _ = _write_vacancy_files(tmp_path)
    llm = _make_llm()
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=_make_vacancy_row(jd_path))

    with patch("tools.cv_cover.database", mock_db):
        await cv_cover(ctx, 1)

    user_input = llm.complete.call_args[0][0]
    assert "Build great products" in user_input  # JD text
    assert "Fit score" in user_input             # analysis
    assert "Strong PM" in user_input             # CV text


@pytest.mark.asyncio
async def test_cover_tracks_pipeline_run(tmp_path):
    jd_path, _, _ = _write_vacancy_files(tmp_path)
    ctx = _make_ctx(tmp_path)
    mock_db = _mock_db(vacancy_row=_make_vacancy_row(jd_path), run_id=42)

    with patch("tools.cv_cover.database", mock_db):
        await cv_cover(ctx, 1)

    mock_db.insert_pipeline_run.assert_awaited_once_with(1, phase="phase4")
    mock_db.update_pipeline_run.assert_any_await(42, status="running")
    expected_cover_path = str(jd_path.parent / "Oleksii_Bondarenko_Cover.md")
    mock_db.update_pipeline_run.assert_any_await(
        42, status="done", result_path=expected_cover_path
    )


# ── Error cases ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cover_vacancy_not_found(tmp_path):
    ctx = _make_ctx(tmp_path)
    mock_db = _mock_db(vacancy_row=None)

    with patch("tools.cv_cover.database", mock_db):
        result = await cv_cover(ctx, 999)

    assert "⚠️" in result
    assert "999" in result


@pytest.mark.asyncio
async def test_cover_jd_missing(tmp_path):
    jd_path, _, _ = _write_vacancy_files(tmp_path)
    jd_path.unlink()
    ctx = _make_ctx(tmp_path)
    mock_db = _mock_db(vacancy_row=_make_vacancy_row(jd_path))

    with patch("tools.cv_cover.database", mock_db):
        result = await cv_cover(ctx, 1)

    assert "⚠️" in result
    assert "JD.md" in result


@pytest.mark.asyncio
async def test_cover_analysis_missing(tmp_path):
    jd_path, analysis_path, _ = _write_vacancy_files(tmp_path)
    analysis_path.unlink()
    ctx = _make_ctx(tmp_path)
    mock_db = _mock_db(vacancy_row=_make_vacancy_row(jd_path))

    with patch("tools.cv_cover.database", mock_db):
        result = await cv_cover(ctx, 1)

    assert "⚠️" in result
    assert "JD_analysis.md" in result


@pytest.mark.asyncio
async def test_cover_cv_missing(tmp_path):
    jd_path, _, cv_path = _write_vacancy_files(tmp_path)
    cv_path.unlink()
    ctx = _make_ctx(tmp_path)
    mock_db = _mock_db(vacancy_row=_make_vacancy_row(jd_path))

    with patch("tools.cv_cover.database", mock_db):
        result = await cv_cover(ctx, 1)

    assert "⚠️" in result
    assert "CV" in result


@pytest.mark.asyncio
async def test_cover_llm_error_returns_warning(tmp_path):
    jd_path, _, _ = _write_vacancy_files(tmp_path)
    llm = _make_llm(side_effect=LLMError("rate limit"))
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=_make_vacancy_row(jd_path))

    with patch("tools.cv_cover.database", mock_db):
        result = await cv_cover(ctx, 1)

    assert "⚠️" in result
    assert "rate limit" in result


@pytest.mark.asyncio
async def test_cover_llm_error_no_status_update(tmp_path):
    jd_path, _, _ = _write_vacancy_files(tmp_path)
    llm = _make_llm(side_effect=LLMError("timeout"))
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=_make_vacancy_row(jd_path))

    with patch("tools.cv_cover.database", mock_db):
        await cv_cover(ctx, 1)

    mock_db.update_vacancy_status.assert_not_called()


@pytest.mark.asyncio
async def test_cover_llm_error_no_cover_md(tmp_path):
    jd_path, _, _ = _write_vacancy_files(tmp_path)
    llm = _make_llm(side_effect=LLMError("timeout"))
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=_make_vacancy_row(jd_path))

    with patch("tools.cv_cover.database", mock_db):
        await cv_cover(ctx, 1)

    cover_path = jd_path.parent / "Oleksii_Bondarenko_Cover.md"
    assert not cover_path.exists()
