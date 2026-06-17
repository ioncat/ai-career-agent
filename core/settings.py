"""
core/settings.py — application config loaded from env vars.

Required vars: ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
Optional vars (have defaults): LLM_MODEL, DB_PATH, PARSER_URL,
                               CANDIDATE_NAME, PDF_SERVICE_URL, MULTI_USER_ENABLED
Deprecated (still functional as fallback): PROFILE_MD_PATH
  — EPIC-17: profile now loaded from DB (users.profile_json).
    PROFILE_MD_PATH is used only when DB profile is empty (new install / not yet onboarded).
    Will be removed after production rollout of Telegram onboarding.

Fails fast on startup if required vars are missing — never starts in broken state.

Usage:
    settings = load_settings()   # reads .env then env
    print(settings.llm_model)
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

# Load .env file if present (don't fail if absent — prod uses real env vars)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv optional; env vars may be set by Docker / shell


@dataclass(frozen=True)
class Settings:
    # ── Required ──────────────────────────────────────────────────────────────
    anthropic_api_key: str
    telegram_token: str
    telegram_chat_id: int

    # ── Optional with defaults ─────────────────────────────────────────────────
    llm_model: str = "claude-opus-4-5"
    profile_md_path: Path = field(default_factory=lambda: Path("../callback-cv/skill/PROFILE.md"))
    db_path: Path = field(default_factory=lambda: Path("db/agent.db"))
    parser_url: str = "http://localhost:8001"
    pdf_service_url: str = "http://localhost:8002"
    vacancies_path: Path = field(default_factory=lambda: Path("vacancies"))
    max_tokens: int = 4096
    candidate_name: str = "Candidate"
    seen_jobs_path: Path = field(default_factory=lambda: Path("seen_jobs.json"))
    rss_poll_interval: int = 60  # seconds between seen_jobs.json polls
    agent_mode: str = "production"  # "testing" → confirm before each LLM API call
    default_skill_type: str = "pm"  # skill_type for default user; overridable via DEFAULT_SKILL_TYPE
    # MULTI_USER_ENABLED=false (default): bot accepts only TELEGRAM_CHAT_ID — single-user mode.
    # Set to "true" to allow any Telegram user to onboard. Requires removing allowed_chat_id filter.
    # Known bottleneck at scale: profile_json single column, no concurrent write protection.
    # Production path: separate profiles table + proper auth. See docs/discovery/core-differentiators.md.
    multi_user_enabled: bool = False
    llm_provider: str = "claude"           # "claude" | "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:32b"


class ConfigError(Exception):
    """Raised on startup when required env vars are missing."""


def load_settings() -> Settings:
    """Load Settings from environment. Raises ConfigError on missing required vars."""
    missing: list[str] = []

    def _require(name: str) -> str:
        val = os.getenv(name, "").strip()
        if not val:
            missing.append(name)
        return val

    def _optional(name: str, default: str) -> str:
        return os.getenv(name, default).strip() or default

    api_key        = _require("ANTHROPIC_API_KEY")
    telegram_token = _require("TELEGRAM_BOT_TOKEN")
    chat_id_str    = _require("TELEGRAM_CHAT_ID")

    if missing:
        raise ConfigError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "Copy .env.example → .env and fill in the values."
        )

    try:
        chat_id = int(chat_id_str)
    except ValueError:
        raise ConfigError(f"TELEGRAM_CHAT_ID must be an integer, got: {chat_id_str!r}")

    return Settings(
        anthropic_api_key=api_key,
        telegram_token=telegram_token,
        telegram_chat_id=chat_id,
        llm_model=_optional("LLM_MODEL", "claude-opus-4-5"),
        profile_md_path=Path(_optional(
            "PROFILE_MD_PATH", "../callback-cv/skill/PROFILE.md"
        )),
        db_path=Path(_optional("DB_PATH", "db/agent.db")),
        parser_url=_optional("PARSER_URL", "http://localhost:8001"),
        pdf_service_url=_optional("PDF_SERVICE_URL", "http://localhost:8002"),
        vacancies_path=Path(_optional("VACANCIES_PATH", "vacancies")),
        max_tokens=int(_optional("MAX_TOKENS", "4096")),
        candidate_name=_optional("CANDIDATE_NAME", "Candidate"),
        seen_jobs_path=Path(_optional("SEEN_JOBS_PATH", "seen_jobs.json")),
        rss_poll_interval=int(_optional("RSS_POLL_INTERVAL", "60")),
        agent_mode=_optional("AGENT_MODE", "production"),
        default_skill_type=_optional("DEFAULT_SKILL_TYPE", "pm"),
        multi_user_enabled=_optional("MULTI_USER_ENABLED", "false").lower() == "true",
        llm_provider=_optional("LLM_PROVIDER", "claude"),
        ollama_base_url=_optional("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_model=_optional("OLLAMA_MODEL", "qwen2.5:32b"),
    )
