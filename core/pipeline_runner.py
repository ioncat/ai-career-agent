"""core/pipeline_runner.py — Orchestrated pipeline runner using FSM + notifier.

Three public functions: run_analyze, run_generate_cv, run_generate_cover.
Each follows the same pattern:
  1. fsm_transition → claim the in-progress state (raises FSMError on wrong pre-state)
  2. Call the tool (tool handles its own final status write on success)
  3. notify() success event
  On exception:
  4. Set error status / rollback status
  5. notify() failure event
  6. Re-raise so the caller (worker / API) can log and surface to user

Workers and API endpoints call these runners. Existing workers that bypass this
module remain valid during the migration — they will be refactored to thin wrappers
once pipeline_runner is proven stable (EPIC-21 C2 → C4 migration).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from core.deps import AgentDeps
from core.notifier import PipelineEvent, notify
from core.pipeline_fsm import FSMError, VacancyState, fsm_transition
from db import database

log = logging.getLogger(__name__)


@dataclass
class _Ctx:
    deps: AgentDeps


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _vacancy_title(vacancy_id: int) -> str:
    row = await database.get_vacancy_by_id(vacancy_id)
    if not row:
        return f"#{vacancy_id}"
    title = row["title"] or ""
    company = row["company"] or ""
    if title and company:
        return f"{company} — {title}"
    return title or company or f"#{vacancy_id}"


# ── Runners ───────────────────────────────────────────────────────────────────


async def run_analyze(deps: AgentDeps, vacancy_id: int) -> None:
    """Run Phase 1+2 analysis for vacancy_id.

    Pre-condition: vacancy must be in state 'analysis_queued'.
    Post-condition on success: vacancy status = 'analyzed'.
    Post-condition on failure: vacancy status = 'analysis_failed'.
    """
    await fsm_transition(vacancy_id, VacancyState.ANALYZING)
    try:
        from tools.cv_analyze import cv_analyze

        ctx = _Ctx(deps=deps)
        await cv_analyze(ctx, vacancy_id)  # type: ignore[arg-type]
        label = await _vacancy_title(vacancy_id)
        await notify(
            deps.user_id,
            PipelineEvent.ANALYSIS_DONE,
            vacancy_id,
            title=f"Analysis done — {label}",
        )
        log.info("pipeline_runner: analysis done v#%d", vacancy_id)
    except Exception as exc:
        err = str(exc)[:500]
        log.error("pipeline_runner: analysis failed v#%d: %s", vacancy_id, err)
        await database.set_analysis_error(vacancy_id, err)
        await notify(
            deps.user_id,
            PipelineEvent.ANALYSIS_FAILED,
            vacancy_id,
            title=f"Analysis failed — #{vacancy_id}",
            body=err,
        )
        raise


async def run_generate_cv(
    deps: AgentDeps,
    vacancy_id: int,
    language: str = "auto",
) -> None:
    """Run Phase 3+3.5 CV generation for vacancy_id.

    Pre-condition: vacancy must be in state 'cv_queued'.
    Post-condition on success: vacancy status = 'cv_generated'.
    Post-condition on failure: vacancy status rolled back to 'analyzed'.
    """
    await fsm_transition(vacancy_id, VacancyState.CV_GENERATING)
    try:
        from tools.cv_generate import cv_generate

        ctx = _Ctx(deps=deps)
        await cv_generate(ctx, vacancy_id, language=language)  # type: ignore[arg-type]
        label = await _vacancy_title(vacancy_id)
        await notify(
            deps.user_id,
            PipelineEvent.CV_DONE,
            vacancy_id,
            title=f"CV ready — {label}",
        )
        log.info("pipeline_runner: CV done v#%d", vacancy_id)
    except Exception as exc:
        err = str(exc)[:500]
        log.error("pipeline_runner: CV failed v#%d: %s", vacancy_id, err)
        await database.update_vacancy_status(vacancy_id, VacancyState.ANALYZED)
        await notify(
            deps.user_id,
            PipelineEvent.CV_FAILED,
            vacancy_id,
            title=f"CV failed — #{vacancy_id}",
            body=err,
        )
        raise

    # ── Phase 3.7: Editorial Audit (opt-in, best-effort, never blocks CV status) ──
    # Gate (apply + fit>=7) lives inside cv_editorial_audit itself — most vacancies
    # skip here for free (one DB read, no LLM call). Never raises past this point.
    await _run_editorial_audit_best_effort(deps, vacancy_id, target="cv")


async def run_generate_cover(deps: AgentDeps, vacancy_id: int) -> None:
    """Run Phase 4 cover letter generation for vacancy_id.

    Pre-condition: vacancy must be in state 'cv_generated'.
    Post-condition on success: vacancy status = 'cover_generated'.
    Post-condition on failure: vacancy status rolled back to 'cv_generated'.
    """
    await fsm_transition(vacancy_id, VacancyState.COVER_GENERATING)
    try:
        from tools.cv_cover import cv_cover

        ctx = _Ctx(deps=deps)
        await cv_cover(ctx, vacancy_id)  # type: ignore[arg-type]
        label = await _vacancy_title(vacancy_id)
        await notify(
            deps.user_id,
            PipelineEvent.COVER_DONE,
            vacancy_id,
            title=f"Cover ready — {label}",
        )
        log.info("pipeline_runner: cover done v#%d", vacancy_id)
    except Exception as exc:
        err = str(exc)[:500]
        log.error("pipeline_runner: cover failed v#%d: %s", vacancy_id, err)
        await database.update_vacancy_status(vacancy_id, VacancyState.CV_GENERATED)
        await notify(
            deps.user_id,
            PipelineEvent.COVER_FAILED,
            vacancy_id,
            title=f"Cover failed — #{vacancy_id}",
            body=err,
        )
        raise

    # ── Phase 3.7: Editorial Audit (opt-in, best-effort, never blocks cover status) ──
    await _run_editorial_audit_best_effort(deps, vacancy_id, target="cover")


async def _run_editorial_audit_best_effort(
    deps: AgentDeps, vacancy_id: int, target: str
) -> None:
    """Run Phase 3.7 editorial audit as a supplementary, non-blocking step.

    Called automatically after CV/Cover generation succeeds — this is what makes
    Phase 3.7 "opt-in" without needing a human to trigger it: the gate inside
    cv_editorial_audit (Phase 2 recommendation=apply, fit_score>=7) decides
    per-vacancy whether it actually runs. Most vacancies skip for free (a DB
    read, no LLM call) — only genuinely strong matches pay the extra cost.

    Deliberately does not affect vacancy status and never re-raises: a failure
    or a real LLM error here must not roll back or fail CV/Cover generation,
    which already succeeded and is independently usable.
    """
    try:
        from tools.cv_editorial_audit import _parse_analysis_json, cv_editorial_audit

        ctx = _Ctx(deps=deps)
        result = await cv_editorial_audit(ctx, vacancy_id, target=target)  # type: ignore[arg-type]

        if result.startswith("⚠️"):
            # Gate not met, or document not found yet — expected for most vacancies.
            log.info(
                "pipeline_runner: editorial audit (%s) skipped v#%d: %s",
                target, vacancy_id, result,
            )
            return

        label = await _vacancy_title(vacancy_id)
        vacancy = await database.get_vacancy_by_id(vacancy_id)
        scores = {}
        if vacancy:
            scores = _parse_analysis_json(vacancy).get(f"p3_7_{target}", {})
        body = ", ".join(f"{k}={v}/10" for k, v in scores.items()) if scores else ""

        await notify(
            deps.user_id,
            PipelineEvent.EDITORIAL_AUDIT_DONE,
            vacancy_id,
            title=f"Editorial audit ({target}) — {label}",
            body=body,
        )
        log.info("pipeline_runner: editorial audit (%s) done v#%d", target, vacancy_id)
    except Exception as exc:
        err = str(exc)[:500]
        log.warning(
            "pipeline_runner: editorial audit (%s) failed v#%d: %s",
            target, vacancy_id, err,
        )
        await notify(
            deps.user_id,
            PipelineEvent.EDITORIAL_AUDIT_FAILED,
            vacancy_id,
            title=f"Editorial audit ({target}) failed — #{vacancy_id}",
            body=err,
        )
