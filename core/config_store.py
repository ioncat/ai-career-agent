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
import re

from db import database

log = logging.getLogger(__name__)

VALID_PROVIDERS = {"claude_api", "ollama_api", "claude_cli"}
VALID_EFFORTS = {"off", "low", "medium", "high", "xhigh", "max"}

# EPIC-27: independently-routable pipeline phases. Ordered (pipeline order), not a set —
# iteration order matters for GET /api/config/phases responses.
VALID_PHASES = ("prefilter", "phase1", "phase2", "phase3", "phase3_5", "phase4")

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


async def get_config(phase: str | None = None) -> dict:
    """Return {provider, model, thinking_effort} — model is the raw DB value (may be None).

    phase=None (default): today's global behavior, unchanged.
    phase="phase1" etc: if that phase has an override (phase_llm_config), return it;
    otherwise fall through to the same global default. Unknown phase names are NOT
    validated here (read-only resolution) — invalid phase names are rejected by
    set_phase_config/delete_phase_config instead, where writing one would be a mistake
    worth catching loudly.
    """
    await _ensure_seeded()
    if phase is not None:
        override = await database.get_phase_llm_config(phase)
        if override is not None:
            return {
                "provider": override["provider"],
                "model": override["model"],
                "thinking_effort": override["thinking_effort"] or "off",
            }
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


async def set_phase_config(
    phase: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    thinking_effort: str | None = None,
) -> dict:
    """Create/update an override for one phase. Same provider-switch-resets-model
    semantics as set_config(). provider is required the first time an override is
    created for a phase (there's no "current" provider to fall back to yet).
    Raises ConfigError on an unknown phase or invalid provider/effort value.
    """
    if phase not in VALID_PHASES:
        raise ConfigError(f"unknown phase {phase!r}, must be one of {list(VALID_PHASES)}")

    current = await database.get_phase_llm_config(phase)

    new_provider = current["provider"] if current else None
    # provider_switched means "changing away from an already-pinned provider" —
    # NOT "creating a pin for the first time". On first creation there's no old
    # model to invalidate, so a caller setting provider+model together in one call
    # (the common UI action: pin a previously-unpinned phase) must not have its
    # model silently discarded.
    provider_switched = False
    if provider is not None:
        new_provider = provider.lower()
        if new_provider not in VALID_PROVIDERS:
            raise ConfigError(f"llm_provider must be one of {sorted(VALID_PROVIDERS)}")
        provider_switched = current is not None and new_provider != current["provider"]
    if new_provider is None:
        raise ConfigError(f"phase {phase!r} has no existing override — provider is required to create one")

    new_effort = thinking_effort if thinking_effort is not None else (current["thinking_effort"] if current else "off")
    if new_effort not in VALID_EFFORTS:
        raise ConfigError(f"thinking_effort must be one of {sorted(VALID_EFFORTS)}")

    if provider_switched:
        new_model = None
    elif model is not None:
        new_model = model
    else:
        new_model = current["model"] if current else None

    await database.set_phase_llm_config(phase, new_provider, new_model, new_effort)
    log.info(
        "config_store: set phase=%s provider=%s model=%s effort=%s",
        phase, new_provider, new_model, new_effort,
    )
    return {"provider": new_provider, "model": new_model, "thinking_effort": new_effort}


async def delete_phase_config(phase: str) -> None:
    """Remove a phase's override — it falls back to the global default on the next read."""
    if phase not in VALID_PHASES:
        raise ConfigError(f"unknown phase {phase!r}, must be one of {list(VALID_PHASES)}")
    await database.delete_phase_llm_config(phase)
    log.info("config_store: cleared override for phase=%s", phase)


async def get_resolved_phase_configs() -> dict[str, dict]:
    """Return every known phase with its resolved config (override or global fallback),
    plus is_override so callers can distinguish "explicitly pinned" from "following
    default" without a second lookup. Used by GET /api/config/phases.
    """
    global_cfg = await get_config()
    overrides = await database.list_phase_llm_configs()
    result: dict[str, dict] = {}
    for phase in VALID_PHASES:
        if phase in overrides:
            result[phase] = {**overrides[phase], "is_override": True}
        else:
            result[phase] = {**global_cfg, "is_override": False}
    return result


def _extract_critical_blockers(profile_md: str) -> str:
    """Pull just the '## Critical Blockers' yaml block out of PROFILE.md.

    The prefilter phase only ever needs this list — sending the full profile
    (Evidence/Archetype/Honest Gaps, ~6K tokens) gave a small local model
    unrelated facts to misapply as blockers (e.g. pulling an Honest Gaps line
    instead of a real Critical Blockers one — found 2026-07-17 testing
    gemma4:e2b). Keeps the '## Critical Blockers' heading itself so it matches
    the literal text prefilter.md's prompt tells the model to look for.
    """
    m = re.search(r"## Critical Blockers.*?```yaml\s*\n(.*?)```", profile_md, re.DOTALL)
    if not m:
        return "## Critical Blockers\n\n(none)"
    lines = [ln for ln in m.group(1).splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if not lines:
        return "## Critical Blockers\n\n(none)"
    return "## Critical Blockers\n\n" + "\n".join(lines) + "\n"


async def build_llm_client(phase: str | None, settings) -> object:
    """Build a live LLM provider instance for `phase` (or the global default when
    phase=None), resolving through get_config(phase).

    Centralizes what used to be duplicated identically in every worker's
    _fresh_llm() (AnalysisWorker, CVWorker, CoverWorker) — those methods now just
    delegate here with a phase name. `settings` is a core.settings.Settings
    instance, passed explicitly rather than imported (avoids import-time coupling;
    this module already owns config resolution, not settings loading).
    """
    from core.llm_client import ClaudeCodeProvider, ClaudeProvider, OllamaProvider

    cfg = await get_config(phase)
    provider_type = cfg["provider"]
    model = effective_model(provider_type, cfg["model"])
    effort = cfg["thinking_effort"]

    profile_md = ""
    if settings.profile_md_path.exists():
        profile_md = settings.profile_md_path.read_text(encoding="utf-8")
        if phase == "prefilter":
            profile_md = _extract_critical_blockers(profile_md)

    log.info(
        "config_store: building LLM — phase=%s provider=%s model=%s effort=%s",
        phase, provider_type, model, effort,
    )

    if provider_type == "claude_cli":
        return ClaudeCodeProvider(
            profile_md=profile_md,
            model=model,
            timeout=settings.claude_cli_timeout,
            effort=effort,
        )
    if provider_type == "ollama_api":
        # prefilter's real token budget is small (~280 system + JD + output) —
        # cap num_ctx instead of letting Ollama load the model's full declared
        # context (e.g. qwen3:8b defaults to 40960), which can overflow a 16GB
        # GPU's VRAM and force CPU offload (found 2026-07-17: 33.5min instead
        # of ~10-20s). Other phases keep Ollama's default (untested for this
        # specific issue, out of scope here).
        num_ctx = 4096 if phase == "prefilter" else None
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=model,
            profile_md=profile_md,
            max_tokens=settings.max_tokens,
            timeout=settings.ollama_timeout,
            effort=effort,
            num_ctx=num_ctx,
        )
    return ClaudeProvider(
        api_key=settings.anthropic_api_key,
        model=model,
        profile_md=profile_md,
        max_tokens=settings.max_tokens,
    )
