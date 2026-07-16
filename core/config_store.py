"""
core/config_store.py — single source of truth for runtime LLM config
(provider, model, thinking_effort).

Truth lives in the `user_settings` DB row (single-user today: user_id=1).
`.env` only SEEDS the provider on first run — after that, env is never
consulted again for provider selection. This module is the ONLY place that
knows where truth lives; every caller (API, workers, scripts) reads/writes
through it, never through os.getenv("LLM_PROVIDER") or raw database calls.

Why this matters (safety): a system that silently falls back between two
config sources ("DB if set, else env") cannot answer "who is authoritative
right now" without checking both — that ambiguity is the exact shape of bugs
like the CLI/API billing leak, where a call went to a provider nobody
explicitly chose. Seeding once and then trusting only the DB removes the
ambiguity for good.

Migrating to multi-user/SaaS later: swap the DB table for a per-tenant store
inside this module — callers (API routes, workers) never change.
"""

import logging
import os

from db import database

log = logging.getLogger(__name__)

VALID_PROVIDERS = {"claude_api", "ollama_api", "claude_cli"}
VALID_EFFORTS = {"off", "low", "medium", "high", "xhigh", "max"}

_USER_ID = 1  # single-user today; becomes per-request once multi-user lands

_seeded = False


class ConfigError(ValueError):
    """Invalid provider/effort value — callers map this to HTTP 422."""


async def _ensure_seeded() -> None:
    """On first call in this process, seed llm_provider from env if the DB has none.

    After this runs once, env is never read again for provider selection —
    the DB row is the only thing consulted, for the rest of the process
    lifetime and across restarts (the seed persists).
    """
    global _seeded
    if _seeded:
        return
    row = await database.get_user_settings(_USER_ID)
    if not row or not row.get("llm_provider"):
        env_provider = os.getenv("LLM_PROVIDER", "claude_api").lower()
        if env_provider not in VALID_PROVIDERS:
            log.warning("config_store: invalid LLM_PROVIDER env %r, seeding claude_api instead", env_provider)
            env_provider = "claude_api"
        await database.set_user_settings(
            _USER_ID,
            llm_provider=env_provider,
            llm_model=(row.get("llm_model") if row else None),
            thinking_effort=(row.get("thinking_effort") if row else None) or "off",
        )
        log.info("config_store: seeded llm_provider=%s from env (first run)", env_provider)
    _seeded = True


def _env_model_for(provider: str) -> str:
    """Env-configured default model for a provider, used when no DB model is set.

    This is a normal cascading default (per-provider, deterministic), not a
    truth-ambiguity — unlike provider selection, an unset model has exactly
    one well-defined fallback and never competes with a DB value.
    """
    if provider == "ollama_api":
        return os.getenv("OLLAMA_MODEL", "qwen2.5:32b")
    return os.getenv("LLM_MODEL", "claude-opus-4-5")


async def get_config() -> dict:
    """Return {provider, model, thinking_effort} — model is the raw DB value (may be None)."""
    await _ensure_seeded()
    row = await database.get_user_settings(_USER_ID) or {}
    return {
        "provider": row.get("llm_provider") or "claude_api",
        "model": row.get("llm_model"),
        "thinking_effort": row.get("thinking_effort") or "off",
    }


async def get_llm_provider() -> str:
    cfg = await get_config()
    return cfg["provider"]


def effective_model(provider: str, db_model: str | None) -> str:
    """Resolve the model actually used: DB override, else provider's env default."""
    return db_model or _env_model_for(provider)


async def set_config(
    *,
    provider: str | None = None,
    model: str | None = None,
    thinking_effort: str | None = None,
) -> dict:
    """Update config. Switching provider resets model to None (new provider's default).

    provider=None / thinking_effort=None means "leave unchanged". model=None
    when NOT switching provider also means "leave unchanged" — pass an empty
    string if you ever need to explicitly clear the model outside a switch
    (not currently exposed).
    Raises ConfigError on an invalid provider/effort value.
    """
    await _ensure_seeded()
    current = await get_config()

    new_provider = current["provider"]
    provider_switched = False
    if provider is not None:
        new_provider = provider.lower()
        if new_provider not in VALID_PROVIDERS:
            raise ConfigError(f"llm_provider must be one of {sorted(VALID_PROVIDERS)}")
        provider_switched = new_provider != current["provider"]

    new_effort = thinking_effort if thinking_effort is not None else current["thinking_effort"]
    if new_effort not in VALID_EFFORTS:
        raise ConfigError(f"thinking_effort must be one of {sorted(VALID_EFFORTS)}")

    if provider_switched:
        new_model = None  # a model of the old provider is invalid for the new one
    elif model is not None:
        new_model = model
    else:
        new_model = current["model"]

    await database.set_user_settings(
        _USER_ID, llm_provider=new_provider, llm_model=new_model, thinking_effort=new_effort
    )
    log.info("config_store: set provider=%s model=%s effort=%s", new_provider, new_model, new_effort)
    return {"provider": new_provider, "model": new_model, "thinking_effort": new_effort}
