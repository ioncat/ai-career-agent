"""
tests/test_since_filters.py - a client's `since` works in any ISO 8601 shape.

Stored timestamps are "YYYY-MM-DD HH:MM:SS" (UTC, written by SQLite) and were compared with `since` as plain
strings, so a client value with a "T" never matched a row of the same day (" " sorts before "T"): the Flutter
notification cursor never advanced and no event reached the app. Covers database.normalize_since, the two
filters that use it (vacancy list, notifications) and the API behavior for a bad value.
"""

import sqlite3

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from db import database

# one stored row per time: 09:59:59 (before), 10:00:00 (the boundary), 10:00:01 (after)
BEFORE, BOUNDARY, AFTER = "2026-10-09 09:59:59", "2026-10-09 10:00:00", "2026-10-09 10:00:01"


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


def _set(path, table, column, row_id, value):
    con = sqlite3.connect(path)
    con.execute(f"UPDATE {table} SET {column} = ? WHERE id = ?", (value, row_id))
    con.commit()
    con.close()


async def _notifications(path):
    ids = {}
    for label, stamp in (("before", BEFORE), ("boundary", BOUNDARY), ("after", AFTER)):
        nid = await database.insert_notification(1, "cv_done", title=label)
        _set(path, "notifications", "created_at", nid, stamp)
        ids[label] = nid
    return ids


async def _vacancies(path):
    ids = {}
    for n, (label, stamp) in enumerate((("before", BEFORE), ("boundary", BOUNDARY), ("after", AFTER))):
        vid = await database.insert_vacancy(url=f"https://djinni.co/jobs/since{n}/")
        _set(path, "vacancies", "updated_at", vid, stamp)
        ids[label] = vid
    return ids


# every shape of "10:00:00 UTC" a client might send, and what the filter should keep
SAME_INSTANT = [
    "2026-10-09 10:00:00",            # the stored form
    "2026-10-09T10:00:00",            # ISO with T, no zone (what the Flutter client sends)
    "2026-10-09T10:00:00Z",           # UTC marker
    "2026-10-09T10:00:00.000",        # fractional seconds, no zone (Dart toIso8601String)
    "2026-10-09T10:00:00.000Z",
    "2026-10-09T10:00:00.250000Z",    # microseconds
    "2026-10-09T13:00:00+03:00",      # an offset: the same instant
    "2026-10-09T05:00:00-05:00",
    " 2026-10-09T10:00:00 ",          # stray spaces
]


@pytest.mark.parametrize("since,expected", [
    ("2026-10-09T10:00:00", "2026-10-09 10:00:00"),
    ("2026-10-09T10:00:00Z", "2026-10-09 10:00:00"),
    ("2026-10-09T10:00:00.987654", "2026-10-09 10:00:00"),
    ("2026-10-09T13:00:00+03:00", "2026-10-09 10:00:00"),
    ("2026-10-09T23:30:00-02:00", "2026-10-10 01:30:00"),          # the offset can move the date
    ("2026-10-09", "2026-10-09 00:00:00"),
    ("2026-10-09 10:00:00", "2026-10-09 10:00:00"),
])
def test_normalize_since_gives_the_stored_form(since, expected):
    assert database.normalize_since(since) == expected


@pytest.mark.parametrize("bad", ["", "   ", "yesterday", "2026-13-45T00:00:00", "10:00", "2026-10-09T25:00:00"])
def test_normalize_since_rejects_what_is_not_a_datetime(bad):
    with pytest.raises(ValueError):
        database.normalize_since(bad)


@pytest.mark.asyncio
@pytest.mark.parametrize("since", SAME_INSTANT)
async def test_notifications_since_keeps_the_boundary_row_and_what_is_newer(db_path, since):
    ids = await _notifications(db_path)

    rows = await database.list_notifications(1, since=since)

    assert {r["id"] for r in rows} == {ids["boundary"], ids["after"]}            # the >= re-fetch of the boundary works


@pytest.mark.asyncio
@pytest.mark.parametrize("since", SAME_INSTANT)
async def test_vacancy_list_since_keeps_the_boundary_row_and_what_is_newer(db_path, since):
    ids = await _vacancies(db_path)

    rows = await database.list_vacancies(since=since)

    assert {r["id"] for r in rows} == {ids["boundary"], ids["after"]}


@pytest.mark.asyncio
async def test_a_later_row_of_the_same_day_is_not_dropped_by_a_t_separated_cursor(db_path):
    """The reported defect: ' ' < 'T', so a same-day row looked older than the cursor and nothing ever matched."""
    ids = await _notifications(db_path)

    rows = await database.list_notifications(1, since="2026-10-09T10:00:00.500")

    assert ids["after"] in {r["id"] for r in rows}


@pytest.mark.asyncio
async def test_a_cursor_just_after_the_boundary_excludes_it(db_path):
    ids = await _notifications(db_path)

    rows = await database.list_notifications(1, since="2026-10-09T10:00:01")

    assert {r["id"] for r in rows} == {ids["after"]}


@pytest.mark.asyncio
async def test_a_cursor_advancing_with_the_newest_row_never_loses_one(db_path):
    """Simulate the client: it sends back the newest created_at it saw, as ISO with T."""
    ids = await _notifications(db_path)
    seen = {r["id"] for r in await database.list_notifications(1)}
    cursor = max(r["created_at"] for r in await database.list_notifications(1)).replace(" ", "T")
    late = await database.insert_notification(1, "cv_done", title="late")
    _set(db_path, "notifications", "created_at", late, "2026-10-09 10:00:02")

    fresh = {r["id"] for r in await database.list_notifications(1, since=cursor)} - seen

    assert fresh == {late} and ids["after"] in seen


# ── the API ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def client(db_path, tmp_path, monkeypatch):
    from web.api import app
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("VACANCIES_PATH", str(tmp_path / "vacancies"))
    with TestClient(app) as c:
        yield c


@pytest.mark.asyncio
async def test_the_notifications_api_accepts_an_iso_cursor_with_t(client, db_path):
    ids = await _notifications(db_path)

    body = client.get("/api/notifications", params={"user_id": 1, "since": "2026-10-09T10:00:00.000"}).json()

    assert {n["id"] for n in body} == {ids["boundary"], ids["after"]}


@pytest.mark.asyncio
async def test_the_vacancy_list_api_accepts_an_iso_cursor_with_t(client, db_path):
    ids = await _vacancies(db_path)

    body = client.get("/api/vacancies", params={"since": "2026-10-09T10:00:00Z"}).json()

    assert {v["id"] for v in body} == {ids["boundary"], ids["after"]}


@pytest.mark.parametrize("path", ["/api/notifications", "/api/vacancies"])
def test_a_since_that_is_not_a_datetime_is_a_400_not_an_empty_answer(client, path):
    resp = client.get(path, params={"since": "yesterday"})

    assert resp.status_code == 400
    assert "since" in resp.json()["detail"].lower()


@pytest.mark.parametrize("path", ["/api/notifications", "/api/vacancies"])
def test_no_since_and_an_empty_since_mean_no_filter(client, path):
    assert client.get(path).status_code == 200
    assert client.get(path, params={"since": ""}).status_code == 200
