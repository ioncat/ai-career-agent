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


def test_applied_twin_prints_twin_id_and_folder(temp_db, capsys):
    db, vid = temp_db
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO vacancies (url, user_id, markdown_path, applied, applied_at, status) "
        "VALUES ('https://example.com/jobs/2', 1, 'vacancies/applied/1/x/JD.md', 1, '2026-01-01 10:00:00', 'analyzed')"
    )
    twin_id = con.execute("SELECT id FROM vacancies WHERE url = 'https://example.com/jobs/2'").fetchone()[0]
    con.execute("UPDATE vacancies SET duplicate_of = ? WHERE id = ?", (twin_id, vid))
    con.commit()
    con.close()
    capsys.readouterr()
    asyncio.run(vt.cmd_applied_twin(vid))
    out = json.loads(capsys.readouterr().out)
    assert out["id"] == vid
    assert out["applied_twin_id"] == twin_id
    assert out["twin_folder"].replace("\\", "/") == "vacancies/applied/1/x"


def test_applied_twin_null_when_none(temp_db, capsys):
    _, vid = temp_db
    capsys.readouterr()
    asyncio.run(vt.cmd_applied_twin(vid))
    out = json.loads(capsys.readouterr().out)
    assert out["applied_twin_id"] is None and out["twin_folder"] is None


def test_applied_twin_unknown_vacancy_exits_1(temp_db):
    with pytest.raises(SystemExit) as exc:
        asyncio.run(vt.cmd_applied_twin(99999))
    assert exc.value.code == 1
