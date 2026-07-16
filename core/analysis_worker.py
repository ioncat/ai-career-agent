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
            try:
                vacancy_id = await asyncio.wait_for(self._queue.get(), timeout=300)
                asyncio.create_task(self._execute(vacancy_id))
            except asyncio.TimeoutError:
                # Periodic sweep: pick up any analysis_queued vacancies missed by enqueue()
                # (e.g. set via standalone tracker fallback while agent.py wasn't serving)
                await self._recover_queued()

    _ANALYSIS_TIMEOUT = 600  # 10 minutes — covers slow claude CLI runs

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
                await asyncio.wait_for(
                    cv_analyze(ctx, vacancy_id),  # type: ignore[arg-type]
                    timeout=self._ANALYSIS_TIMEOUT,
                )
                log.info("AnalysisWorker: done — v#%d", vacancy_id)
                await self._push_result(vacancy_id)
            except asyncio.TimeoutError:
                log.error(
                    "AnalysisWorker: timeout v#%d (>%ds)", vacancy_id, self._ANALYSIS_TIMEOUT
                )
                await database.set_analysis_error(
                    vacancy_id, f"Analysis timed out after {self._ANALYSIS_TIMEOUT // 60} minutes"
                )
            except Exception as exc:
                err_msg = str(exc)[:500]
                log.error("AnalysisWorker: failed v#%d: %s", vacancy_id, err_msg)
                await database.set_analysis_error(vacancy_id, err_msg)

    async def _fresh_llm(self) -> object:
        """Build LLM provider from core.config_store (single source of truth) on every call."""
        from core.llm_client import ClaudeCodeProvider, ClaudeProvider, OllamaProvider

        cfg = await config_store.get_config()
        provider_type = cfg["provider"]
        model = config_store.effective_model(provider_type, cfg["model"])
        effort = cfg["thinking_effort"]

        profile_md = ""
        if self._settings.profile_md_path.exists():
            profile_md = self._settings.profile_md_path.read_text(encoding="utf-8")

        log.info(
            "AnalysisWorker: building LLM — provider=%s model=%s effort=%s source=config_store",
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
                model=model,
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
