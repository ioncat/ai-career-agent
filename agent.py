"""
agent.py — career-agent entry point.

Startup sequence:
1. Load Settings from env
2. Configure + initialise SQLite DB
3. Build ClaudeProvider (loads PROFILE.md for prompt caching)
4. Build ToolRegistry + register domain tools
5. Build Router (PydanticAI Agent)
6. Build TelegramBot (with FSM onboarding + MULTI_USER_ENABLED flag)
7. Start long polling (blocks until Ctrl-C or SIGTERM)

Run:
    python agent.py
"""

import asyncio
import logging
import logging.handlers
import signal
import sys
from pathlib import Path

import uvicorn

from adapters.cv_adapter import CVAdapter
from adapters.parser_adapter import ParserAdapter
from core.deps import AgentDeps
from core.rss_watcher import RSSWatcher
from core.settings import ConfigError, load_settings
from core.llm_client import ClaudeProvider, OllamaProvider, ClaudeCodeProvider
from core.tool_registry import ToolRegistry
from core.router import Router
from core.telegram import TelegramBot
from db import database

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_LOG_DATE_FMT = "%Y-%m-%d %H:%M:%S"
_LOG_DIR = Path("logs")


def _configure_logging() -> None:
    """Set up root logger: StreamHandler (terminal) + RotatingFileHandler (file).

    Logs go to both stdout and logs/agent.log simultaneously.
    File rotates at 5 MB, keeps 5 backups — ~25 MB total max.
    """
    _LOG_DIR.mkdir(exist_ok=True)
    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE_FMT)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_DIR / "agent.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(stream_handler)
    root.addHandler(file_handler)


_configure_logging()
log = logging.getLogger("agent")


def _register_tools(registry: ToolRegistry, llm: ClaudeProvider) -> None:
    """Register all domain tools.

    Tools are imported here to avoid circular imports.
    Each EPIC (7–11) adds its tools in this function.
    """
    from tools.cv_fetch_jd import cv_fetch_jd
    registry.register(cv_fetch_jd)

    from tools.cv_analyze import cv_analyze
    registry.register(cv_analyze)

    from tools.cv_generate import cv_generate
    registry.register(cv_generate)

    from tools.cv_cover import cv_cover
    registry.register(cv_cover)

    from tools.cv_get_tracker import cv_get_tracker
    registry.register(cv_get_tracker)

    log.info("ToolRegistry: %d tools registered — %s", len(registry), registry.names())


async def main() -> None:
    # ── 1. Config ─────────────────────────────────────────────────────────────
    try:
        settings = load_settings()
    except ConfigError as exc:
        log.error("Config error: %s", exc)
        sys.exit(1)

    log.info("Settings loaded — model=%s chat_id=%d", settings.llm_model, settings.telegram_chat_id)

    # ── 2. Database ───────────────────────────────────────────────────────────
    database.configure(settings.db_path)
    await database.init_db()

    # Seed default user from TELEGRAM_CHAT_ID on first run; returns existing id on subsequent runs.
    default_user_id = await database.get_or_create_default_user(
        telegram_chat_id=settings.telegram_chat_id,
        name="Default User",
        skill_type=settings.default_skill_type,
    )
    default_user_row = await database.get_user_by_id(default_user_id)
    default_skill_type = default_user_row["skill_type"] if default_user_row else settings.default_skill_type
    log.info("Default user: id=%d skill_type=%s", default_user_id, default_skill_type)

    # ── 3. LLM client ─────────────────────────────────────────────────────────
    # Load full PROFILE.md from file — authoritative LLM system prompt (PROFILE.md > DB).
    # Also parse CandidateProfile (structured fields) and store in users.profile_json
    # so the auto-pipeline can access domain_interests without reading the file.
    from core.profile_loader import parse_profile_md as _parse_profile

    if settings.profile_md_path.exists():
        profile_md = settings.profile_md_path.read_text(encoding="utf-8")
        log.info("Profile loaded from %s (%d chars)", settings.profile_md_path, len(profile_md))
        profile = _parse_profile(profile_md)
        await database.update_user_profile(
            default_user_id, profile.model_dump_json()
        )
        log.info(
            "CandidateProfile stored in DB — user_id=%d skill_type=%s domains=%d",
            default_user_id, profile.skill_type, len(profile.domain_interests),
        )
    else:
        log.warning(
            "PROFILE.md not found at %s — pipeline will run with degraded profile",
            settings.profile_md_path,
        )
        profile_md = "# Candidate Profile\n\n_Profile not found._"
        profile = None

    if settings.llm_provider == "claude_cli":
        llm = ClaudeCodeProvider(
            profile_md=profile_md,
            model=settings.llm_model,
            timeout=settings.claude_cli_timeout,
        )
        log.info("LLM provider: claude_cli — model=%s (subscription, $0 cost)", settings.llm_model)
    elif settings.llm_provider == "ollama_api":
        llm = OllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            profile_md=profile_md,
            max_tokens=settings.max_tokens,
            timeout=settings.ollama_timeout,
        )
        log.info("LLM provider: ollama_api — model=%s base_url=%s", settings.ollama_model, settings.ollama_base_url)
    else:  # claude_api (default)
        llm = ClaudeProvider(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model,
            profile_md=profile_md,
            max_tokens=settings.max_tokens,
            testing_mode=(settings.agent_mode == "testing"),
        )
        if settings.agent_mode == "testing":
            log.warning("AGENT_MODE=testing — Claude API calls require confirmation before each request")
        log.info("LLM provider: Claude — model=%s", settings.llm_model)

    # ── 4. Tools + deps ──────────────────────────────────────────────────────
    settings.vacancies_path.mkdir(parents=True, exist_ok=True)

    parser_adapter = ParserAdapter(base_url=settings.parser_url)
    cv_adapter = CVAdapter(pdf_service_url=settings.pdf_service_url)
    deps = AgentDeps(
        parser_adapter=parser_adapter,
        llm=llm,
        vacancies_path=settings.vacancies_path,
        candidate_name=settings.candidate_name,
        cv_adapter=cv_adapter,
        user_id=default_user_id,
        skill_type=default_skill_type,
        profile=profile,
    )

    registry = ToolRegistry()
    _register_tools(registry, llm)

    # ── 5. Router ─────────────────────────────────────────────────────────────
    router = Router(
        api_key=settings.anthropic_api_key,
        model=settings.llm_model,
        registry=registry,
        deps=deps,
    )

    # ── 6. Telegram bot ───────────────────────────────────────────────────────
    bot = TelegramBot(
        token=settings.telegram_token,
        allowed_chat_id=settings.telegram_chat_id,
        on_message=router.handle,
        multi_user_enabled=settings.multi_user_enabled,
        default_user_id=default_user_id,
    )

    # ── 7. RSS Watcher ────────────────────────────────────────────────────────
    watcher = RSSWatcher(
        deps=deps,
        telegram_bot=bot,
        poll_interval=settings.rss_poll_interval,
        concurrency=settings.rss_concurrency,
    )

    # ── 8. Web tracker (FastAPI) ──────────────────────────────────────────────
    import socket as _socket
    _web_server = None
    _web_task = None
    _probe = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    try:
        _probe.bind(("127.0.0.1", settings.web_port))
        _probe.close()
        from web.api import app as _web_app  # import after database.configure()
        _web_cfg = uvicorn.Config(
            _web_app,
            host="127.0.0.1",
            port=settings.web_port,
            log_level="warning",
        )
        _web_server = uvicorn.Server(_web_cfg)
        _web_task = asyncio.create_task(_web_server.serve())
        log.info("Web tracker started on http://127.0.0.1:%d", settings.web_port)
    except OSError:
        _probe.close()
        log.warning(
            "Port %d already in use — web tracker running externally, skipping embedded start",
            settings.web_port,
        )

    # ── 9. Run ────────────────────────────────────────────────────────────────
    log.info(
        "career-agent starting — rss_poll=%ds",
        settings.rss_poll_interval,
    )

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _handle_signal() -> None:
        log.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            pass  # Windows — signals handled via KeyboardInterrupt

    await watcher.start()
    try:
        await bot.start()
    except KeyboardInterrupt:
        pass
    finally:
        if _web_server is not None:
            _web_server.should_exit = True
        if _web_task is not None:
            await _web_task
        await watcher.stop()
        await bot.stop()
        llm.log_session_summary()
        log.info("career-agent stopped")


if __name__ == "__main__":
    asyncio.run(main())
