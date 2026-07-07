"""
core/analysis_worker.py — Background worker for Phase 1+2 vacancy analysis.

Triggered immediately via enqueue() from API endpoints.
Uses a shared LLM semaphore to cap concurrent LLM calls across all workers.
"""

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass

from core.deps import AgentDeps
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

    async def enqueue(self, vacancy_id: int) -> None:
        """Set status to 'analyzing' immediately, then queue for processing."""
        await database.update_vacancy_status(vacancy_id, "analyzing")
        await self._queue.put(vacancy_id)
        log.info("AnalysisWorker: enqueued v#%d", vacancy_id)

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
            vacancy_id = await self._queue.get()
            asyncio.create_task(self._execute(vacancy_id))

    async def _execute(self, vacancy_id: int) -> None:
        from tools.cv_analyze import cv_analyze

        async with self._llm_sem:
            try:
                llm = await self._fresh_llm()
                fresh_deps = AgentDeps(
                    parser_adapter=self._deps.parser_adapter,
                    llm=llm,  # type: ignore[arg-type]
                    vacancies_path=self._deps.vacancies_path,
                    candidate_name=self._deps.candidate_name,
                    cv_adapter=self._deps.cv_adapter,
                    user_id=self._deps.user_id,
                    skill_type=self._deps.skill_type,
                    profile=self._deps.profile,
                )
                ctx = _Ctx(deps=fresh_deps)
                await cv_analyze(ctx, vacancy_id)  # type: ignore[arg-type]
                log.info("AnalysisWorker: done — v#%d", vacancy_id)
                await self._push_result(vacancy_id)
            except Exception as exc:
                err_msg = str(exc)[:500]
                log.error("AnalysisWorker: failed v#%d: %s", vacancy_id, err_msg)
                await database.set_analysis_error(vacancy_id, err_msg)

    async def _fresh_llm(self) -> object:
        """Build LLM provider from current user_settings DB row on every call."""
        from core.llm_client import ClaudeCodeProvider, ClaudeProvider, OllamaProvider

        db_row = await database.get_user_settings(self._deps.user_id)
        provider_type = self._settings.llm_provider

        model = (
            (db_row.get("llm_model") if db_row else None)
            or self._settings.llm_model
        )
        effort = (db_row.get("thinking_effort") if db_row else None) or "off"

        profile_md = ""
        if self._settings.profile_md_path.exists():
            profile_md = self._settings.profile_md_path.read_text(encoding="utf-8")

        log.info(
            "AnalysisWorker: building LLM — provider=%s model=%s effort=%s",
            provider_type, model, effort,
        )

        if provider_type == "claude_cli":
            return ClaudeCodeProvider(
                profile_md=profile_md,
                model=model,
                timeout=self._settings.claude_cli_timeout,
                effort=effort,
            )
        if provider_type == "ollama_api":
            return OllamaProvider(
                base_url=self._settings.ollama_base_url,
                model=self._settings.ollama_model,
                profile_md=profile_md,
                max_tokens=self._settings.max_tokens,
                timeout=self._settings.ollama_timeout,
            )
        return ClaudeProvider(
            api_key=self._settings.anthropic_api_key,
            model=model,
            profile_md=profile_md,
            max_tokens=self._settings.max_tokens,
        )

    async def _push_result(self, vacancy_id: int) -> None:
        from contracts.pipeline import AnalysisJson
        from core.push import send_push

        try:
            row = await database.get_vacancy_by_id(vacancy_id)
            if not row:
                return
            aj_str = row["analysis_json"] if "analysis_json" in row.keys() else None
            aj = AnalysisJson.model_validate_json(aj_str or "{}")
            if not aj.p2:
                return
            title = row["title"] or f"Vacancy #{vacancy_id}"
            await send_push(
                user_id=self._deps.user_id,
                title=f"✅ {title}",
                body=f"Fit {aj.p2.fit_score}/10 · {aj.p2.recommendation_label}",
            )
        except Exception as exc:
            log.warning("AnalysisWorker: push failed v#%d: %s", vacancy_id, exc)
