"""
tests/test_fetch_failed_backfill.py - scripts/fetch_failed_backfill.py

Moves only vacancies the fetch retry cap gave up on (declined + 'Fetch failed ...' error, no JD,
no analysis, not applied) to status 'fetch_failed'. Writes status and declined_at, nothing else.
"""

import sqlite3

import pytest
import pytest_asyncio

from db import database
from scripts import fetch_failed_backfill as script

GIVE_UP = "Fetch failed 5x — giving up: jd-parser unreachable"


@pytest_asyncio.fixture
async def db_path(tmp_path):
    path = tmp_path / "test.db"
    database.configure(path)
    await database.init_db()
    return path


async def _row(db_path, n, **cols):
    vid = await database.insert_vacancy(url=f"https://djinni.co/jobs/ffb{n}/", user_id=None)
    sets = {"status": "declined", "analysis_error": GIVE_UP, "updated_at": "2026-01-02 03:04:05", **cols}
    con = sqlite3.connect(db_path)
    con.execute("UPDATE vacancies SET " + ", ".join(f"{k} = ?" for k in sets) + " WHERE id = ?",
                (*sets.values(), vid))
    con.commit()
    con.close()
    return vid


def _get(db_path, vid):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        return dict(con.execute("SELECT * FROM vacancies WHERE id = ?", (vid,)).fetchone())
    finally:
        con.close()


@pytest.mark.asyncio
async def test_only_given_up_rows_without_jd_are_selected(db_path):
    target = await _row(db_path, 1)
    await _row(db_path, 2, analysis_error=None)                      # legacy imported, plain decline
    await _row(db_path, 3, markdown_path="vacancies/inbox/1/3/JD.md")  # a JD exists
    await _row(db_path, 4, analysis_json='{"p1": {}}')               # analysed
    await _row(db_path, 5, applied=1)                                # applied
    await _row(db_path, 6, status="fetched")                         # not declined
    await _row(db_path, 7, analysis_error="Analysis failed: timeout")  # a different error
    assert [r["id"] for r in script.read_rows(db_path)] == [target]


@pytest.mark.asyncio
async def test_dry_run_leaves_the_live_db_untouched(db_path):
    vid = await _row(db_path, 1)
    before = _get(db_path, vid)

    res = script.run(db_path, apply=False)

    assert _get(db_path, vid) == before
    assert res["problems"] == []
    assert res["diff"]["vacancies"]["changed"] == {vid: ["status"]}


@pytest.mark.asyncio
async def test_apply_backs_up_changes_status_and_declined_at_only(db_path, tmp_path):
    vid = await _row(db_path, 1, declined_at="2026-07-28 06:16:21")
    other = await _row(db_path, 2, analysis_error=None)
    before, before_other = _get(db_path, vid), _get(db_path, other)

    res = script.run(db_path, apply=True, backup_dir=tmp_path / "bk")

    assert res["problems"] == [] and res["backup"].exists()
    after = _get(db_path, vid)
    assert after["status"] == "fetch_failed" and after["declined_at"] is None
    assert {k: v for k, v in after.items() if k not in ("status", "declined_at")} == \
           {k: v for k, v in before.items() if k not in ("status", "declined_at")}   # updated_at kept
    assert _get(db_path, other) == before_other
    assert script.read_rows(db_path) == []                                            # re-run plans nothing
