"""
tests/test_analyzed_at_backfill.py — scripts/analyzed_at_backfill.py (2026-10-06).

Restores "analyzed on" dates by writing `pipeline_runs` phase2 rows from the
JD_analysis.md file date. Per Rule 11 the important tests are the regression
ones: the backfill must leave every other table and column alone (a previous
backfill silently bumped updated_at on ~300 rows).
"""

import json
import os
import sqlite3
from pathlib import Path

import pytest
import pytest_asyncio

from db import database
from scripts import analyzed_at_backfill as bf

FIT = json.dumps({"p1": {"role": "PM"}, "p2": {"fit_score": 7, "recommendation": "apply"}})
NO_FIT = json.dumps({"p1": {"role": "PM"}})
# 2026-06-20 09:10:18 UTC
EPOCH = 1781946618


@pytest_asyncio.fixture
async def env(tmp_path):
    db_path = tmp_path / "test.db"
    database.configure(db_path)
    await database.init_db()
    uid = await database.insert_user("Test User")
    return {"tmp": tmp_path, "db": db_path, "uid": uid, "n": 0}


async def _add(env, *, analysis_json=FIT, with_file=True, with_path=True, run=False,
               mtime=EPOCH) -> int:
    env["n"] += 1
    n = env["n"]
    folder = env["tmp"] / f"v{n}"
    folder.mkdir()
    md = folder / "JD.md"
    md.write_text("jd", encoding="utf-8")
    vid = await database.insert_vacancy(
        url=f"https://example.org/jobs/{n}", title="Product Manager", company="Acme",
        markdown_path=str(md) if with_path else None, user_id=env["uid"],
    )
    con = sqlite3.connect(env["db"])
    con.execute("UPDATE vacancies SET analysis_json = ? WHERE id = ?", (analysis_json, vid))
    if run:
        con.execute(
            "INSERT INTO pipeline_runs (vacancy_id, phase, status, started_at, finished_at) "
            "VALUES (?, 'phase2', 'done', '2026-07-01 10:00:00', '2026-07-01 10:05:00')", (vid,))
    con.commit()
    con.close()
    if with_file:
        f = folder / "JD_analysis.md"
        f.write_text("analysis", encoding="utf-8")
        os.utime(f, (mtime, mtime))
    return vid


def _run(env, **kw):
    return bf.run(env["db"], root=env["tmp"], backup_dir=env["tmp"] / "backups", **kw)


# ── pure helpers ──────────────────────────────────────────────────────────────

def test_has_fit_score_shapes():
    assert bf.has_fit_score(FIT)
    assert bf.has_fit_score(json.dumps({"p2": {"fit_score": 0}}))   # 0 is a real score
    assert not bf.has_fit_score(NO_FIT)
    assert not bf.has_fit_score(json.dumps({"p2": {"recommendation": "apply"}}))
    assert not bf.has_fit_score("")
    assert not bf.has_fit_score(None)
    assert not bf.has_fit_score("not json")


def test_file_date_is_utc_regardless_of_machine_timezone(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("x")
    os.utime(f, (EPOCH, EPOCH))
    assert bf.file_date_utc(f) == "2026-06-20 09:10:18"


# ── plan ──────────────────────────────────────────────────────────────────────

async def test_plan_selects_only_analyzed_without_a_run(env):
    want = await _add(env)
    await _add(env, run=True)               # already has a real done run
    await _add(env, analysis_json=NO_FIT)   # never reached Phase 2
    no_file = await _add(env, with_file=False)
    no_path = await _add(env, with_path=False, with_file=False)
    inserts, skipped = bf.plan_inserts(bf.read_rows(env["db"]), env["tmp"])
    assert [i["vacancy_id"] for i in inserts] == [want]
    assert inserts[0]["finished_at"] == "2026-06-20 09:10:18"
    assert skipped == {"no_path": [no_path], "no_file": [no_file]}


async def test_result_path_is_relative_to_root(env):
    await _add(env)
    inserts, _ = bf.plan_inserts(bf.read_rows(env["db"]), env["tmp"])
    assert inserts[0]["result_path"] == str(Path("v1") / "JD_analysis.md")


# ── Rule 11 regression: nothing but the new pipeline_runs rows may change ─────

async def test_dry_run_leaves_the_live_db_untouched(env):
    await _add(env)
    await _add(env)
    before = env["tmp"] / "before.db"
    bf.snapshot(env["db"], before)
    res = _run(env, apply=False)
    assert len(res["inserts"]) == 2
    assert bf.diff_databases(before, env["db"]) == {}


async def test_dry_run_diff_reports_only_new_pipeline_runs_rows(env):
    await _add(env)
    await _add(env, run=True)
    res = _run(env, apply=False)
    assert list(res["diff"]) == ["pipeline_runs"]
    assert len(res["diff"]["pipeline_runs"]["added"]) == 1
    assert res["diff"]["pipeline_runs"]["changed"] == {}
    assert res["problems"] == []


async def test_apply_does_not_touch_vacancies_updated_at_or_any_other_column(env):
    vid = await _add(env)
    con = sqlite3.connect(env["db"])
    con.execute("UPDATE vacancies SET updated_at = '2026-01-01 00:00:00' WHERE id = ?", (vid,))
    con.commit()
    con.close()
    res = _run(env, apply=True)
    assert res["backup"].exists()
    assert list(res["diff"]) == ["pipeline_runs"]          # no vacancies/users/links changes
    con = sqlite3.connect(env["db"])
    assert con.execute("SELECT updated_at FROM vacancies WHERE id = ?", (vid,)).fetchone()[0] \
        == "2026-01-01 00:00:00"
    con.close()
    assert res["problems"] == []


async def test_apply_writes_a_marked_done_row_that_the_existing_reader_returns(env):
    vid = await _add(env)
    _run(env, apply=True)
    con = sqlite3.connect(env["db"])
    row = con.execute(
        "SELECT phase, status, started_at, finished_at, created_at, result_path "
        "FROM pipeline_runs WHERE vacancy_id = ?", (vid,)).fetchone()
    con.close()
    assert row == ("phase2", "done", None, "2026-06-20 09:10:18", "2026-06-20 09:10:18",
                   str(Path("v1") / "JD_analysis.md"))
    assert await database.get_last_phase_completion(vid, "phase2") == "2026-06-20 09:10:18"


async def test_rerun_after_apply_plans_nothing(env):
    await _add(env)
    _run(env, apply=True)
    res = bf.plan_inserts(bf.read_rows(env["db"]), env["tmp"])[0]
    assert res == []


async def test_backup_is_never_overwritten(env):
    await _add(env)
    _run(env, apply=True)
    with pytest.raises(FileExistsError):
        _run(env, apply=True)


def test_unexpected_changes_flags_a_touched_vacancies_column():
    diff = {
        "pipeline_runs": {"added": [1], "removed": [], "changed": {}},
        "vacancies": {"added": [], "removed": [], "changed": {7: ["updated_at"]}},
    }
    problems = bf.unexpected_changes(diff, expected_new_runs=1)
    assert problems == ["vacancies rowid 7: columns changed ['updated_at']"]


def test_unexpected_changes_flags_wrong_row_count():
    diff = {"pipeline_runs": {"added": [1, 2], "removed": [], "changed": {}}}
    assert bf.unexpected_changes(diff, 3) == ["pipeline_runs: 2 rows added, expected 3"]
    assert bf.unexpected_changes({}, 0) == []
