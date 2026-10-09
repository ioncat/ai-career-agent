"""
tests/conftest.py — shared pytest fixtures.

Sets ALLOW_EXTERNAL_CALLS=true for all tests so ClaudeProvider.complete()
does not raise ExternalCallBlocked. The actual Anthropic client is always
mocked — no real network calls happen in tests.
"""

import pytest


@pytest.fixture(autouse=True)
def allow_external_in_tests(monkeypatch):
    monkeypatch.setenv("ALLOW_EXTERNAL_CALLS", "true")


@pytest.fixture(autouse=True)
def never_touch_the_live_database(monkeypatch, tmp_path):
    """Point both database paths at a throwaway file for every test.

    Two things can open the real `db/agent.db`: the API's startup (web.api lifespan reads the env var
    DB_PATH, default `db/agent.db`, and runs init_db() with its schema migrations) and any direct
    `database.*` call in a test that never called `database.configure()` (db.database does not read
    DB_PATH: its module-level `_db_path` defaults to the live file). A table-rebuild migration once
    reached the live database this way. Tests that need a specific database still set DB_PATH or call
    configure() themselves; this only closes the default, and monkeypatch restores both afterwards.
    """
    from db import database

    guard = tmp_path / "guard_default.db"
    monkeypatch.setenv("DB_PATH", str(guard))
    monkeypatch.setattr(database, "_db_path", guard)
