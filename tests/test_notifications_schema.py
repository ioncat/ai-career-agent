"""
tests/test_notifications_schema.py - notifications phase 2: the schema step and what it enables.

Covers: db/database.py _migrate_notifications (rebuild of the old table, idempotent re-runs, nothing
else touched), insert_notification (severity, origin, code, idempotency key, system events),
prune_notifications (retention), notify() backward compatibility and the new options, and
GET /api/notifications with the new fields.
"""

import sqlite3
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from core.notifier import PipelineEvent, notify
from db import database

OLD_DDL = """
CREATE TABLE notifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    vacancy_id  INTEGER REFERENCES vacancies(id) ON DELETE SET NULL,
    event       TEXT    NOT NULL,
    title       TEXT    NOT NULL DEFAULT '',
    body        TEXT    NOT NULL DEFAULT '',
    read        INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
)
"""


@pytest_asyncio.fixture
async def db_path(tmp_path):
    path = tmp_path / "test.db"
    database.configure(path)
    await database.init_db()
    con = sqlite3.connect(path)
    con.execute("INSERT INTO users (id, telegram_chat_id, name) VALUES (1, 111, 'First')")
    con.execute("INSERT INTO users (id, telegram_chat_id, name) VALUES (2, 222, 'Second')")
    con.commit()
    con.close()
    return path


async def _vid(n):
    return await database.insert_vacancy(url=f"https://djinni.co/jobs/ns-{n}/")


def _con(path):
    return sqlite3.connect(path)


def _columns(path):
    con = _con(path)
    try:
        return {r[1]: r for r in con.execute("PRAGMA table_info(notifications)")}
    finally:
        con.close()


def _make_old_table(path, rows):
    """Put the table back into its pre-migration shape, with the given rows."""
    con = _con(path)
    con.execute("DROP INDEX IF EXISTS idx_notifications_key")
    con.execute("DROP TABLE notifications")
    con.execute(OLD_DDL)
    con.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications (user_id, created_at)")
    for r in rows:
        con.execute(
            "INSERT INTO notifications (id, user_id, vacancy_id, event, title, body, read, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", r)
    con.commit()
    con.close()


OLD_ROWS = [
    (1, 1, None, "analysis_done", "Analysis done", "fit 8", 1, "2026-10-01 10:00:00"),
    (2, 1, None, "cv_failed", "CV failed", "boom", 0, "2026-10-02 11:00:00"),
    (7, 1, None, "new_vacancy", "New", "", 0, "2026-10-03 12:00:00"),
]


# ── the table shape ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_fresh_database_has_the_new_shape(db_path):
    cols = _columns(db_path)

    assert {"severity", "origin", "code", "key"} <= set(cols)
    assert cols["user_id"][3] == 0                       # nullable: system events have no user
    assert cols["severity"][4] == "'info'" and cols["origin"][4] == "'auto'"


@pytest.mark.asyncio
async def test_the_old_table_is_rebuilt_with_every_row_kept(db_path):
    _make_old_table(db_path, OLD_ROWS)

    await database.init_db()

    cols = _columns(db_path)
    assert {"severity", "origin", "code", "key"} <= set(cols) and cols["user_id"][3] == 0
    con = _con(db_path)
    rows = con.execute(
        "SELECT id, user_id, event, title, body, read, created_at, severity, origin, code, key "
        "FROM notifications ORDER BY id").fetchall()
    con.close()
    assert rows == [
        (1, 1, "analysis_done", "Analysis done", "fit 8", 1, "2026-10-01 10:00:00", "success", "auto", None, None),
        (2, 1, "cv_failed", "CV failed", "boom", 0, "2026-10-02 11:00:00", "error", "auto", None, None),
        (7, 1, "new_vacancy", "New", "", 0, "2026-10-03 12:00:00", "info", "auto", None, None),
    ]


@pytest.mark.asyncio
async def test_new_rows_continue_after_the_highest_old_id(db_path):
    _make_old_table(db_path, OLD_ROWS)
    await database.init_db()

    new_id = await database.insert_notification(1, "analysis_done", title="t")

    assert new_id > 7


@pytest.mark.asyncio
async def test_rerunning_the_migration_changes_nothing(db_path):
    _make_old_table(db_path, OLD_ROWS)
    await database.init_db()
    con = _con(db_path)
    before = (con.execute("SELECT * FROM notifications ORDER BY id").fetchall(),
              con.execute("SELECT name, sql FROM sqlite_master WHERE tbl_name = 'notifications' ORDER BY name").fetchall())
    con.close()

    await database.init_db()
    await database.init_db()

    con = _con(db_path)
    after = (con.execute("SELECT * FROM notifications ORDER BY id").fetchall(),
             con.execute("SELECT name, sql FROM sqlite_master WHERE tbl_name = 'notifications' ORDER BY name").fetchall())
    con.close()
    assert after == before


@pytest.mark.asyncio
async def test_the_rebuild_touches_no_other_table(db_path):
    await database.insert_vacancy(url="https://djinni.co/jobs/ns1/")
    _make_old_table(db_path, OLD_ROWS)
    con = _con(db_path)
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT IN ('notifications', 'sqlite_sequence')")]
    before = {t: con.execute(f"SELECT * FROM {t}").fetchall() for t in tables}
    before_schema = con.execute(
        "SELECT name, sql FROM sqlite_master WHERE tbl_name != 'notifications' ORDER BY name").fetchall()
    con.close()

    await database.init_db()

    con = _con(db_path)
    assert {t: con.execute(f"SELECT * FROM {t}").fetchall() for t in tables} == before
    assert con.execute(
        "SELECT name, sql FROM sqlite_master WHERE tbl_name != 'notifications' ORDER BY name").fetchall() == before_schema
    con.close()


@pytest.mark.asyncio
async def test_a_failed_rebuild_leaves_the_old_table_in_place(db_path):
    _make_old_table(db_path, OLD_ROWS)
    # make the copy step fail: a leftover table with the temporary name and a conflicting definition cannot
    # be reused, so break the INSERT by pre-creating a view with the new table's name
    con = _con(db_path)
    con.execute("CREATE VIEW notifications_new AS SELECT 1")
    con.commit()
    con.close()

    with pytest.raises(Exception):
        await database.init_db()

    con = _con(db_path)
    assert con.execute("SELECT count(*) FROM notifications").fetchone()[0] == 3     # rows intact
    assert "severity" not in {r[1] for r in con.execute("PRAGMA table_info(notifications)")}
    con.close()


# ── the new fields on insert ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_severity_defaults_from_the_event_name_and_can_be_set(db_path):
    a = await database.insert_notification(1, "analysis_done")
    b = await database.insert_notification(1, "cv_failed")
    c = await database.insert_notification(1, "new_vacancy")
    d = await database.insert_notification(1, "feed_failing", severity="warning")

    rows = {r["id"]: r for r in await database.list_notifications(1)}
    assert [rows[i]["severity"] for i in (a, b, c, d)] == ["success", "error", "info", "warning"]


@pytest.mark.asyncio
async def test_origin_code_and_key_are_stored(db_path):
    vid = await _vid("a")
    nid = await database.insert_notification(
        1, "cv_failed", vid, "CV failed", "boom", origin="user", code="llm_error", key="cv:5:failed")

    row = next(r for r in await database.list_notifications(1) if r["id"] == nid)
    assert (row["origin"], row["code"], row["key"], row["vacancy_id"]) == ("user", "llm_error", "cv:5:failed", vid)


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", [{"severity": "fatal"}, {"origin": "robot"}, {"key": "k" * 201}])
async def test_invalid_values_are_rejected(db_path, kwargs):
    with pytest.raises(ValueError):
        await database.insert_notification(1, "cv_failed", **kwargs)


@pytest.mark.asyncio
async def test_the_same_key_for_the_same_user_is_stored_once(db_path):
    first = await database.insert_notification(1, "analysis_failed", key="analysis:5:failed")
    again = await database.insert_notification(1, "analysis_failed", key="analysis:5:failed")

    assert first is not None and again is None
    assert len(await database.list_notifications(1)) == 1


@pytest.mark.asyncio
async def test_the_same_key_for_another_user_or_no_key_is_allowed(db_path):
    assert await database.insert_notification(1, "analysis_failed", key="k") is not None
    assert await database.insert_notification(2, "analysis_failed", key="k") is not None
    assert await database.insert_notification(1, "analysis_failed") is not None        # no key: never deduplicated
    assert await database.insert_notification(1, "analysis_failed") is not None


@pytest.mark.asyncio
async def test_a_blank_key_is_the_same_as_no_key(db_path):
    assert await database.insert_notification(1, "cv_done", key="  ") is not None
    assert await database.insert_notification(1, "cv_done", key="") is not None


# ── system events (no user) ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_system_event_has_no_user_and_is_shown_to_every_user(db_path):
    sid = await database.insert_notification(
        None, "feed_failing", severity="warning", origin="system", key="monitor:djinni:failing")

    assert sid in [r["id"] for r in await database.list_notifications(1)]
    assert sid in [r["id"] for r in await database.list_notifications(2)]
    assert (await database.list_notifications(1))[0]["user_id"] is None


@pytest.mark.asyncio
async def test_system_events_are_deduplicated_among_themselves_only(db_path):
    assert await database.insert_notification(None, "feed_failing", key="monitor:djinni:failing") is not None
    assert await database.insert_notification(None, "feed_failing", key="monitor:djinni:failing") is None
    assert await database.insert_notification(1, "feed_failing", key="monitor:djinni:failing") is not None


@pytest.mark.asyncio
async def test_mark_all_read_also_marks_system_events(db_path):
    await database.insert_notification(1, "cv_done")
    await database.insert_notification(None, "feed_failing", severity="warning", origin="system")

    await database.mark_all_notifications_read(1)

    assert all(r["read"] == 1 for r in await database.list_notifications(1))


# ── retention ─────────────────────────────────────────────────────────────────

def _backdate(path, nid, days):
    con = _con(path)
    con.execute("UPDATE notifications SET created_at = datetime('now', ?) WHERE id = ?", (f"-{days} days", nid))
    con.commit()
    con.close()


@pytest.mark.asyncio
async def test_prune_deletes_events_older_than_the_age_cap(db_path):
    old = await database.insert_notification(1, "cv_done")
    fresh = await database.insert_notification(1, "cv_done")
    _backdate(db_path, old, 120)
    await database.mark_notification_read(old)                   # only READ events are removed by age

    deleted = await database.prune_notifications(max_age_days=90, max_rows=1000)

    assert deleted == 1
    assert [r["id"] for r in await database.list_notifications(1)] == [fresh]


@pytest.mark.asyncio
async def test_prune_keeps_only_the_newest_rows_over_the_count_cap(db_path):
    ids = [await database.insert_notification(1, "cv_done") for _ in range(7)]

    deleted = await database.prune_notifications(max_age_days=90, max_rows=3)

    assert deleted == 4
    assert sorted(r["id"] for r in await database.list_notifications(1)) == ids[-3:]


@pytest.mark.asyncio
async def test_the_documented_retention_caps_are_the_defaults(db_path):
    assert (database.NOTIFICATION_RETENTION_DAYS, database.NOTIFICATION_RETENTION_MAX_ROWS) == (90, 2000)
    old = await database.insert_notification(1, "cv_done")
    _backdate(db_path, old, 91)
    await database.mark_notification_read(old)

    assert await database.prune_notifications() == 1


@pytest.mark.asyncio
async def test_an_insert_that_lands_on_every_hundredth_id_runs_the_retention_pass(db_path):
    for _ in range(99):
        await database.insert_notification(1, "cv_done")

    with patch.object(database, "prune_notifications", AsyncMock(return_value=0)) as pruned:
        await database.insert_notification(1, "cv_done")             # id 100

    pruned.assert_awaited_once()


# ── notify(): the original signature still works, the new options are honoured ──

def _no_push():
    return patch("core.notifier._try_web_push", AsyncMock())


@pytest.mark.asyncio
async def test_notify_with_the_original_arguments_still_stores_the_event(db_path):
    vid = await _vid("b")
    with _no_push():
        await notify(1, PipelineEvent.ANALYSIS_DONE, vid, title="Analysis done", body="fit 8/10")
        await notify(1, PipelineEvent.CV_FAILED, title="CV failed")

    rows = {r["event"]: r for r in await database.list_notifications(1)}
    assert (rows["analysis_done"]["severity"], rows["analysis_done"]["origin"]) == ("success", "auto")
    assert rows["analysis_done"]["vacancy_id"] == vid and rows["analysis_done"]["body"] == "fit 8/10"
    assert rows["cv_failed"]["severity"] == "error"


@pytest.mark.asyncio
async def test_notify_passes_severity_origin_code_and_key_through(db_path):
    vid = await _vid("c")
    with _no_push():
        await notify(1, PipelineEvent.CV_FAILED, vid, title="t", severity="warning", origin="user",
                     code="llm_timeout", key="cv:5:failed")

    row = (await database.list_notifications(1))[0]
    assert (row["severity"], row["origin"], row["code"], row["key"]) == ("warning", "user", "llm_timeout", "cv:5:failed")


@pytest.mark.asyncio
async def test_notify_with_a_repeated_key_stores_and_pushes_once(db_path):
    vid = await _vid("d")
    with patch("core.notifier._try_web_push", AsyncMock()) as push:
        await notify(1, PipelineEvent.CV_FAILED, vid, title="t", key="cv:5:failed")
        await notify(1, PipelineEvent.CV_FAILED, vid, title="t", key="cv:5:failed")

    assert len(await database.list_notifications(1)) == 1
    assert push.await_count == 1


@pytest.mark.asyncio
async def test_notify_for_a_system_event_stores_it_and_sends_no_per_user_push(db_path):
    with patch("core.notifier._try_web_push", AsyncMock()) as push:
        await notify(None, PipelineEvent.ANALYSIS_FAILED, title="system", origin="system")

    assert (await database.list_notifications(1))[0]["user_id"] is None
    push.assert_not_awaited()


# ── the API ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_notifications_api_returns_the_new_fields_and_system_events(db_path, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from web.api import app

    monkeypatch.setenv("DB_PATH", str(db_path))                  # the app's startup reads its database from here
    monkeypatch.setenv("VACANCIES_PATH", str(tmp_path / "vacancies"))

    vid = await _vid("e")
    await database.insert_notification(1, "cv_failed", vid, "CV failed", "boom", origin="user", code="llm_error")
    await database.insert_notification(None, "feed_failing", title="feed", severity="warning", origin="system",
                                       key="monitor:x:failing")

    with TestClient(app) as client:
        items = client.get("/api/notifications", params={"user_id": 1}).json()

    by_event = {i["event"]: i for i in items}
    assert (by_event["cv_failed"]["severity"], by_event["cv_failed"]["origin"], by_event["cv_failed"]["code"]) == \
        ("error", "user", "llm_error")
    assert by_event["feed_failing"]["user_id"] is None and by_event["feed_failing"]["severity"] == "warning"


# ── review follow-up: errors are not "duplicates", retention policy, rollback ──

@pytest.mark.asyncio
async def test_a_not_null_violation_surfaces_instead_of_looking_like_a_duplicate(db_path):
    with pytest.raises(sqlite3.IntegrityError):
        await database.insert_notification(1, "cv_done", title=None)


@pytest.mark.asyncio
async def test_notify_with_a_bad_value_logs_a_failed_insert_not_a_duplicate(db_path, caplog):
    import logging
    caplog.set_level(logging.INFO, logger="core.notifier")

    with _no_push():
        await notify(1, PipelineEvent.CV_DONE, title=None)

    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "DB insert failed" in messages and "duplicate" not in messages


@pytest.mark.asyncio
async def test_an_unread_event_survives_the_age_rule_but_not_the_row_cap(db_path):
    unread_old = await database.insert_notification(1, "cv_failed")
    read_old = await database.insert_notification(1, "cv_done")
    _backdate(db_path, unread_old, 200)
    _backdate(db_path, read_old, 200)
    await database.mark_notification_read(read_old)

    assert await database.prune_notifications(max_age_days=90, max_rows=1000) == 1      # only the read one
    assert [r["id"] for r in await database.list_notifications(1)] == [unread_old]

    newer = [await database.insert_notification(1, "cv_done") for _ in range(3)]
    await database.prune_notifications(max_age_days=90, max_rows=3)                      # the cap covers unread too
    assert sorted(r["id"] for r in await database.list_notifications(1)) == newer


@pytest.mark.asyncio
async def test_a_failing_retention_pass_does_not_turn_a_saved_insert_into_a_failure(db_path, caplog):
    import logging
    caplog.set_level(logging.INFO)
    for _ in range(99):
        await database.insert_notification(1, "cv_done")

    with patch.object(database, "prune_notifications", AsyncMock(side_effect=RuntimeError("prune down"))):
        new_id = await database.insert_notification(1, "cv_done")                       # id 100

    assert new_id is not None
    assert "retention pass failed" in " ".join(r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_a_failure_before_the_transaction_keeps_its_own_error(db_path):
    import aiosqlite
    _make_old_table(db_path, OLD_ROWS)

    async with aiosqlite.connect(db_path) as db:
        db.executescript = AsyncMock(side_effect=RuntimeError("boom before BEGIN"))
        with pytest.raises(RuntimeError, match="boom before BEGIN"):
            await database._migrate_notifications(db)                 # not "no transaction is active"
