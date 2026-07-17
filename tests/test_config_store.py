"""
tests/test_config_store.py — core/config_store.py: single source of truth
for LLM provider/model/effort.

Covers the seed-once contract (env only matters on first read, ever), the
validation guard, and provider-switch model reset. Uses a real temp DB per
test (aiosqlite), no mocks — same pattern as tests/test_web_api.py.
"""

import pytest
import pytest_asyncio

from core import config_store
from db import database


@pytest_asyncio.fixture(autouse=True)
async def temp_db(tmp_path, monkeypatch):
    """Fresh DB + fresh config_store seed state per test.

    config_store's `_seeded` flag is process-wide, not DB-scoped — it must be
    reset alongside the DB, otherwise a provider seeded by an earlier test
    lingers and this test's env monkeypatches have no effect.
    """
    db_path = tmp_path / "test.db"
    database.configure(db_path)
    await database.init_db()
    await database.insert_user(name="U", telegram_chat_id=9001, skill_type="pm")
    monkeypatch.setenv("DB_PATH", str(db_path))
    config_store._seeded = False
    # core.settings calls load_dotenv() on import, which — if some other test
    # file imported it first — has already set the REAL LLM_PROVIDER env var
    # from the project's .env (not test-scoped, monkeypatch can't undo a load
    # that already happened). Tests here must not depend on env being unset;
    # delenv gives a deterministic baseline unless a test explicitly overrides it.
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    yield


# ── Seeding ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_seeds_provider_from_env_on_first_call(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "claude_cli")
    cfg = await config_store.get_config()
    assert cfg["provider"] == "claude_cli"
    # Persisted, not just returned in-memory — a later process restart sees it too
    row = await database.get_user_settings(1)
    assert row["llm_provider"] == "claude_cli"


@pytest.mark.asyncio
async def test_seed_only_happens_once_env_ignored_after(monkeypatch):
    """The whole point of the seam: after the first read, env is dead to us."""
    monkeypatch.setenv("LLM_PROVIDER", "claude_cli")
    first = await config_store.get_config()
    assert first["provider"] == "claude_cli"

    monkeypatch.setenv("LLM_PROVIDER", "ollama_api")  # env flips after seeding
    second = await config_store.get_config()
    assert second["provider"] == "claude_cli"  # unchanged — DB is now authoritative


@pytest.mark.asyncio
async def test_invalid_env_provider_falls_back_to_claude_api(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "not-a-real-provider")
    cfg = await config_store.get_config()
    assert cfg["provider"] == "claude_api"


@pytest.mark.asyncio
async def test_missing_env_provider_defaults_to_claude_api(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    cfg = await config_store.get_config()
    assert cfg["provider"] == "claude_api"


# ── set_config validation ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_config_rejects_invalid_provider():
    with pytest.raises(config_store.ConfigError):
        await config_store.set_config(provider="gpt5")


@pytest.mark.asyncio
async def test_set_config_rejects_invalid_effort():
    with pytest.raises(config_store.ConfigError):
        await config_store.set_config(thinking_effort="ultra")


@pytest.mark.asyncio
async def test_set_config_invalid_call_does_not_persist():
    """A rejected patch must not partially write — old values stay intact."""
    await config_store.set_config(provider="claude_api", thinking_effort="medium")
    with pytest.raises(config_store.ConfigError):
        await config_store.set_config(provider="gpt5")
    cfg = await config_store.get_config()
    assert cfg["provider"] == "claude_api"
    assert cfg["thinking_effort"] == "medium"


# ── set_config semantics ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_config_switch_resets_model():
    await config_store.set_config(provider="claude_api", model="claude-opus-4-5")
    cfg = await config_store.set_config(provider="ollama_api")
    assert cfg["provider"] == "ollama_api"
    assert cfg["model"] is None  # a Claude model name is meaningless for Ollama


@pytest.mark.asyncio
async def test_set_config_same_provider_keeps_model():
    await config_store.set_config(provider="claude_api", model="claude-opus-4-5")
    cfg = await config_store.set_config(thinking_effort="high")
    assert cfg["model"] == "claude-opus-4-5"  # untouched by an unrelated field patch
    assert cfg["thinking_effort"] == "high"


@pytest.mark.asyncio
async def test_set_config_provider_always_stored_explicitly():
    """No more 'NULL means env default' trick — DB always holds the real value."""
    await config_store.set_config(provider="claude_api")
    row = await database.get_user_settings(1)
    assert row["llm_provider"] == "claude_api"


# ── effective_model ──────────────────────────────────────────────────────────

def test_effective_model_db_override_wins():
    assert config_store.effective_model("claude_api", "claude-haiku-4-5") == "claude-haiku-4-5"


def test_effective_model_ollama_env_fallback(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
    assert config_store.effective_model("ollama_api", None) == "qwen3:8b"


def test_effective_model_claude_env_fallback(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-4-6")
    assert config_store.effective_model("claude_api", None) == "claude-sonnet-4-6"


# ── Per-phase config (EPIC-27) ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_config_phase_falls_back_to_global_when_unpinned():
    await config_store.set_config(provider="claude_api", thinking_effort="medium")
    cfg = await config_store.get_config("phase1")
    assert cfg["provider"] == "claude_api"
    assert cfg["thinking_effort"] == "medium"


@pytest.mark.asyncio
async def test_get_config_phase_pin_wins_over_global():
    await config_store.set_config(provider="claude_api")
    await config_store.set_phase_config("prefilter", provider="ollama_api", model="gemma3:2b")
    assert (await config_store.get_config("prefilter"))["provider"] == "ollama_api"
    # Unpinned phase is untouched by the other phase's pin
    assert (await config_store.get_config("phase1"))["provider"] == "claude_api"


@pytest.mark.asyncio
async def test_set_phase_config_first_pin_keeps_model_together_with_provider():
    """Regression: first-ever pin for a phase must not silently drop the model —
    provider_switched must mean 'changed FROM an existing pin', not 'created one'."""
    cfg = await config_store.set_phase_config("prefilter", provider="ollama_api", model="gemma3:2b")
    assert cfg == {"provider": "ollama_api", "model": "gemma3:2b", "thinking_effort": "off"}


@pytest.mark.asyncio
async def test_set_phase_config_real_switch_resets_model():
    await config_store.set_phase_config("prefilter", provider="ollama_api", model="gemma3:2b")
    cfg = await config_store.set_phase_config("prefilter", provider="claude_api")
    assert cfg["model"] is None


@pytest.mark.asyncio
async def test_set_phase_config_model_only_patch_keeps_provider():
    await config_store.set_phase_config("prefilter", provider="ollama_api", model="gemma3:2b")
    cfg = await config_store.set_phase_config("prefilter", model="llama3.2:3b")
    assert cfg["provider"] == "ollama_api"
    assert cfg["model"] == "llama3.2:3b"


@pytest.mark.asyncio
async def test_set_phase_config_rejects_unknown_phase():
    with pytest.raises(config_store.ConfigError):
        await config_store.set_phase_config("not_a_phase", provider="ollama_api")


@pytest.mark.asyncio
async def test_set_phase_config_rejects_invalid_provider():
    with pytest.raises(config_store.ConfigError):
        await config_store.set_phase_config("phase1", provider="gpt5")


@pytest.mark.asyncio
async def test_set_phase_config_rejects_invalid_effort():
    with pytest.raises(config_store.ConfigError):
        await config_store.set_phase_config("phase1", provider="claude_api", thinking_effort="ultra")


@pytest.mark.asyncio
async def test_set_phase_config_no_existing_pin_requires_provider():
    with pytest.raises(config_store.ConfigError):
        await config_store.set_phase_config("phase1", model="claude-opus-4-8")


@pytest.mark.asyncio
async def test_delete_phase_config_resets_to_global_default():
    await config_store.set_config(provider="claude_api")
    await config_store.set_phase_config("prefilter", provider="ollama_api", model="gemma3:2b")
    await config_store.delete_phase_config("prefilter")
    assert (await config_store.get_config("prefilter"))["provider"] == "claude_api"


@pytest.mark.asyncio
async def test_delete_phase_config_rejects_unknown_phase():
    with pytest.raises(config_store.ConfigError):
        await config_store.delete_phase_config("not_a_phase")


@pytest.mark.asyncio
async def test_get_resolved_phase_configs_marks_overrides_correctly():
    await config_store.set_config(provider="claude_api")
    await config_store.set_phase_config("prefilter", provider="ollama_api", model="gemma3:2b")
    resolved = await config_store.get_resolved_phase_configs()
    assert set(resolved.keys()) == set(config_store.VALID_PHASES)
    assert resolved["prefilter"]["is_override"] is True
    assert resolved["prefilter"]["provider"] == "ollama_api"
    assert resolved["phase1"]["is_override"] is False
    assert resolved["phase1"]["provider"] == "claude_api"


# ── _extract_critical_blockers — prefilter context trimming (2026-07-17) ─────
# Sending the full PROFILE.md (~6K tokens: Evidence, Archetype, Honest Gaps...)
# to the prefilter's small local model gave it unrelated facts to misapply as
# blockers (e.g. pulling an Honest Gaps line instead of a real Critical
# Blockers one). This extracts just the yaml block so prefilter only ever
# sees the ~10 lines it actually needs.

def test_extract_critical_blockers_pulls_only_yaml_lines():
    profile = """# Profile

## Some Other Section

Irrelevant content that must not leak into the extracted block.

## Critical Blockers

Some explanation prose here.

```yaml
english: C1 required (mine: B2)
location: must reside in EU (I'm in Ukraine)
```

## Honest Gaps

- No A/B testing experience
"""
    result = config_store._extract_critical_blockers(profile)
    assert result.startswith("## Critical Blockers")
    assert "english: C1 required (mine: B2)" in result
    assert "location: must reside in EU" in result
    assert "Irrelevant content" not in result
    assert "Honest Gaps" not in result
    assert "No A/B testing" not in result


def test_extract_critical_blockers_strips_comment_lines():
    profile = """## Critical Blockers

```yaml
# Uncomment and fill in real hard limits — comment line, not a blocker
english: C1 required (mine: B2)
```
"""
    result = config_store._extract_critical_blockers(profile)
    assert "# Uncomment" not in result
    assert "english: C1 required" in result


def test_extract_critical_blockers_missing_section_returns_none_marker():
    result = config_store._extract_critical_blockers("# Profile\n\nNo blockers section here.")
    assert result == "## Critical Blockers\n\n(none)"


def test_extract_critical_blockers_empty_yaml_returns_none_marker():
    profile = """## Critical Blockers

```yaml
# Uncomment and fill in real hard limits. Examples:
```
"""
    result = config_store._extract_critical_blockers(profile)
    assert result == "## Critical Blockers\n\n(none)"
