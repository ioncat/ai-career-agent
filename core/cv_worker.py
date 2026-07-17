"""
core/cv_worker.py — Background worker for Phase 3+3.5 CV generation.

Triggered immediately via enqueue() from API endpoints.
Uses a shared LLM semaphore to cap concurrent LLM calls across all workers.
"""

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass

from core import config_store
from core.deps import AgentDeps
from core.settings import Settings
from db import database

log = logging.getLogger(__name__)


@dataclass
class _Ctx:
    deps: AgentDeps


class CVWorker:
    """Immediate CV generation queue — picks up vacancy_id, runs Phase 3+3.5."""

    def __init__(
        self,
        deps: AgentDeps,
        settings: Settings,
        llm_sem: asyncio.Semaphore,
    ) -> None:
        self._deps = deps
        self._settings = settings
        self._llm_sem = llm_sem
        self._queue: asyncio.Queue[tuple[int, str]] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="cv-worker")
        log.info("CVWorker: started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        log.info("CVWorker: stopped")

    async def enqueue(self, vacancy_id: int, language: str = "auto") -> None:
        """Set status to 'cv_generating' immediately, then queue for processing."""
        await database.update_vacancy_status(vacancy_id, "cv_generating")
        await self._queue.put((vacancy_id, language))
        log.info("CVWorker: enqueued v#%d language=%s", vacancy_id, language)

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _run(self) -> None:
        while True:
            vacancy_id, language = await self._queue.get()
            asyncio.create_task(self._execute(vacancy_id, language))

    async def _execute(self, vacancy_id: int, language: str) -> None:
        from tools.cv_generate import cv_generate

        async with self._llm_sem:
            try:
                fresh_deps = AgentDeps(
                    parser_adapter=self._deps.parser_adapter,
                    get_llm=self._fresh_llm,  # type: ignore[arg-type]
                    vacancies_path=self._deps.vacancies_path,
                    candidate_name=self._deps.candidate_name,
                    cv_adapter=self._deps.cv_adapter,
                    user_id=self._deps.user_id,
                    skill_type=self._deps.skill_type,
                    profile=self._deps.profile,
                )
                ctx = _Ctx(deps=fresh_deps)
                await cv_generate(ctx, vacancy_id, language=language)  # type: ignore[arg-type]
                log.info("CVWorker: done — v#%d", vacancy_id)
            except Exception as exc:
                err_msg = str(exc)[:500]
                log.error("CVWorker: failed v#%d: %s", vacancy_id, err_msg)
                await database.update_vacancy_status(vacancy_id, "analyzed")

    async def _fresh_llm(self, phase: str) -> object:
        """Build LLM provider for `phase` via core.config_store (single source of truth).

        Bound to AgentDeps.get_llm — cv_generate() calls this once per sub-phase
        (phase3, phase3_5), each independently resolvable (EPIC-27).
        """
        return await config_store.build_llm_client(phase, self._settings)
