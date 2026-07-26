"""
tools/cv_editorial_audit.py — Phase 3.7: Editorial Audit (opt-in final polish).

Runs after Phase 3.6 (which isn't itself wired into the Python pipeline — this
tool doesn't depend on it). Not part of the automatic status-driven pipeline
(core/pipeline_runner.py) by design: this phase is opt-in, gated on a strong
fit outcome, and would break cost discipline if it ran for every vacancy.

Covers CV and Cover both — audited separately (one LLM call, one report, one
JD_analysis.md section per document), never merged into a single pass. Unlike
cv_generate.py's Phase 3/3.5, this tool never rewrites the audited file
directly — it appends the audit report to JD_analysis.md and returns it. The
caller (Telegram push, Flutter, or a Claude Code session) decides whether and
how to apply any findings; there is no interactive confirm loop here (Telegram
is push-only, per project convention — see CLAUDE.md).

Tool registered in agent.py via ToolRegistry.
Receives shared dependencies via RunContext[AgentDeps].
"""

import logging
import re
from pathlib import Path

from pydantic_ai import RunContext

from core.deps import AgentDeps
from core.llm_client import LLMError
from core.translit import safe_filename_stem
from db import database

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

_MIN_FIT_SCORE = 7
_QUALIFYING_RECOMMENDATION = "apply"

_DOC_TYPES = {"cv": "CV", "cover": "Cover"}


async def cv_editorial_audit(
    ctx: RunContext[AgentDeps],
    vacancy_id: int,
    target: str = "cv",
    force: bool = False,
) -> str:
    """Run the Phase 3.7 editorial audit against the saved CV and/or Cover.

    Gated by default on a strong-fit outcome (Phase 2 recommendation == 'apply'
    and fit_score >= 7) — this is a multi-pass, higher-cost audit not meant to
    run on every vacancy. Pass force=True to bypass the gate.

    Args:
        vacancy_id: DB id of the vacancy (must already have the target document(s)).
        target:     'cv' (default) | 'cover' | 'both'.
        force:      Skip the fit-score/recommendation gate.

    Returns:
        The audit report text (both reports concatenated if target='both').
        Full reports are also appended to JD_analysis.md, one section each.
    """
    log.info("cv_editorial_audit: vacancy_id=%d target=%s force=%s", vacancy_id, target, force)

    target = target.lower()
    if target not in ("cv", "cover", "both"):
        return f"⚠️ target должен быть 'cv' | 'cover' | 'both', получено: {target!r}"

    vacancy = await database.get_vacancy_by_id(vacancy_id)
    if not vacancy:
        return f"⚠️ Вакансия #{vacancy_id} не найдена в базе."

    markdown_path = vacancy["markdown_path"]
    jd_path = Path(markdown_path)
    if not jd_path.exists():
        return f"⚠️ Файл JD.md не найден:\n<code>{jd_path}</code>"

    analysis_path = jd_path.parent / "JD_analysis.md"
    if not analysis_path.exists():
        return f"⚠️ JD_analysis.md не найден для вакансии #{vacancy_id}."

    # ── Gate: only run for a strong-fit outcome, unless forced ───────────────
    analysis_json = _parse_analysis_json(vacancy)
    p2 = analysis_json.get("p2", {})
    fit_score = p2.get("fit_score")
    recommendation = p2.get("recommendation")

    if not force:
        qualifies = (
            recommendation == _QUALIFYING_RECOMMENDATION
            and isinstance(fit_score, (int, float))
            and fit_score >= _MIN_FIT_SCORE
        )
        if not qualifies:
            return (
                f"⚠️ Вакансия #{vacancy_id}: fit={fit_score}, rec={recommendation} — "
                f"не соответствует порогу editorial audit (apply, fit≥{_MIN_FIT_SCORE}).\n"
                f"Это дорогая многопроходная проверка — по умолчанию не гоняем на каждую "
                f"вакансию. Вызови ещё раз с force=True, если всё равно нужно."
            )

    targets = ["cv", "cover"] if target == "both" else [target]

    jd_text = jd_path.read_text(encoding="utf-8")
    analysis_text = analysis_path.read_text(encoding="utf-8")
    audience_blurb = _extract_quick_scan(analysis_text)

    skill_dir = _PROMPTS_DIR / ctx.deps.skill_type
    prompt_path = skill_dir / "phase3_7_editorial_audit.md"
    if not prompt_path.exists():
        return f"⚠️ Промпт не найден: <code>{prompt_path}</code>"
    phase37_prompt = prompt_path.read_text(encoding="utf-8")

    reports: list[str] = []

    for t in targets:
        label = _DOC_TYPES[t]
        doc_path = _latest_doc_path(jd_path.parent, ctx.deps.candidate_name, label)
        if doc_path is None:
            msg = f"⚠️ {label} не найден для вакансии #{vacancy_id} — пропускаю."
            log.warning("cv_editorial_audit: %s", msg)
            reports.append(msg)
            continue

        doc_text = doc_path.read_text(encoding="utf-8")
        user_msg = (
            f"Document under audit: {label}\n\n"
            f"{doc_text}\n\n"
            f"---\n\n"
            f"JD Text:\n\n{jd_text}\n\n"
            f"---\n\n"
            f"Audience context (from Phase 1 Quick Scan):\n\n{audience_blurb}"
        )

        run_id = await database.insert_pipeline_run(vacancy_id, phase=f"phase3_7_{t}")
        await database.update_pipeline_run(run_id, status="running")

        try:
            llm = await ctx.deps.get_llm("phase3_7")
            report = await llm.complete(user_msg, system=phase37_prompt)
            if u := llm.last_call_usage:
                await database.insert_llm_usage(
                    phase=f"phase3_7_{t}", vacancy_id=vacancy_id,
                    user_id=ctx.deps.user_id, **u
                )
        except LLMError as exc:
            await database.update_pipeline_run(run_id, status="error", error_message=str(exc))
            log.error("cv_editorial_audit: LLM error (%s): %s", label, exc)
            raise

        await database.update_pipeline_run(run_id, status="done")

        # ── Append to JD_analysis.md (never overwrite prior sections of same label) ──
        section_marker = f"\n\n---\n\n## Phase 3.7: Editorial Audit ({label})"
        current = analysis_path.read_text(encoding="utf-8")
        cutoff = current.find(section_marker)
        base = current[:cutoff] if cutoff != -1 else current
        analysis_path.write_text(
            base.rstrip() + f"{section_marker}\n\n{report}\n",
            encoding="utf-8",
        )

        scores = _extract_scores(report)
        if scores:
            await database.patch_analysis_json(vacancy_id, f"p3_7_{t}", scores)

        reports.append(f"### Editorial Audit — {label}\n\n{report}")

    return "\n\n---\n\n".join(reports)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_analysis_json(vacancy) -> dict:
    import json as _json
    raw = vacancy["analysis_json"] if "analysis_json" in vacancy.keys() else None
    if not raw:
        return {}
    try:
        return _json.loads(raw)
    except Exception:
        return {}


def _latest_doc_path(vacancy_dir: Path, candidate_name: str, doc_type: str) -> Path | None:
    """Find the highest-versioned {Name}_{doc_type}.md / _v2 / _v3... in the vacancy folder.

    doc_type: 'CV' or 'Cover'.
    """
    safe_name = safe_filename_stem(candidate_name)
    base = vacancy_dir / f"{safe_name}_{doc_type}.md"
    if not base.exists():
        return None
    latest = base
    n = 2
    while True:
        candidate = vacancy_dir / f"{safe_name}_{doc_type}_v{n}.md"
        if not candidate.exists():
            return latest
        latest = candidate
        n += 1


def _extract_quick_scan(analysis_text: str) -> str:
    """Pull just the '## Quick Scan' block — audience/archetype context, not the full analysis."""
    m = re.search(r"(?ms)^## Quick Scan\s*$(.*?)(?=^---|\Z)", analysis_text)
    return m.group(1).strip() if m else analysis_text[:500]


def _extract_scores(report: str) -> dict:
    """Best-effort extraction of the 6 Executive Summary scores (for analysis_json)."""
    fields = [
        "Naturalness", "Credibility", "Readability",
        "Lexical Variety", "Recruiter Confidence", "AI-likeness",
    ]
    scores: dict = {}
    for field in fields:
        m = re.search(rf"{re.escape(field)}[^\d]{{0,10}}(\d{{1,2}})\s*/\s*10", report)
        if m:
            scores[field.lower().replace(" ", "_")] = int(m.group(1))
    return scores
