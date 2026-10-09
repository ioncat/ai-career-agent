"""
tests/test_live_db_guard.py - no test can reach the live database by default.

A schema migration once reached the real `db/agent.db` through a test that started the API without its
own DB_PATH, and the first version of the guard only set that env var, although db.database does not
read it (its module-level `_db_path` defaults to the live file). tests/conftest.py now patches both;
these tests prove it.
"""

import os
from pathlib import Path

import pytest

from db import database

LIVE_DB = Path(database._DEFAULT_DB_PATH)


def _stamp():
    if not LIVE_DB.exists():
        return None
    st = LIVE_DB.stat()
    return (st.st_mtime_ns, st.st_size)


def test_the_database_module_path_is_a_throwaway_file_not_the_live_one(tmp_path):
    assert database._db_path != LIVE_DB
    assert Path(database._db_path).resolve() != LIVE_DB.resolve()
    assert Path(database._db_path).parent == tmp_path


def test_the_env_var_points_at_a_throwaway_file_too(tmp_path):
    assert Path(os.environ["DB_PATH"]).parent == tmp_path


@pytest.mark.asyncio
async def test_a_direct_database_call_without_configure_lands_in_the_temp_file_only(tmp_path):
    before = _stamp()

    await database.init_db()                       # no configure(): the default path is the guard's file
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/guard-1/")
    await database.insert_notification(None, "cv_done", origin="system")

    assert (tmp_path / "guard_default.db").exists()
    assert (await database.get_vacancy_by_id(vid)) is not None                      # it is in the temp file
    assert _stamp() == before                      # the live database was not opened for writing
