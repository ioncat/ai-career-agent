"""
tests/test_settings.py — contract tests for core/settings.py + Chunk 3 default user seeding.

Run: python -m pytest tests/test_settings.py -v
"""

import os
import pytest
import pytest_asyncio

from db import database


@pytest_asyncio.fixture(autouse=True)
async def temp_db(tmp_path):
    """Fresh temp DB for each test."""
    database.configure(tmp_path / "test.db")
    await database.init_db()
    yield


# ── settings: DEFAULT_SKILL_TYPE env var ──────────────────────────────────────

def test_settings_default_skill_type_default(monkeypatch):
    """DEFAULT_SKILL_TYPE not set → defaults to 'pm'."""
    monkeypatch.delenv("DEFAULT_SKILL_TYPE", raising=False)
    # Reload settings with required vars set
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")

    from core.settings import load_settings
    s = load_settings()
    assert s.default_skill_type == "pm"


def test_settings_default_skill_type_override(monkeypatch):
    """DEFAULT_SKILL_TYPE=generic → settings.default_skill_type == 'generic'."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")
    monkeypatch.setenv("DEFAULT_SKILL_TYPE", "generic")

    from core.settings import load_settings
    s = load_settings()
    assert s.default_skill_type == "generic"


# ── settings: CANDIDATE_NAME / CANDIDATE_NAME_UK (2026-07-27) ─────────────────
# Language-aware candidate name — previously a single static CANDIDATE_NAME was
# used unconditionally regardless of CV language (found live, vacancy #844).

def test_settings_candidate_name_defaults(monkeypatch):
    monkeypatch.delenv("CANDIDATE_NAME", raising=False)
    monkeypatch.delenv("CANDIDATE_NAME_UK", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")

    from core.settings import load_settings
    s = load_settings()
    assert s.candidate_name == "Alex Bondarenko"
    assert s.candidate_name_uk == "Олексій Бондаренко"


def test_settings_candidate_name_uk_override(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")
    monkeypatch.setenv("CANDIDATE_NAME_UK", "Тест Тестенко")

    from core.settings import load_settings
    s = load_settings()
    assert s.candidate_name_uk == "Тест Тестенко"


# ── default user seeding (get_or_create_default_user) ─────────────────────────

@pytest.mark.asyncio
async def test_default_user_seeded_on_first_run():
    """get_or_create_default_user creates user with correct skill_type on first call."""
    uid = await database.get_or_create_default_user(
        telegram_chat_id=999001,
        name="Default User",
        skill_type="pm",
    )
    row = await database.get_user_by_id(uid)
    assert row is not None
    assert row["telegram_chat_id"] == 999001
    assert row["skill_type"] == "pm"
    assert row["name"] == "Default User"


@pytest.mark.asyncio
async def test_default_user_seeding_idempotent():
    """get_or_create_default_user returns same id on repeated calls — no duplicate rows."""
    uid1 = await database.get_or_create_default_user(
        telegram_chat_id=999002,
        name="Default User",
        skill_type="pm",
    )
    uid2 = await database.get_or_create_default_user(
        telegram_chat_id=999002,
        name="Default User",
        skill_type="pm",
    )
    assert uid1 == uid2

    users = await database.list_users()
    assert len(users) == 1  # no duplicate


@pytest.mark.asyncio
async def test_default_user_skill_type_read_from_db():
    """skill_type stored at seed time is readable back — simulates agent.py wiring."""
    uid = await database.get_or_create_default_user(
        telegram_chat_id=999003,
        name="Default User",
        skill_type="generic",
    )
    row = await database.get_user_by_id(uid)
    skill_type = row["skill_type"] if row else "pm"
    assert skill_type == "generic"
