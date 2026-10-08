"""
tests/test_vacancy_paths.py - repair of `vacancies.markdown_path` after a hand-renamed folder
(core/vacancy_paths.py, scripts/fix_vacancy_paths.py, the startup hook in agent.py).

Rule under test: repair only when exactly one folder `inbox/<user_id>/{id} — *` holds a JD.md;
otherwise report and leave the row alone. Only `markdown_path` may change: `status` and
`updated_at` stay (the Analyzed folders sort by `updated_at`).
"""

import sqlite3
from pathlib import Path

import pytest
import pytest_asyncio

from core import vacancy_paths
from db import database
from scripts import fix_vacancy_paths as script


@pytest_asyncio.fixture
async def env(tmp_path):
    db_path = tmp_path / "test.db"
    database.configure(db_path)
    await database.init_db()
    root = tmp_path / "project"
    (root / "vacancies" / "inbox" / "1").mkdir(parents=True)
    return {"db": db_path, "root": root, "inbox": root / "vacancies" / "inbox" / "1"}


async def _vacancy(env, n, *, path_text, status="fetched"):
    vid = await database.insert_vacancy(url=f"https://djinni.co/jobs/vp{n}/", user_id=None)
    con = sqlite3.connect(env["db"])
    con.execute("UPDATE vacancies SET markdown_path = ?, status = ?, user_id = 1, "
                "updated_at = '2026-01-02 03:04:05' WHERE id = ?", (path_text, status, vid))
    con.commit()
    con.close()
    return vid


def _folder(env, name, *, jd=True):
    d = env["inbox"] / name
    d.mkdir()
    if jd:
        (d / "JD.md").write_text("# jd", encoding="utf-8")
    return d


def _row(env, vid):
    con = sqlite3.connect(env["db"])
    con.row_factory = sqlite3.Row
    try:
        return dict(con.execute("SELECT * FROM vacancies WHERE id = ?", (vid,)).fetchone())
    finally:
        con.close()


def _plan(env):
    rows = [{"id": r["id"], "user_id": r["user_id"], "markdown_path": r["markdown_path"]}
            for r in script.read_rows(env["db"])]
    return vacancy_paths.find_repairs(rows, env["root"] / "vacancies", env["root"])


# ── the planning rule ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_exactly_one_matching_folder_is_repaired(env):
    vid = await _vacancy(env, 1, path_text=r"vacancies\inbox\1\old name\JD.md")
    _folder(env, f"{vid} — AI Engineer — Acme")
    repairs, unresolved = _plan(env)
    assert [(r["id"], r["new"]) for r in repairs] == [(vid, f"vacancies\\inbox\\1\\{vid} — AI Engineer — Acme\\JD.md")]
    assert unresolved == []


@pytest.mark.asyncio
async def test_new_path_keeps_the_separator_style_of_the_old_one(env):
    vid = await _vacancy(env, 1, path_text="vacancies/inbox/1/old/JD.md")
    _folder(env, f"{vid} — AI Engineer — Acme")
    repairs, _ = _plan(env)
    assert repairs[0]["new"] == f"vacancies/inbox/1/{vid} — AI Engineer — Acme/JD.md"


@pytest.mark.asyncio
async def test_two_matching_folders_are_not_guessed(env):
    vid = await _vacancy(env, 1, path_text=r"vacancies\inbox\1\old\JD.md")
    _folder(env, f"{vid} — AI Engineer — Acme")
    _folder(env, f"{vid} — AI Engineer — Acme copy")
    repairs, unresolved = _plan(env)
    assert repairs == [] and [u["id"] for u in unresolved] == [vid]
    assert "2 folders" in unresolved[0]["reason"]


@pytest.mark.asyncio
async def test_no_matching_folder_is_reported_not_repaired(env):
    vid = await _vacancy(env, 1, path_text=r"vacancies\inbox\1\gone\JD.md")
    repairs, unresolved = _plan(env)
    assert repairs == [] and [u["id"] for u in unresolved] == [vid]


@pytest.mark.asyncio
async def test_folder_without_jd_md_is_not_a_repair(env):
    vid = await _vacancy(env, 1, path_text=r"vacancies\inbox\1\old\JD.md")
    _folder(env, f"{vid} — AI Engineer — Acme", jd=False)
    repairs, unresolved = _plan(env)
    assert repairs == [] and "no JD.md" in unresolved[0]["reason"]


@pytest.mark.asyncio
async def test_another_id_with_the_same_digits_prefix_does_not_match(env):
    vid = await _vacancy(env, 1, path_text=r"vacancies\inbox\1\old\JD.md")
    _folder(env, f"{vid}0 — Someone Else — Acme")          # id 10, 100 ... is not id 1
    repairs, unresolved = _plan(env)
    assert repairs == [] and [u["id"] for u in unresolved] == [vid]


@pytest.mark.asyncio
async def test_healthy_empty_and_null_paths_are_left_out(env):
    ok = _folder(env, "5 — Role — Co")
    await _vacancy(env, 1, path_text=str(ok / "JD.md"))     # absolute and existing
    await _vacancy(env, 2, path_text="")
    await _vacancy(env, 3, path_text=None)
    assert _plan(env) == ([], [])


# ── the startup hook ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_startup_repair_writes_only_markdown_path(env):
    fixed = await _vacancy(env, 1, path_text=r"vacancies\inbox\1\old\JD.md", status="analyzed")
    lost = await _vacancy(env, 2, path_text=r"vacancies\inbox\1\gone\JD.md", status="declined")
    _folder(env, f"{fixed} — AI Engineer — Acme")
    before_fixed, before_lost = _row(env, fixed), _row(env, lost)

    result = await vacancy_paths.repair_markdown_paths(Path("vacancies"), env["root"])

    assert [r["id"] for r in result["repaired"]] == [fixed]
    assert [u["id"] for u in result["unresolved"]] == [lost]
    after = _row(env, fixed)
    assert after["markdown_path"].endswith(f"{fixed} — AI Engineer — Acme\\JD.md")
    assert {k: v for k, v in after.items() if k != "markdown_path"} == \
           {k: v for k, v in before_fixed.items() if k != "markdown_path"}     # status, updated_at kept
    assert _row(env, lost) == before_lost


@pytest.mark.asyncio
async def test_startup_repair_is_idempotent(env):
    vid = await _vacancy(env, 1, path_text=r"vacancies\inbox\1\old\JD.md")
    _folder(env, f"{vid} — AI Engineer — Acme")
    await vacancy_paths.repair_markdown_paths(Path("vacancies"), env["root"])
    again = await vacancy_paths.repair_markdown_paths(Path("vacancies"), env["root"])
    assert again == {"repaired": [], "unresolved": []}


# ── the on-demand script: dry run, apply, backup ──────────────────────────────

@pytest.mark.asyncio
async def test_dry_run_leaves_the_live_db_untouched_and_diff_is_clean(env):
    vid = await _vacancy(env, 1, path_text=r"vacancies\inbox\1\old\JD.md")
    _folder(env, f"{vid} — AI Engineer — Acme")
    before = _row(env, vid)

    res = script.run(env["db"], apply=False, vacancies_root=env["root"] / "vacancies", project_root=env["root"])

    assert _row(env, vid) == before
    assert res["problems"] == []
    assert res["diff"]["vacancies"]["changed"] == {vid: ["markdown_path"]}


@pytest.mark.asyncio
async def test_apply_backs_up_writes_one_column_and_a_rerun_plans_nothing(env, tmp_path):
    vid = await _vacancy(env, 1, path_text=r"vacancies\inbox\1\old\JD.md", status="cv_generated")
    _folder(env, f"{vid} — AI Engineer — Acme")
    before = _row(env, vid)

    res = script.run(env["db"], apply=True, vacancies_root=env["root"] / "vacancies",
                     project_root=env["root"], backup_dir=tmp_path / "bk")

    assert res["problems"] == [] and res["backup"].exists()
    after = _row(env, vid)
    assert after["markdown_path"] != before["markdown_path"]
    assert {k: v for k, v in after.items() if k != "markdown_path"} == \
           {k: v for k, v in before.items() if k != "markdown_path"}
    again = script.run(env["db"], apply=False, vacancies_root=env["root"] / "vacancies", project_root=env["root"])
    assert again["repairs"] == [] and again["problems"] == []
