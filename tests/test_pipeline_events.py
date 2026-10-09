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
    assert event["title"] == "CV failed — Acme — Product Manager"
    assert event["body"] == "The model provider returned an error."          # the stable text of the code, not the raw reason


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
    assert event["body"] == "The model provider returned an error."
    row = await database.get_vacancy_by_id(vid)
    assert row["status"] == "analysis_failed" and row["analysis_error"] == "p2 parse failed"   # the raw reason stays on the vacancy


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
    assert event["body"] == "The model did not answer in time."


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

    for name in ("analysis_worker", "cv_worker", "cover_worker"):       # restored after the test (monkeypatch)
        monkeypatch.setattr(app.state, name, AsyncMock(), raising=False)
    with TestClient(app) as client:
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
    assert (user_id, title, body) == (1, "CV failed — Acme — Product Manager", "The model provider returned an error.")


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


# ── review follow-up: nothing technical in a notification, caps, the watcher path, never raising ──

@pytest.mark.asyncio
async def test_a_failure_notification_never_carries_the_raw_reason(db_path, _no_real_push):
    """The raw reason can hold a local path or scraped text: it stays on the vacancy, the event gets the code's text."""
    vid = await _vacancy("cv_generating")
    secret = "/data/vacancies/inbox/1/12 — Секрет/JD.md не найден"

    with patch("tools.cv_generate.cv_generate", _tool(RuntimeError(secret))):
        await _worker(CVWorker)._execute(vid, "auto", "user")

    (event,) = await _events()
    assert secret not in event["body"] and secret not in event["title"]
    assert event["body"] == "The generation failed. Open the vacancy to see the reason and retry."
    assert secret not in " ".join(str(a) for a in _no_real_push.await_args.args)          # nor in the push payload
    stored = database.decode_generation_failure((await database.get_vacancy_by_id(vid))["last_generation_failure"])
    assert stored["reason"] == secret                                                      # the card still has it


@pytest.mark.asyncio
async def test_a_very_long_scraped_title_is_capped_in_the_event(db_path):
    vid = await _vacancy("cv_generating", title="T" * 900, company="C" * 900)

    with patch("tools.cv_generate.cv_generate", _tool(LLMError("down"))):
        await _worker(CVWorker)._execute(vid, "auto", "auto")

    (event,) = await _events()
    assert len(event["title"]) <= database.NOTIFICATION_TITLE_MAX
    assert event["title"].startswith("CV failed — ") and "…" in event["title"]


@pytest.mark.asyncio
async def test_the_database_layer_caps_title_and_body_and_normalises_the_code(db_path):
    nid = await database.insert_notification(1, "cv_failed", title="t" * 1000, body="b" * 1000, code="not_a_code")

    row = next(r for r in await _events() if r["id"] == nid)
    assert len(row["title"]) == database.NOTIFICATION_TITLE_MAX
    assert len(row["body"]) == database.NOTIFICATION_BODY_MAX
    assert row["code"] == "unknown"


def test_every_failure_code_has_a_user_text_without_technical_detail():
    from core import failure_codes
    assert set(failure_codes.USER_TEXT) == set(failure_codes.ALL_CODES)
    for text in failure_codes.USER_TEXT.values():
        assert text and text.isascii() and "/" not in text and "\\" not in text and len(text) < 100
    assert failure_codes.user_text("something_new") == failure_codes.USER_TEXT["unknown"]


# the finishing step of an analysis never raises and never leaves a warning-text failure "analyzing"

@pytest.mark.asyncio
async def test_a_read_error_after_a_warning_text_still_records_the_failure(db_path):
    vid = await _vacancy("analyzing")
    real = database.get_vacancy_by_id
    calls = {"n": 0}

    async def flaky(vacancy_id):
        calls["n"] += 1
        if calls["n"] == 1:                       # the first read in finish_analysis fails
            raise RuntimeError("db hiccup")
        return await real(vacancy_id)

    with patch.object(database, "get_vacancy_by_id", flaky):
        await pipeline_events.finish_analysis(1, vid, "⚠️ Файл JD.md не найден:\n<code>x</code>", "auto")

    assert (await real(vid))["status"] == "analysis_failed"


@pytest.mark.asyncio
async def test_a_read_error_after_a_clean_result_does_not_mark_the_analysis_failed(db_path):
    vid = await _vacancy("analyzed")

    with patch.object(database, "get_vacancy_by_id", AsyncMock(side_effect=RuntimeError("db hiccup"))):
        await pipeline_events.finish_analysis(1, vid, "✅ done", "auto")          # must not raise

    assert (await database.get_vacancy_by_id(vid))["status"] == "analyzed"


@pytest.mark.asyncio
async def test_the_failure_recorders_never_raise_from_an_except_branch(db_path):
    with patch.object(database, "set_analysis_error", AsyncMock(side_effect=RuntimeError("db down"))), \
         patch.object(database, "fail_generation", AsyncMock(side_effect=RuntimeError("db down"))):
        await pipeline_events.record_analysis_failure(1, 5, "auto", "x", "analysis_failed")
        await pipeline_events.record_generation_failure("cv", 1, 5, "auto", "x", "llm_error", "analyzed")


# the watcher's automatic analysis goes through the same helpers as the worker (origin "auto")

def _watcher():
    from core.rss_watcher import RSSWatcher
    deps = MagicMock()
    deps.user_id = 1
    settings = MagicMock()
    settings.analysis_mode = "full_auto"
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return RSSWatcher(deps=deps, telegram_bot=bot, poll_interval=999, concurrency=1, settings=settings)


@pytest.mark.asyncio
async def test_the_watchers_automatic_analysis_raises_its_events_through_the_router(db_path, _no_real_push):
    vid = await _vacancy("fetched", n=40)

    async def fetch(deps, url):
        return vid

    async def analyze(ctx, vacancy_id):
        await database.update_vacancy_status(vacancy_id, "analyzed")
        return "✅ done"

    with patch("tools.cv_fetch_jd.fetch_jd", fetch), patch("tools.cv_analyze.cv_analyze", analyze):
        await _watcher()._process("https://djinni.co/jobs/pe40")

    (event,) = await _events()
    assert (event["event"], event["origin"]) == ("analysis_done", "auto")
    _no_real_push.assert_awaited_once()                       # one push, from the router


@pytest.mark.asyncio
async def test_the_watchers_analysis_that_only_returns_a_warning_is_not_left_analyzing(db_path):
    vid = await _vacancy("fetched", n=41)

    async def fetch(deps, url):
        return vid

    async def analyze(ctx, vacancy_id):
        return "⚠️ Файл JD.md не найден:\n<code>x</code>"

    with patch("tools.cv_fetch_jd.fetch_jd", fetch), patch("tools.cv_analyze.cv_analyze", analyze):
        await _watcher()._process("https://djinni.co/jobs/pe41")

    assert (await database.get_vacancy_by_id(vid))["status"] == "analysis_failed"
    (event,) = await _events()
    assert (event["event"], event["code"], event["origin"]) == ("analysis_failed", "jd_missing", "auto")


@pytest.mark.asyncio
async def test_the_watchers_analysis_exception_is_recorded_with_its_event(db_path):
    vid = await _vacancy("fetched", n=42)

    async def fetch(deps, url):
        return vid

    async def analyze(ctx, vacancy_id):
        raise LLMError("provider down")

    with patch("tools.cv_fetch_jd.fetch_jd", fetch), patch("tools.cv_analyze.cv_analyze", analyze):
        await _watcher()._process("https://djinni.co/jobs/pe42")

    assert (await database.get_vacancy_by_id(vid))["status"] == "analysis_failed"
    (event,) = await _events()
    assert (event["event"], event["code"], event["origin"]) == ("analysis_failed", "llm_error", "auto")
