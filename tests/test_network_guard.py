"""
tests/test_network_guard.py — unit tests for core/network_guard.py.
"""

import pytest

from core.network_guard import ExternalCallBlocked, guard_external


def test_guard_blocks_when_env_not_set(monkeypatch):
    monkeypatch.delenv("ALLOW_EXTERNAL_CALLS", raising=False)
    with pytest.raises(ExternalCallBlocked):
        guard_external()


def test_guard_blocks_when_env_false(monkeypatch):
    monkeypatch.setenv("ALLOW_EXTERNAL_CALLS", "false")
    with pytest.raises(ExternalCallBlocked):
        guard_external()


def test_guard_blocks_case_insensitive(monkeypatch):
    monkeypatch.setenv("ALLOW_EXTERNAL_CALLS", "FALSE")
    with pytest.raises(ExternalCallBlocked):
        guard_external()


def test_guard_passes_when_env_true(monkeypatch):
    monkeypatch.setenv("ALLOW_EXTERNAL_CALLS", "true")
    guard_external()  # must not raise


def test_guard_passes_case_insensitive(monkeypatch):
    monkeypatch.setenv("ALLOW_EXTERNAL_CALLS", "True")
    guard_external()  # must not raise


def test_guard_error_includes_label(monkeypatch):
    monkeypatch.delenv("ALLOW_EXTERNAL_CALLS", raising=False)
    with pytest.raises(ExternalCallBlocked, match="Claude API"):
        guard_external("Claude API")


def test_guard_error_includes_instructions(monkeypatch):
    monkeypatch.delenv("ALLOW_EXTERNAL_CALLS", raising=False)
    with pytest.raises(ExternalCallBlocked, match="ALLOW_EXTERNAL_CALLS=true"):
        guard_external()
