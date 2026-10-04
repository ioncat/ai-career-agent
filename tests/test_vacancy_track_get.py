"""`vacancy_track.py get --field`: fetch one column without exposing prior analysis.

These tests call the command functions in-process with the DB path patched to a temp file.
They must NOT shell out to the script: it runs `load_dotenv(.env, override=True)`, so a
`DB_PATH` environment variable cannot redirect a subprocess away from the real database.
"""
from __future__ import annotations

import asyncio
import json
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
    original_path = vt.database._db_path
    asyncio.run(_init(db))
    con = sqlite3.connect(db)
    con.execute("INSERT INTO users (id, name) VALUES (1, 'test user')")
    con.commit()
    con.close()
    asyncio.run(vt.cmd_upsert(url="https://example.com/jobs/1", title="Product Manager", user_id=1, path=None))
    con = sqlite3.connect(db)
    vid = con.execute("SELECT id FROM vacancies").fetchone()[0]
    con.execute(
        "UPDATE vacancies SET markdown_path = ?, analysis_json = ? WHERE id = ?",
        ("vacancies/inbox/1/x/JD.md", json.dumps({"p1": {"role": "SECRET-OLD-ANALYSIS"}}), vid),
    )
    con.commit()
    con.close()
    yield db, vid
    vt.database.configure(original_path)


def test_field_prints_only_that_value(temp_db, capsys):
    _, vid = temp_db
    capsys.readouterr()
    asyncio.run(vt.cmd_get(vid, field="markdown_path"))
    out = capsys.readouterr().out
    assert out.strip() == "vacancies/inbox/1/x/JD.md"
    assert "SECRET-OLD-ANALYSIS" not in out


def test_full_record_still_includes_analysis(temp_db, capsys):
    _, vid = temp_db
    capsys.readouterr()
    asyncio.run(vt.cmd_get(vid))
    assert "SECRET-OLD-ANALYSIS" in capsys.readouterr().out


def test_unknown_field_exits_with_error(temp_db, capsys):
    _, vid = temp_db
    with pytest.raises(SystemExit) as exc:
        asyncio.run(vt.cmd_get(vid, field="no_such_column"))
    assert exc.value.code == 1
    assert "unknown field" in capsys.readouterr().err
