"""
core/cover_worker.py — Background worker for Phase 4 cover letter generation.

Triggered immediately via enqueue() from API endpoints.
Uses a shared LLM semaphore to cap concurrent LLM calls across all workers.
"""

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass

from core import config_store
from core.deps import AgentDeps
from core.generation_failure import exception_code, exception_reason, soft_failure
from core.pipeline_events import emit_done, record_generation_failure
from core.settings import Settings
from db import database

log = logging.getLogger(__name__)


@dataclass
class _Ctx:
    deps: AgentDeps


class CoverWorker:
    """Immediate cover generation queue — picks up vacancy_id, runs Phase 4."""

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
        self._task = asyncio.create_task(self._run(), name="cover-worker")
        log.info("CoverWorker: started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        log.info("CoverWorker: stopped")

    async def enqueue(self, vacancy_id: int, origin: str = "auto") -> None:
        """Set status to 'cover_generating' immediately, then queue for processing.

        `origin` is "user" when an API endpoint was hit from the app, "auto" otherwise.
        """
        await database.update_vacancy_status(vacancy_id, "cover_generating")
        await self._queue.put((vacancy_id, origin))
        log.info("CoverWorker: enqueued v#%d origin=%s", vacancy_id, origin)

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _run(self) -> None:
        while True:
            vacancy_id, origin = await self._queue.get()
            asyncio.create_task(self._execute(vacancy_id, origin))

    async def _execute(self, vacancy_id: int, origin: str = "auto") -> None:
        from tools.cv_cover import cv_cover

        async with self._llm_sem:
            try:
                fresh_deps = AgentDeps(
                    parser_adapter=self._deps.parser_adapter,
                    get_llm=self._fresh_llm,  # type: ignore[arg-type]
                    vacancies_path=self._deps.vacancies_path,
                    cv_adapter=self._deps.cv_adapter,
                    user_id=self._deps.user_id,
                    skill_type=self._deps.skill_type,
                    profile=self._deps.profile,
                )
                ctx = _Ctx(deps=fresh_deps)
                result = await cv_cover(ctx, vacancy_id)  # type: ignore[arg-type]
                if (failure := soft_failure(result)) is not None:
                    raise failure
                log.info("CoverWorker: done — v#%d", vacancy_id)
            except Exception as exc:
                err_msg = exception_reason(exc)[:500]
                log.error("CoverWorker: failed v#%d: %s", vacancy_id, err_msg)
                # Rollback, the failure on the vacancy and its event: one transaction (core/pipeline_events.py).
                await record_generation_failure(
                    "cover", self._deps.user_id, vacancy_id, origin, err_msg, exception_code(exc),
                    "cv_generated",
                )
            else:
                await emit_done("cover", self._deps.user_id, vacancy_id, origin)

    async def _fresh_llm(self, phase: str) -> object:
        """Build LLM provider for `phase` via core.config_store (single source of truth).

        Bound to AgentDeps.get_llm — cv_cover() calls this once for phase4 (EPIC-27).
        """
        return await config_store.build_llm_client(phase, self._settings)
