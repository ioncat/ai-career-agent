"""
agent.py — career-agent entry point.

Startup sequence:
1. Load Settings from env
2. Configure + initialise SQLite DB
3. Wire phase-aware LLM resolution (core.config_store.build_llm_client — each
   pipeline phase builds its own client per call, provider/model may differ per
   phase; see EPIC-27)
4. Build AgentDeps + workers (AnalysisWorker, CVWorker, CoverWorker)
5. Build TelegramBot (push notifications only — no incoming message routing)
6. Start RSS Watcher + workers + FastAPI; block on stop_event

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
from core import config_store
from core.deps import AgentDeps
from core.analysis_worker import AnalysisWorker
from core.cv_worker import CVWorker
from core.cover_worker import CoverWorker
from core.rss_watcher import RSSWatcher
from core.settings import ConfigError, load_settings
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
    await database.reset_stuck_statuses()  # must run before workers start

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

    # LLM client is now built fresh per phase call, not once at startup — see
    # core.config_store.build_llm_client (EPIC-27). config_store, not raw env
    # settings, is the source of truth for provider/model/effort (seeded from
    # env once, then DB-authoritative — see config_store.py's module docstring).
    async def _fresh_llm(phase: str) -> object:
        return await config_store.build_llm_client(phase, settings)

    log.info("LLM: phase-aware resolution via config_store (env-seeded provider=%s)", settings.llm_provider)

    # ── 4. Tools + deps ──────────────────────────────────────────────────────
    settings.vacancies_path.mkdir(parents=True, exist_ok=True)

    parser_adapter = ParserAdapter(base_url=settings.parser_url)
    cv_adapter = CVAdapter(pdf_service_url=settings.pdf_service_url)
    deps = AgentDeps(
        parser_adapter=parser_adapter,
        get_llm=_fresh_llm,
        vacancies_path=settings.vacancies_path,
        candidate_name=settings.candidate_name,
        cv_adapter=cv_adapter,
        user_id=default_user_id,
        skill_type=default_skill_type,
        profile=profile,
    )

    # ── 5. Telegram bot (push-only) ───────────────────────────────────────────
    bot = TelegramBot(
        token=settings.telegram_token,
        chat_id=settings.telegram_chat_id,
    )

    # ── 7. Workers + RSS Watcher ──────────────────────────────────────────────
    llm_sem = asyncio.Semaphore(settings.llm_concurrency)

    analysis_worker = AnalysisWorker(deps=deps, settings=settings, llm_sem=llm_sem)
    cv_worker = CVWorker(deps=deps, settings=settings, llm_sem=llm_sem)
    cover_worker = CoverWorker(deps=deps, settings=settings, llm_sem=llm_sem)

    watcher = RSSWatcher(
        deps=deps,
        telegram_bot=bot,
        poll_interval=settings.rss_poll_interval,
        concurrency=settings.rss_concurrency,
        settings=settings,
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
        _web_app.state.analysis_worker = analysis_worker
        _web_app.state.cv_worker = cv_worker
        _web_app.state.cover_worker = cover_worker
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

    await analysis_worker.start()
    await cv_worker.start()
    await cover_worker.start()
    await watcher.start()
    try:
        await stop_event.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        if _web_server is not None:
            _web_server.should_exit = True
        if _web_task is not None:
            await _web_task
        await watcher.stop()
        await cover_worker.stop()
        await cv_worker.stop()
        await analysis_worker.stop()
        await bot.stop()
        # No single shared LLM client left to summarize (EPIC-27 — each phase call
        # builds its own client). Per-call cost/usage is tracked in llm_usage (DB).
        log.info("career-agent stopped")


if __name__ == "__main__":
    asyncio.run(main())
