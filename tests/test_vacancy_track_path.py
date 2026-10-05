"""`vacancy_track.py update/upsert --path`: markdown_path must name JD.md, not a sibling artifact.

A JD_analysis.md path made Flutter show the analysis as the Job Description and
tagged the vacancy from the analysis text. Command functions run in-process with
the DB path patched to a temp file (see test_vacancy_track_get.py for why).
"""
from __future__ import annotations

import asyncio
import sqlite3

import pytest

from scripts import vacancy_track as vt


async def _init(db):
    vt.database.configure(db)
    await vt.database.init_db()


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    monkeypatch.setattr(vt, "_db_path", lambda: db)
    asyncio.run(_init(db))
    con = sqlite3.connect(db)
    con.execute("INSERT INTO users (id, name) VALUES (1, 'test user')")
    con.commit()
    con.close()
    asyncio.run(vt.cmd_upsert(url="https://example.com/jobs/1", title="Product Manager", user_id=1, path=None))
    return db


def _row(db):
    con = sqlite3.connect(db)
    try:
        return con.execute("SELECT id, markdown_path, tags FROM vacancies").fetchone()
    finally:
        con.close()


def test_jd_path_swaps_analysis_file_for_sibling_jd(tmp_path):
    (tmp_path / "JD.md").write_text("jd", encoding="utf-8")
    (tmp_path / "JD_analysis.md").write_text("analysis", encoding="utf-8")
    assert vt._jd_path(str(tmp_path / "JD_analysis.md")) == str(tmp_path / "JD.md")
    assert vt._jd_path(str(tmp_path / "JD.md")) == str(tmp_path / "JD.md")


def test_jd_path_keeps_path_when_no_sibling_jd(tmp_path):
    (tmp_path / "JD_analysis.md").write_text("analysis", encoding="utf-8")
    assert vt._jd_path(str(tmp_path / "JD_analysis.md")) == str(tmp_path / "JD_analysis.md")
    assert vt._jd_path(None) is None


def test_update_with_analysis_path_stores_jd_and_tags_from_jd_only(temp_db, tmp_path):
    (tmp_path / "JD.md").write_text("We build a telemedicine platform for patients and clinics.", encoding="utf-8")
    (tmp_path / "JD_analysis.md").write_text(
        "Analysis. Adjacent: igaming, casino, betting, fintech, banking payments, mobile app.", encoding="utf-8"
    )
    vid = _row(temp_db)[0]
    asyncio.run(vt.cmd_update(vid, "analyzed", str(tmp_path / "JD_analysis.md"), None, None))
    _, md_path, tags = _row(temp_db)
    assert md_path == str(tmp_path / "JD.md")
    for junk in ("igaming", "fintech", "mobile"):
        assert junk not in (tags or "")
