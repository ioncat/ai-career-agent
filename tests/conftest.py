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
