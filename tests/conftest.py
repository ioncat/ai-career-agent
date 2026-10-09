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
    """Default DB_PATH to a throwaway file for every test.

    The API's startup (web.api lifespan) opens DB_PATH, default `db/agent.db`, and runs init_db()
    with its schema migrations. A test that starts the app without pointing DB_PATH at its own
    database would migrate the real one (this happened once, on a table-rebuild migration). Tests
    that need a specific database still set DB_PATH themselves; this only closes the default.
    """
    monkeypatch.setenv("DB_PATH", str(tmp_path / "guard_default.db"))
