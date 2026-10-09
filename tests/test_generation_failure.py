"""
tests/test_generation_failure.py - a failed CV / cover generation stays visible on the vacancy.

Covers: the stored failure (db/database.py fail_generation, decode_generation_failure, the clear
inside update_vacancy_status), what counts as a failure (core/generation_failure.py), and both
workers (core/cv_worker.py, core/cover_worker.py), including the "soft" failure where a tool
returns a warning string instead of raising.
"""

import asyncio
import json
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from core.cover_worker import CoverWorker
from core.cv_worker import CVWorker
from core.generation_failure import exception_reason, soft_failure_reason
from db import database


@pytest_asyncio.fixture
async def db_path(tmp_path):
    path = tmp_path / "test.db"
    database.configure(path)
    await database.init_db()
    return path


async def _vacancy(n, status="analyzed"):
    return await database.insert_vacancy(url=f"https://djinni.co/jobs/gf{n}/", status=status)


async def _failure(vid):
    return database.decode_generation_failure((await database.get_vacancy_by_id(vid))["last_generation_failure"])


# ── what counts as a failure ──────────────────────────────────────────────────

def test_soft_failure_reason_strips_the_sign_and_markup():
    reason = soft_failure_reason("⚠️ Файл JD.md не найден:\n<code>vacancies/x/JD.md</code>")
    assert reason == "Файл JD.md не найден: vacancies/x/JD.md"


def test_a_success_text_or_a_non_string_is_not_a_failure():
    assert soft_failure_reason("✅ CV готов — <b>PM</b>") is None
    assert soft_failure_reason(None) is None
    assert soft_failure_reason("") is None


def test_exception_reason_falls_back_to_the_class_name():
    assert exception_reason(ValueError("bad input")) == "bad input"
    assert exception_reason(TimeoutError()) == "TimeoutError"


# ── the stored failure ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fail_generation_rolls_back_the_status_and_stores_kind_reason_time(db_path):
    vid = await _vacancy(1, status="cv_generating")

    await database.fail_generation(vid, "cv", "LLM timeout", "analyzed")

    row = await database.get_vacancy_by_id(vid)
    assert row["status"] == "analyzed"
    failure = database.decode_generation_failure(row["last_generation_failure"])
    assert failure["kind"] == "cv" and failure["reason"] == "LLM timeout"
    assert len(failure["at"]) == 19  # UTC, "YYYY-MM-DD HH:MM:SS"


@pytest.mark.asyncio
async def test_fail_generation_cuts_a_long_reason_and_rejects_an_unknown_kind(db_path):
    vid = await _vacancy(2, status="cover_generating")

    await database.fail_generation(vid, "cover", "x" * 900, "cv_generated")
    assert len((await _failure(vid))["reason"]) == database.GENERATION_FAILURE_REASON_MAX

    with pytest.raises(ValueError):
        await database.fail_generation(vid, "pdf", "boom", "cv_generated")


@pytest.mark.asyncio
async def test_fail_generation_is_picked_up_by_the_since_poll(db_path):
    vid = await _vacancy(3, status="cv_generating")
    con = sqlite3.connect(db_path)
    con.execute("UPDATE vacancies SET updated_at = '2026-01-01 00:00:00' WHERE id = ?", (vid,))
    con.commit()
    con.close()

    await database.fail_generation(vid, "cv", "boom", "analyzed")

    rows = await database.list_vacancies(since="2026-06-01T00:00:00")
    assert vid in [r["id"] for r in rows]


@pytest.mark.asyncio
async def test_success_of_the_same_kind_clears_the_failure_in_the_same_write(db_path):
    vid = await _vacancy(4)
    await database.fail_generation(vid, "cv", "boom", "analyzed")

    await database.update_vacancy_status(vid, "cv_generated")

    assert await _failure(vid) is None
    assert (await database.get_vacancy_by_id(vid))["status"] == "cv_generated"


@pytest.mark.asyncio
async def test_success_of_the_other_kind_keeps_the_failure(db_path):
    vid = await _vacancy(5, status="cv_generated")
    await database.fail_generation(vid, "cover", "boom", "cv_generated")

    await database.update_vacancy_status(vid, "cv_generated")       # a CV status is not a cover success

    assert (await _failure(vid))["kind"] == "cover"


@pytest.mark.asyncio
async def test_other_status_changes_keep_the_failure(db_path):
    vid = await _vacancy(6)
    await database.fail_generation(vid, "cv", "boom", "analyzed")

    await database.update_vacancy_status(vid, "declined")
    await database.update_vacancy_status(vid, "analyzed")

    assert (await _failure(vid))["kind"] == "cv"


@pytest.mark.asyncio
async def test_a_new_failure_replaces_the_old_one(db_path):
    vid = await _vacancy(7)
    await database.fail_generation(vid, "cv", "first", "analyzed")
    await database.fail_generation(vid, "cv", "second", "analyzed")

    assert (await _failure(vid))["reason"] == "second"


@pytest.mark.asyncio
async def test_a_row_without_a_stored_failure_decodes_to_none(db_path):
    vid = await _vacancy(8)
    assert (await database.get_vacancy_by_id(vid))["last_generation_failure"] is None
    assert await _failure(vid) is None


@pytest.mark.parametrize("raw", [None, "", "not json", "[]", '{"kind": "pdf", "reason": "x"}', '{"reason": "x"}'])
def test_decode_ignores_missing_or_malformed_values(raw):
    assert database.decode_generation_failure(raw) is None


def test_decode_keeps_kind_reason_at():
    raw = json.dumps({"kind": "cover", "reason": "r", "at": "2026-10-09 10:00:00"})
    assert database.decode_generation_failure(raw) == {
        "kind": "cover", "target": None, "reason": "r", "code": None, "lang": None,
        "at": "2026-10-09 10:00:00"}


# ── the workers ───────────────────────────────────────────────────────────────

def _worker(cls):
    return cls(deps=MagicMock(), settings=MagicMock(), llm_sem=asyncio.Semaphore(1))


def _tool(outcome):
    return AsyncMock(side_effect=outcome) if isinstance(outcome, Exception) else AsyncMock(return_value=outcome)


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome,expected", [
    (RuntimeError("LLM provider error"), "LLM provider error"),
    ("⚠️ Ошибка Claude на фазе 3:\nrate limit", "rate limit"),
])
async def test_cv_worker_failure_is_recorded_and_the_status_rolled_back(db_path, outcome, expected):
    vid = await _vacancy(10, status="cv_generating")

    with patch("tools.cv_generate.cv_generate", _tool(outcome)):
        await _worker(CVWorker)._execute(vid, "auto")

    row = await database.get_vacancy_by_id(vid)
    assert row["status"] == "analyzed"
    failure = database.decode_generation_failure(row["last_generation_failure"])
    assert failure["kind"] == "cv" and expected in failure["reason"]


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome,expected", [
    (RuntimeError("PDF render error"), "PDF render error"),
    ("⚠️ Ошибка Claude на фазе 4:\nrate limit", "rate limit"),
])
async def test_cover_worker_failure_is_recorded_and_the_status_rolled_back(db_path, outcome, expected):
    vid = await _vacancy(11, status="cover_generating")

    with patch("tools.cv_cover.cv_cover", _tool(outcome)):
        await _worker(CoverWorker)._execute(vid)

    row = await database.get_vacancy_by_id(vid)
    assert row["status"] == "cv_generated"
    failure = database.decode_generation_failure(row["last_generation_failure"])
    assert failure["kind"] == "cover" and expected in failure["reason"]


@pytest.mark.asyncio
async def test_a_timeout_without_a_message_still_gives_a_reason(db_path):
    vid = await _vacancy(12, status="cv_generating")

    with patch("tools.cv_generate.cv_generate", _tool(TimeoutError())):
        await _worker(CVWorker)._execute(vid, "auto")

    assert (await _failure(vid))["reason"] == "TimeoutError"


@pytest.mark.asyncio
async def test_a_successful_cv_run_clears_an_earlier_cv_failure(db_path):
    vid = await _vacancy(13)
    await database.fail_generation(vid, "cv", "boom", "analyzed")

    async def real_tool_like(ctx, vacancy_id, language="auto"):   # the real tool ends with this write
        await database.update_vacancy_status(vacancy_id, "cv_generated")
        return "✅ CV готов"

    with patch("tools.cv_generate.cv_generate", real_tool_like):
        await _worker(CVWorker)._execute(vid, "auto")

    row = await database.get_vacancy_by_id(vid)
    assert row["status"] == "cv_generated" and row["last_generation_failure"] is None


@pytest.mark.asyncio
async def test_a_failed_retry_leaves_one_current_failure(db_path):
    vid = await _vacancy(14, status="cv_generating")
    with patch("tools.cv_generate.cv_generate", _tool(RuntimeError("first"))):
        await _worker(CVWorker)._execute(vid, "auto")
    await database.update_vacancy_status(vid, "cv_generating")        # the user pressed retry
    with patch("tools.cv_generate.cv_generate", _tool(RuntimeError("second"))):
        await _worker(CVWorker)._execute(vid, "auto")

    assert (await _failure(vid))["reason"] == "second"


# ── kind "pdf": the document exists, only its render failed ───────────────────

@pytest.mark.asyncio
async def test_pdf_failure_is_recorded_without_touching_the_status(db_path):
    vid = await _vacancy(20, status="cv_generated")

    await database.record_pdf_failure(vid, "cv", "pdf-service unavailable")

    row = await database.get_vacancy_by_id(vid)
    assert row["status"] == "cv_generated"
    failure = database.decode_generation_failure(row["last_generation_failure"])
    assert (failure["kind"], failure["target"], failure["reason"]) == ("pdf", "cv", "pdf-service unavailable")


@pytest.mark.asyncio
async def test_pdf_failure_rejects_an_unknown_target_and_fail_generation_rejects_pdf(db_path):
    vid = await _vacancy(21, status="cv_generated")

    with pytest.raises(ValueError):
        await database.record_pdf_failure(vid, "letter", "boom")
    with pytest.raises(ValueError):
        await database.fail_generation(vid, "pdf", "boom", "cv_generated")   # pdf never rolls back a status


@pytest.mark.asyncio
async def test_pdf_failure_is_picked_up_by_the_since_poll(db_path):
    vid = await _vacancy(22, status="cv_generated")
    con = sqlite3.connect(db_path)
    con.execute("UPDATE vacancies SET updated_at = '2026-01-01 00:00:00' WHERE id = ?", (vid,))
    con.commit()
    con.close()

    await database.record_pdf_failure(vid, "cover", "boom")

    assert vid in [r["id"] for r in await database.list_vacancies(since="2026-06-01T00:00:00")]


@pytest.mark.asyncio
async def test_successful_render_of_the_same_target_clears_the_pdf_failure(db_path):
    vid = await _vacancy(23, status="cv_generated")
    await database.record_pdf_failure(vid, "cv", "boom")

    assert await database.clear_pdf_failure(vid, "cv") is True
    assert await _failure(vid) is None
    assert await database.clear_pdf_failure(vid, "cv") is False        # nothing left to clear


@pytest.mark.asyncio
async def test_render_of_the_other_target_keeps_the_pdf_failure(db_path):
    vid = await _vacancy(24, status="cv_generated")
    await database.record_pdf_failure(vid, "cv", "boom")

    assert await database.clear_pdf_failure(vid, "cover") is False
    assert (await _failure(vid))["target"] == "cv"


@pytest.mark.asyncio
async def test_a_render_never_clears_a_cv_or_cover_generation_failure(db_path):
    vid = await _vacancy(25)
    await database.fail_generation(vid, "cv", "LLM error", "analyzed")

    assert await database.clear_pdf_failure(vid, "cv") is False
    assert (await _failure(vid))["kind"] == "cv"


@pytest.mark.asyncio
async def test_a_successful_cv_status_does_not_clear_a_pdf_failure(db_path):
    """Only the render outcome ends a pdf failure, not the CV status write."""
    vid = await _vacancy(26)
    await database.record_pdf_failure(vid, "cv", "boom")

    await database.update_vacancy_status(vid, "cv_generated")

    assert (await _failure(vid))["kind"] == "pdf"


@pytest.mark.parametrize("raw", ['{"kind": "pdf", "reason": "x"}', '{"kind": "pdf", "target": "letter", "reason": "x"}'])
def test_decode_rejects_a_pdf_failure_without_a_valid_target(raw):
    assert database.decode_generation_failure(raw) is None
