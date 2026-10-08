"""
tests/test_recommendation_backfill.py — scripts/recommendation_backfill.py.

Normalizes non-canonical `p2.recommendation` values in `vacancies.analysis_json`.
The important tests are the regression ones from the bulk-data rule: only that one
value changes, `updated_at` and every other column and table stay as they were
(the normal setter `patch_analysis_json` bumps `updated_at`, which would reorder
the Analyzed folders), a dry run leaves the live DB untouched, a re-run does nothing.
"""

import json
import sqlite3

import pytest
import pytest_asyncio

from db import database
from scripts import recommendation_backfill as bf


def _doc(rec, **extra):
    return json.dumps({"p1": {"role": "PM"}, "p2": {"fit_score": 5, "recommendation": rec, **extra}},
                      ensure_ascii=False)


@pytest_asyncio.fixture
async def env(tmp_path):
    db_path = tmp_path / "test.db"
    database.configure(db_path)
    await database.init_db()
    return {"db": db_path, "tmp": tmp_path}


async def _add(env, n, analysis_json):
    vid = await database.insert_vacancy(url=f"https://djinni.co/jobs/rb{n}/")
    con = sqlite3.connect(env["db"])
    con.execute("UPDATE vacancies SET analysis_json = ?, updated_at = '2026-01-02 03:04:05' WHERE id = ?",
                (analysis_json, vid))
    con.commit()
    con.close()
    return vid


def _row(env, vid):
    con = sqlite3.connect(env["db"])
    con.row_factory = sqlite3.Row
    try:
        return dict(con.execute("SELECT * FROM vacancies WHERE id = ?", (vid,)).fetchone())
    finally:
        con.close()


# ── pure helpers ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    ("take a chance", "take_a_chance"),
    ("Take A Chance", "take_a_chance"),
    ("take-a-chance", "take_a_chance"),
    ("skip", "decline"),
    ("apply", None),            # already canonical
    ("take_a_chance", None),    # already canonical
    ("maybe later", None),      # unknown: needs a human
    (None, None),
])
def test_canonical_for(value, expected):
    assert bf.canonical_for(value) == expected


def test_substitute_changes_only_the_value():
    text = _doc("take a chance", why_apply=["strong delivery"])
    new = bf.substitute(text, "take a chance", "take_a_chance")
    assert new == text.replace('"take a chance"', '"take_a_chance"')


def test_substitute_refuses_a_pair_that_is_not_unique():
    text = json.dumps({"p2": {"recommendation": "skip"}, "p3": {"recommendation": "skip"}})
    assert bf.substitute(text, "skip", "decline") is None


def test_plan_ignores_canonical_missing_and_broken_documents():
    rows = [
        {"id": 1, "status": "analyzed", "applied": 0, "analysis_json": _doc("apply")},
        {"id": 2, "status": "analyzed", "applied": 0, "analysis_json": json.dumps({"p1": {}})},
        {"id": 3, "status": "analyzed", "applied": 0, "analysis_json": "{not json"},
        {"id": 4, "status": "analyzed", "applied": 1, "analysis_json": _doc("take a chance")},
        {"id": 5, "status": "declined", "applied": 0, "analysis_json": _doc("maybe later")},
    ]
    updates, unmapped = bf.plan_updates(rows)
    assert [(u["id"], u["new"]) for u in updates] == [(4, "take_a_chance")]
    assert [u["id"] for u in unmapped] == [5]


# ── database behaviour ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dry_run_leaves_the_live_db_untouched_and_is_clean(env):
    vid = await _add(env, 1, _doc("take a chance"))
    before = _row(env, vid)

    res = bf.run(env["db"], apply=False)

    assert _row(env, vid) == before
    assert res["problems"] == []
    assert [u["id"] for u in res["updates"]] == [vid]
    assert res["diff"]["vacancies"]["changed"] == {vid: ["analysis_json"]}


@pytest.mark.asyncio
async def test_apply_writes_only_analysis_json_and_keeps_updated_at(env):
    changed = await _add(env, 1, _doc("take a chance", why_apply=["x"]))
    skip = await _add(env, 2, _doc("skip"))
    other = await _add(env, 3, _doc("apply"))
    before = {v: _row(env, v) for v in (changed, skip, other)}

    res = bf.run(env["db"], apply=True, backup_dir=env["tmp"] / "bk")

    assert res["problems"] == []
    assert res["backup"].exists()
    for vid, rec in ((changed, "take_a_chance"), (skip, "decline"), (other, "apply")):
        after = _row(env, vid)
        assert json.loads(after["analysis_json"])["p2"]["recommendation"] == rec
        assert after["updated_at"] == before[vid]["updated_at"]
        assert {k: v for k, v in after.items() if k != "analysis_json"} ==                {k: v for k, v in before[vid].items() if k != "analysis_json"}
    assert json.loads(_row(env, changed)["analysis_json"])["p2"]["why_apply"] == ["x"]
    assert _row(env, other)["analysis_json"] == before[other]["analysis_json"]


@pytest.mark.asyncio
async def test_rerun_after_apply_plans_nothing(env):
    await _add(env, 1, _doc("take a chance"))
    bf.run(env["db"], apply=True, backup_dir=env["tmp"] / "bk")

    res = bf.run(env["db"], apply=False)

    assert res["updates"] == []
    assert res["problems"] == []


@pytest.mark.asyncio
async def test_existing_backup_is_never_overwritten(env, tmp_path):
    from scripts.analyzed_at_backfill import snapshot
    target = tmp_path / "bk.db"
    snapshot(env["db"], target)
    with pytest.raises(FileExistsError):
        snapshot(env["db"], target)
