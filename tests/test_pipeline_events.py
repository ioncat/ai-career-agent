"""
tests/test_pipeline_events.py - notifications phase 3: the three workers raise events.

Covers core/pipeline_events.py and the wiring in AnalysisWorker, CVWorker and CoverWorker: the event
and the state of a failure stored in one transaction, the event after a success, `origin` set by the
backend, the router's Web Push channel, and the API passing origin "user" for the owner's own clicks.
"""

import asyncio
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from core import pipeline_events
from core.analysis_worker import AnalysisWorker
from core.cover_worker import CoverWorker
from core.cv_worker import CVWorker
from core.llm_client import LLMError, LLMUnavailableError
from db import database


@pytest_asyncio.fixture
async def db_path(tmp_path):
    path = tmp_path / "test.db"
    database.configure(path)
    await database.init_db()
    con = sqlite3.connect(path)
    con.execute("INSERT INTO users (id, telegram_chat_id, name) VALUES (1, 111, 'Owner')")
    con.commit()
    con.close()
    return path


@pytest.fixture(autouse=True)
def _no_real_push():
    with patch("core.notifier._try_web_push", AsyncMock()) as push:
        yield push


async def _vacancy(status, n=1, title="Product Manager", company="Acme"):
    vid = await database.insert_vacancy(url=f"https://djinni.co/jobs/pe{n}/", title=title, status=status)
    await database.update_vacancy_fields(vid, company=company)
    return vid


def _worker(cls):
    deps = MagicMock()
    deps.user_id = 1
    return cls(deps=deps, settings=MagicMock(), llm_sem=asyncio.Semaphore(1))


def _tool(outcome):
    return AsyncMock(side_effect=outcome) if isinstance(outcome, Exception) else AsyncMock(return_value=outcome)


async def _events():
    return await database.list_notifications(1)


# ── CV: failure = state + event in one transaction ────────────────────────────

@pytest.mark.asyncio
async def test_a_failed_cv_run_stores_the_state_and_the_event_together(db_path):
    vid = await _vacancy("cv_generating")

    with patch("tools.cv_generate.cv_generate", _tool(LLMError("provider down"))):
        await _worker(CVWorker)._execute(vid, "Ukrainian", "user")

    row = await database.get_vacancy_by_id(vid)
    stored = database.decode_generation_failure(row["last_generation_failure"])
    assert row["status"] == "analyzed" and (stored["kind"], stored["code"], stored["lang"]) == ("cv", "llm_error", "uk")
    (event,) = await _events()
    assert (event["event"], event["severity"], event["origin"], event["code"], event["vacancy_id"]) == \
        ("cv_failed", "error", "user", "llm_error", vid)
    assert event["title"] == "CV failed — Acme — Product Manager" and event["body"] == "provider down"


@pytest.mark.asyncio
async def test_the_failure_event_comes_with_the_state_through_one_commit(db_path):
    """The event is inserted on the same connection, before the one commit of the state write."""
    vid = await _vacancy("cv_generating")
    order = []
    real_insert = database._insert_notification

    async def spy(db, *a, **kw):
        order.append("event inserted")
        return await real_insert(db, *a, **kw)

    with patch.object(database, "_insert_notification", spy):
        await database.fail_generation(
            vid, "cv", "boom", "analyzed", code="llm_error",
            notification={"user_id": 1, "event": "cv_failed", "vacancy_id": vid, "title": "t", "origin": "user"})

    assert order == ["event inserted"]
    assert (await database.get_vacancy_by_id(vid))["last_generation_failure"] is not None
    assert len(await _events()) == 1


@pytest.mark.asyncio
async def test_a_bad_event_never_costs_the_state_write(db_path):
    vid = await _vacancy("cv_generating")

    stored = await database.fail_generation(
        vid, "cv", "boom", "analyzed",
        notification={"user_id": 1, "event": "cv_failed", "vacancy_id": vid, "title": "t", "origin": "robot"})

    assert stored is None
    row = await database.get_vacancy_by_id(vid)
    assert row["status"] == "analyzed" and row["last_generation_failure"] is not None
    assert await _events() == []


@pytest.mark.asyncio
async def test_a_tool_warning_text_becomes_a_failure_event_with_its_code(db_path):
    vid = await _vacancy("cv_generating")

    with patch("tools.cv_generate.cv_generate", _tool("⚠️ Файл JD.md не найден:\n<code>x</code>")):
        await _worker(CVWorker)._execute(vid, "auto", "auto")

    (event,) = await _events()
    assert (event["event"], event["code"], event["origin"]) == ("cv_failed", "jd_missing", "auto")


# ── CV / cover: success = the event after the tool's own state write ──────────

@pytest.mark.asyncio
async def test_a_finished_cv_run_raises_a_success_event(db_path):
    vid = await _vacancy("cv_generating")

    async def tool(ctx, vacancy_id, language="auto"):
        await database.update_vacancy_status(vacancy_id, "cv_generated")      # the real tool writes this itself
        return "✅ CV готов"

    with patch("tools.cv_generate.cv_generate", tool):
        await _worker(CVWorker)._execute(vid, "auto", "user")

    (event,) = await _events()
    assert (event["event"], event["severity"], event["origin"], event["code"]) == ("cv_done", "success", "user", None)
    assert event["title"] == "CV ready — Acme — Product Manager"
    assert (await database.get_vacancy_by_id(vid))["status"] == "cv_generated"


@pytest.mark.asyncio
async def test_cover_failure_and_success_events(db_path):
    failed = await _vacancy("cover_generating", n=1)
    done = await _vacancy("cover_generating", n=2)

    with patch("tools.cv_cover.cv_cover", _tool(RuntimeError("render"))):
        await _worker(CoverWorker)._execute(failed, "user")
    with patch("tools.cv_cover.cv_cover", _tool("✅ Cover message готов")):
        await _worker(CoverWorker)._execute(done, "auto")

    by_vacancy = {e["vacancy_id"]: e for e in await _events()}
    assert (by_vacancy[failed]["event"], by_vacancy[failed]["origin"], by_vacancy[failed]["code"]) == \
        ("cover_failed", "user", "generation_failed")
    assert (by_vacancy[done]["event"], by_vacancy[done]["origin"]) == ("cover_done", "auto")
    assert (await database.get_vacancy_by_id(failed))["status"] == "cv_generated"


# ── analysis ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_finished_analysis_raises_a_success_event(db_path):
    vid = await _vacancy("analyzing")

    async def tool(ctx, vacancy_id):
        await database.update_vacancy_status(vacancy_id, "analyzed")
        return "✅ done"

    with patch("tools.cv_analyze.cv_analyze", tool):
        await _worker(AnalysisWorker)._execute(vid, "user")

    (event,) = await _events()
    assert (event["event"], event["severity"], event["origin"]) == ("analysis_done", "success", "user")
    assert event["title"] == "Analysis done — Acme — Product Manager"


@pytest.mark.asyncio
async def test_an_analysis_failure_the_tool_recorded_gets_its_event_afterwards(db_path):
    vid = await _vacancy("analyzing")

    async def tool(ctx, vacancy_id):
        await database.set_analysis_error(vacancy_id, "p2 parse failed")      # the real tool does this itself
        return "⚠️ Ошибка Claude на фазе 2:\nbad output"

    with patch("tools.cv_analyze.cv_analyze", tool):
        await _worker(AnalysisWorker)._execute(vid, "auto")

    (event,) = await _events()
    assert (event["event"], event["severity"], event["code"]) == ("analysis_failed", "error", "llm_error")
    assert event["body"] == "p2 parse failed"
    assert (await database.get_vacancy_by_id(vid))["status"] == "analysis_failed"


@pytest.mark.asyncio
async def test_a_tool_that_only_returns_a_warning_no_longer_leaves_the_vacancy_analyzing(db_path):
    vid = await _vacancy("analyzing")

    with patch("tools.cv_analyze.cv_analyze", _tool("⚠️ Файл JD.md не найден:\n<code>x</code>")):
        await _worker(AnalysisWorker)._execute(vid, "auto")

    row = await database.get_vacancy_by_id(vid)
    assert row["status"] == "analysis_failed" and "JD.md" in row["analysis_error"]
    (event,) = await _events()
    assert (event["event"], event["code"]) == ("analysis_failed", "jd_missing")


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome,code", [
    (RuntimeError("anything"), "analysis_failed"),
    (LLMError("provider down"), "llm_error"),
    (LLMUnavailableError("claude CLI timed out after 120s"), "llm_timeout"),
])
async def test_an_analysis_exception_stores_state_and_event_with_a_code(db_path, outcome, code):
    vid = await _vacancy("analyzing")

    with patch("tools.cv_analyze.cv_analyze", _tool(outcome)):
        await _worker(AnalysisWorker)._execute(vid, "auto")

    assert (await database.get_vacancy_by_id(vid))["status"] == "analysis_failed"
    (event,) = await _events()
    assert (event["event"], event["code"]) == ("analysis_failed", code)


@pytest.mark.asyncio
async def test_an_analysis_timeout_stores_state_and_event(db_path):
    vid = await _vacancy("analyzing")
    worker = _worker(AnalysisWorker)
    worker._ANALYSIS_TIMEOUT = 0.05

    async def hang(ctx, vacancy_id):
        await asyncio.sleep(10)

    with patch("tools.cv_analyze.cv_analyze", hang):
        await worker._execute(vid, "user")

    (event,) = await _events()
    assert (event["event"], event["code"], event["origin"]) == ("analysis_failed", "llm_timeout", "user")
    assert "timed out" in event["body"].lower()


# ── origin: set by the backend ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_enqueue_carries_the_origin_and_defaults_to_auto(db_path):
    vid = await _vacancy("fetched")
    for worker, args in ((_worker(CVWorker), ("English",)), (_worker(CoverWorker), ()), (_worker(AnalysisWorker), ())):
        await worker.enqueue(vid, *args, origin="user")
        assert worker._queue.get_nowait()[-1] == "user"
        await worker.enqueue(vid, *args)
        assert worker._queue.get_nowait()[-1] == "auto"


@pytest.mark.asyncio
async def test_the_recovery_sweep_is_automatic(db_path):
    vid = await _vacancy("analysis_queued")
    worker = _worker(AnalysisWorker)

    await worker._recover_queued()

    assert worker._queue.get_nowait() == (vid, "auto")


@pytest.mark.asyncio
async def test_the_api_marks_the_owners_own_clicks_as_user(db_path, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from web.api import app

    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("VACANCIES_PATH", str(tmp_path / "vacancies"))
    vid = await _vacancy("fetched")

    with TestClient(app) as client:
        app.state.analysis_worker = AsyncMock()
        app.state.cv_worker = AsyncMock()
        app.state.cover_worker = AsyncMock()
        client.post(f"/api/vacancies/{vid}/analyze")
        client.post(f"/api/vacancies/{vid}/generate-cv", json={"language": "uk"})
        client.post(f"/api/vacancies/{vid}/generate-cover")

        app.state.analysis_worker.enqueue.assert_awaited_once_with(vid, origin="user")
        app.state.cv_worker.enqueue.assert_awaited_once_with(vid, "Ukrainian", origin="user")
        app.state.cover_worker.enqueue.assert_awaited_once_with(vid, origin="user")


# ── the router's other channel: Web Push ──────────────────────────────────────

@pytest.mark.asyncio
async def test_a_stored_failure_event_goes_to_web_push_once(db_path, _no_real_push):
    vid = await _vacancy("cv_generating")

    with patch("tools.cv_generate.cv_generate", _tool(LLMError("provider down"))):
        await _worker(CVWorker)._execute(vid, "auto", "user")

    _no_real_push.assert_awaited_once()
    user_id, title, body = _no_real_push.await_args.args
    assert (user_id, title, body) == (1, "CV failed — Acme — Product Manager", "provider down")


@pytest.mark.asyncio
async def test_a_finished_analysis_pushes_through_the_router_not_a_second_path(db_path, _no_real_push):
    vid = await _vacancy("analyzing")

    async def tool(ctx, vacancy_id):
        await database.update_vacancy_status(vacancy_id, "analyzed")
        return "✅ done"

    with patch("tools.cv_analyze.cv_analyze", tool):
        await _worker(AnalysisWorker)._execute(vid, "auto")

    _no_real_push.assert_awaited_once()                      # the old direct _push_result is gone
    assert not hasattr(AnalysisWorker, "_push_result")


@pytest.mark.asyncio
async def test_a_failed_event_build_still_records_the_state(db_path):
    """If the label lookup fails, the failure state is written without its event."""
    vid = await _vacancy("cv_generating")

    with patch("tools.cv_generate.cv_generate", _tool(LLMError("down"))), \
         patch.object(pipeline_events, "vacancy_label", AsyncMock(side_effect=RuntimeError("db hiccup"))):
        await _worker(CVWorker)._execute(vid, "auto", "auto")

    row = await database.get_vacancy_by_id(vid)
    assert row["status"] == "analyzed" and row["last_generation_failure"] is not None
    assert await _events() == []
