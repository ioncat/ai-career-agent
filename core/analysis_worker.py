"""
core/analysis_worker.py — Background worker for Phase 1+2 vacancy analysis.

Triggered immediately via enqueue() from API endpoints.
Uses a shared LLM semaphore to cap concurrent LLM calls across all workers.
"""

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass

from core import config_store
from core import failure_codes
from core.deps import AgentDeps
from core.generation_failure import analysis_failure_code, exception_reason
from core.pipeline_events import finish_analysis, record_analysis_failure
from core.settings import Settings
from db import database

log = logging.getLogger(__name__)


@dataclass
class _Ctx:
    deps: AgentDeps


class AnalysisWorker:
    """Immediate analysis queue — picks up vacancy_id, runs Phase 1+2."""

    def __init__(
        self,
        deps: AgentDeps,
        settings: Settings,
        llm_sem: asyncio.Semaphore,
    ) -> None:
        self._deps = deps
        self._settings = settings
        self._llm_sem = llm_sem
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._recovery_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="analysis-worker")
        self._recovery_task = asyncio.create_task(
            self._recover_queued(), name="analysis-worker-recovery"
        )
        log.info("AnalysisWorker: started")

    async def stop(self) -> None:
        for task in (self._task, self._recovery_task):
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        log.info("AnalysisWorker: stopped")

    async def enqueue(self, vacancy_id: int, origin: str = "auto") -> None:
        """Set status to 'analyzing' immediately, then queue for processing.

        `origin` is "user" when an API endpoint was hit from the app, "auto" for the recovery sweep
        and anything else the backend started on its own; it is carried into the events of this run.
        """
        await database.update_vacancy_status(vacancy_id, "analyzing")
        await self._queue.put((vacancy_id, origin))
        log.info("AnalysisWorker: enqueued v#%d origin=%s", vacancy_id, origin)

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _recover_queued(self) -> None:
        """On startup: re-enqueue any analysis_queued vacancies left from a prior crash/restart.

        DB init already resets stuck 'analyzing' → 'analysis_queued' before workers start,
        so this catches both mid-run crashes and clean restarts with pending work.
        """
        try:
            rows = await database.list_vacancies(
                status="analysis_queued", user_id=None, limit=50
            )
            for row in rows:
                vid = row["id"]
                log.info("AnalysisWorker: recovery — re-enqueuing v#%d", vid)
                await self.enqueue(vid)
        except Exception as exc:
            log.warning("AnalysisWorker: recovery scan failed: %s", exc)

    async def _run(self) -> None:
        while True:
            try:
                vacancy_id, origin = await asyncio.wait_for(self._queue.get(), timeout=300)
                asyncio.create_task(self._execute(vacancy_id, origin))
            except asyncio.TimeoutError:
                # Periodic sweep: pick up any analysis_queued vacancies missed by enqueue()
                # (e.g. set via standalone tracker fallback while agent.py wasn't serving)
                await self._recover_queued()

    _ANALYSIS_TIMEOUT = 600  # 10 minutes — covers slow claude CLI runs

    async def _execute(self, vacancy_id: int, origin: str = "auto") -> None:
        from tools.cv_analyze import cv_analyze

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
                result = await asyncio.wait_for(
                    cv_analyze(ctx, vacancy_id),  # type: ignore[arg-type]
                    timeout=self._ANALYSIS_TIMEOUT,
                )
            except asyncio.TimeoutError:
                log.error(
                    "AnalysisWorker: timeout v#%d (>%ds)", vacancy_id, self._ANALYSIS_TIMEOUT
                )
                await record_analysis_failure(
                    self._deps.user_id, vacancy_id, origin,
                    f"Analysis timed out after {self._ANALYSIS_TIMEOUT // 60} minutes",
                    failure_codes.LLM_TIMEOUT,
                )
            except Exception as exc:
                err_msg = exception_reason(exc)[:500]
                log.error("AnalysisWorker: failed v#%d: %s", vacancy_id, err_msg)
                await record_analysis_failure(
                    self._deps.user_id, vacancy_id, origin, err_msg, analysis_failure_code(exc),
                )
            else:
                await finish_analysis(self._deps.user_id, vacancy_id, result, origin)

    async def _fresh_llm(self, phase: str) -> object:
        """Build LLM provider for `phase` via core.config_store (single source of truth).

        Bound to AgentDeps.get_llm — cv_analyze() calls this once per sub-phase
        (phase1, phase2), each independently resolvable (EPIC-27).
        """
        return await config_store.build_llm_client(phase, self._settings)
