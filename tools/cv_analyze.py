"""
tools/cv_analyze.py — CV pipeline Phase 1+2 analysis.

Pipeline step 1: JD.md → Phase 1 (JD analysis) → Phase 2 (fit assessment) → JD_analysis.md.

Flow:
    1. Load vacancy from DB by ID.
    2. Read JD.md from disk.
    3. Phase 1: LLM call with phase1_analysis.md prompt → structural JD analysis.
    4. Phase 2: LLM call with phase2_fit.md prompt + Phase 1 output → fit + Quick Scan.
    5. Extract Quick Scan block from Phase 2 output.
    6. Write JD_analysis.md to vacancy folder (Quick Scan at top).
    7. Update vacancy status to "analyzed".
    8. Return Quick Scan block for Telegram.

Tool registered in agent.py via ToolRegistry.
Receives shared dependencies via RunContext[AgentDeps].
"""

import logging
import re
import time
from datetime import datetime
from pathlib import Path

from pydantic_ai import RunContext

from contracts.pipeline import (
    AnalysisJson,
    FitDimensions,
    Phase1Data,
    Phase2Data,
    VacScoreDims,
)
from core.deps import AgentDeps
from core.llm_client import LLMError
from core.vacscore import compute_recommendation, compute_vacancy_score
from db import database

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


async def cv_analyze(ctx: RunContext[AgentDeps], vacancy_id: int) -> str:
    """Run Phase 1+2 analysis on a fetched vacancy and save JD_analysis.md.

    Reads JD.md from the vacancy folder, calls Claude with the phase 1 analysis
    prompt, then calls Claude again with the phase 2 fit assessment prompt.
    Saves the full analysis to JD_analysis.md and returns the Quick Scan block.

    Args:
        vacancy_id: DB id of the vacancy (returned by cv_fetch_jd).

    Returns:
        Quick Scan block as Telegram-formatted text, prefixed with ✅ confirmation.
    """
    log.info("cv_analyze: vacancy_id=%d", vacancy_id)

    # ── Load vacancy from DB ──────────────────────────────────────────────────
    vacancy = await database.get_vacancy_by_id(vacancy_id)
    if not vacancy:
        return (
            f"⚠️ Вакансия #{vacancy_id} не найдена в базе.\n"
            f"Сначала сохрани URL командой fetch."
        )

    title = vacancy["title"] or "Без названия"
    markdown_path = vacancy["markdown_path"]

    # ── Read JD.md ────────────────────────────────────────────────────────────
    jd_path = Path(markdown_path)
    if not jd_path.exists():
        log.error("cv_analyze: JD.md not found at %s", jd_path)
        return f"⚠️ Файл JD.md не найден:\n<code>{jd_path}</code>"

    jd_text = jd_path.read_text(encoding="utf-8")

    # ── Fold in the DB-known salary, if any ───────────────────────────────────
    # `vacancies.salary` is often extracted from RSS/site metadata, not JD.md's
    # own body — without this, Phase 1's compensation scoring and Phase 2's
    # comp-related hidden-risk text reason from "not stated" while the system
    # already knows the number. Found live on #1154 (2026-08-15) and confirmed
    # recurring on #1192 (2026-08-25, DOU/RSS-sourced this time).
    salary = vacancy["salary"]
    if salary:
        jd_text = f"**Listed salary:** {salary}\n\n{jd_text}"

    # ── Load prompts from disk (skill_type-routed) ───────────────────────────
    skill_type = ctx.deps.skill_type
    skill_dir = _PROMPTS_DIR / skill_type
    phase1_prompt = (skill_dir / "phase1_analysis.md").read_text(encoding="utf-8")
    phase2_prompt = (skill_dir / "phase2_fit.md").read_text(encoding="utf-8")

    # ── Phase 1: JD Analysis ──────────────────────────────────────────────────
    run1_id = await database.insert_pipeline_run(vacancy_id, phase="phase1")
    await database.update_pipeline_run(run1_id, status="running")

    try:
        log.info("cv_analyze: Phase 1 start — vacancy_id=%d", vacancy_id)
        t0 = time.monotonic()
        llm1 = await ctx.deps.get_llm("phase1")
        phase1_output = await llm1.complete(jd_text, system=phase1_prompt, budget_tokens=3_000)
        log.info("cv_analyze: Phase 1 done — %d chars, elapsed=%.1fs", len(phase1_output), time.monotonic() - t0)
        if u := llm1.last_call_usage:
            await database.insert_llm_usage(phase="phase1", vacancy_id=vacancy_id, user_id=ctx.deps.user_id, **u)
    except LLMError as exc:
        await database.update_pipeline_run(run1_id, status="error", error_message=str(exc))
        log.error("cv_analyze: Phase 1 LLM error: %s", exc)
        await database.set_analysis_error(vacancy_id, str(exc))
        return f"⚠️ Ошибка Claude на фазе 1:\n{exc}"

    await database.update_pipeline_run(run1_id, status="done")

    # ── Reconcile §1.7 VScore prose with the deterministic dim-table value ────
    # Must happen before Phase 2 sees phase1_output and before JD_analysis.md is
    # written, so both stay consistent with what the DB will store.
    phase1_output = _reconcile_vacancy_score(phase1_output)

    # ── Update DB title from Phase 1 header ──────────────────────────────────
    extracted_title = _extract_vacancy_title(phase1_output)
    if extracted_title:
        await database.update_vacancy_fields(vacancy_id, title=extracted_title)
        title = extracted_title  # use updated title in downstream output
        log.info("cv_analyze: title updated → %r", title)

    # ── Phase 2: Candidate Fit Assessment ─────────────────────────────────────
    run2_id = await database.insert_pipeline_run(vacancy_id, phase="phase2")
    await database.update_pipeline_run(run2_id, status="running")

    phase2_user = (
        f"{jd_text}\n\n"
        f"---\n\n"
        f"Phase 1 Analysis:\n\n{phase1_output}"
    )

    try:
        log.info("cv_analyze: Phase 2 start — vacancy_id=%d", vacancy_id)
        t0 = time.monotonic()
        llm2 = await ctx.deps.get_llm("phase2")
        phase2_output = await llm2.complete(phase2_user, system=phase2_prompt, budget_tokens=3_000)
        log.info("cv_analyze: Phase 2 done — %d chars, elapsed=%.1fs", len(phase2_output), time.monotonic() - t0)
        if u := llm2.last_call_usage:
            await database.insert_llm_usage(phase="phase2", vacancy_id=vacancy_id, user_id=ctx.deps.user_id, **u)
    except LLMError as exc:
        await database.update_pipeline_run(run2_id, status="error", error_message=str(exc))
        log.error("cv_analyze: Phase 2 LLM error: %s", exc)
        await database.set_analysis_error(vacancy_id, str(exc))
        return f"⚠️ Ошибка Claude на фазе 2:\n{exc}"

    # ── Extract Quick Scan ────────────────────────────────────────────────────
    quick_scan = _extract_quick_scan(phase2_output)

    # ── Write JD_analysis.md ──────────────────────────────────────────────────
    # Always overwrite — this is the automated pipeline (CLI/API provider).
    # The "never overwrite, save to Claude Desktop/ subfolder" rule is specific
    # to the manual interactive /analyze skill session (see skill/SKILL.md),
    # not this automated path.
    analysis_path = jd_path.parent / "JD_analysis.md"
    analysis_content = _build_analysis_file(
        title=title,
        url=vacancy["url"],
        phase1=phase1_output,
        phase2=phase2_output,
        quick_scan=quick_scan,
    )
    analysis_path.write_text(analysis_content, encoding="utf-8")
    log.info("cv_analyze: saved JD_analysis.md → %s", analysis_path)

    await database.update_pipeline_run(
        run2_id, status="done", result_path=str(analysis_path)
    )

    # ── Parse + save analysis_json ────────────────────────────────────────────
    aj = AnalysisJson()
    try:
        aj = _build_analysis_json(phase1_output, phase2_output)
        if aj.p1:
            await database.patch_analysis_json(vacancy_id, "p1", aj.p1.model_dump())
        if aj.p2:
            await database.patch_analysis_json(vacancy_id, "p2", aj.p2.model_dump())
        log.info("cv_analyze: analysis_json saved (phases=%s)", aj.phases_done())
    except Exception as exc:
        log.warning("cv_analyze: analysis_json parse failed (non-fatal): %s", exc)

    # ── Surface parse failures to user ───────────────────────────────────────
    if aj.p2 is None:
        # Phase 2 LLM call succeeded but output didn't match expected format.
        # Extract first 400 chars of phase2 output as diagnostic snippet.
        snippet = phase2_output[:400].strip().replace("\n", " ")
        error_msg = (
            f"Phase 2 output could not be parsed into structured data "
            f"(missing/misformatted fields, or a validation error — see logs). "
            f"Raw start: {snippet!r}"
        )
        log.error("cv_analyze: p2 parse failed — %s", error_msg[:200])
        await database.set_analysis_error(vacancy_id, error_msg)
        await database.update_pipeline_run(run2_id, status="error", error_message="p2 parse failed — format mismatch")
        return (
            f"⚠️ Phase 2 завершилась, но не удалось распознать структуру ответа LLM.\n"
            f"Возможно, провайдер не следует формату промпта.\n"
            f"Попробуй другой провайдер или провери JD_analysis.md вручную.\n\n"
            f"<code>{snippet[:300]}</code>"
        )

    # ── Update vacancy status ─────────────────────────────────────────────────
    await database.update_vacancy_status(vacancy_id, "analyzed")

    return (
        f"✅ Анализ готов — <b>{title}</b>\n"
        f"Файл: <code>{analysis_path}</code>\n\n"
        f"{quick_scan}"
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_quick_scan(phase2_output: str) -> str:
    """Extract the ## Quick Scan block from Phase 2 LLM output.

    Matches from '## Quick Scan' to the next '## ' section or end of string.
    Falls back to first 500 chars if the block is not found.
    """
    match = re.search(
        r"(##\s*Quick Scan\b.*?)(?=\n##\s|\Z)",
        phase2_output,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    log.warning("cv_analyze: Quick Scan block not found in Phase 2 output; using fallback")
    return phase2_output[:500].strip()


def _strip_quick_scan_from_phase2(phase2: str) -> str:
    """Remove ## Quick Scan block from Phase 2 body.

    Quick Scan is placed at the top of the file separately — keeping it
    inside phase2 body causes duplication in JD_analysis.md.
    """
    m = re.search(r"(?m)^##\s+Quick Scan\b", phase2, re.IGNORECASE)
    if not m:
        return phase2
    # Find the next ## section after Quick Scan
    rest = phase2[m.start():]
    next_sec = re.search(r"(?m)^##\s+(?!Quick Scan)", rest, re.IGNORECASE)
    if next_sec:
        return (phase2[:m.start()] + rest[next_sec.start():]).strip()
    return phase2[:m.start()].strip()


_ROLE_RE    = re.compile(r"\*\*Role:\*\*\s*(.+?)(?:\n|$)", re.IGNORECASE)
_COMPANY_RE = re.compile(r"\*\*Company:\*\*\s*(.+?)(?:\n|$)", re.IGNORECASE)


def _extract_vacancy_title(phase1_output: str) -> str | None:
    """Parse Role + Company from Phase 1 ## 1.0 Vacancy Header block.

    Returns "Role — Company" string if both fields found, else None.
    Falls back gracefully — never raises.
    """
    role_m    = _ROLE_RE.search(phase1_output)
    company_m = _COMPANY_RE.search(phase1_output)
    if not role_m or not company_m:
        return None
    role    = role_m.group(1).strip()
    company = company_m.group(1).strip()
    if not role or not company:
        return None
    return f"{role} — {company}"


def _build_analysis_file(
    title: str,
    url: str,
    phase1: str,
    phase2: str,
    quick_scan: str,
) -> str:
    """Compose JD_analysis.md content.

    Quick Scan goes at the top (as required by phase2_fit.md prompt).
    Full Phase 2 assessment (without Quick Scan) and Phase 1 follow.
    """
    date = datetime.now().strftime("%Y-%m-%d")
    phase2_body = _strip_quick_scan_from_phase2(phase2)
    return (
        f"# Analysis: {title}\n\n"
        f"Source: {url}\n"
        f"Date: {date}\n\n"
        f"---\n\n"
        f"{quick_scan}\n\n"
        f"---\n\n"
        f"## Phase 2: Candidate Fit Assessment\n\n"
        f"{phase2_body}\n\n"
        f"---\n\n"
        f"## Phase 1: JD Analysis\n\n"
        f"{phase1}\n"
    )


# ── analysis_json parsers ─────────────────────────────────────────────────────
# Parse structured fields from Phase 1+2 LLM markdown output.
# All parsers return None on parse failure — callers handle gracefully.

# Phase 1 §1.7 dim table: "| company_tier | 3/4 | reasoning |"
_DIM_PATTERNS: dict[str, re.Pattern] = {
    "company_tier":      re.compile(r"(?m)^\|\s*company_tier\s*\|\s*(\d+)/4"),
    "seniority":         re.compile(r"(?m)^\|\s*seniority\s*\|\s*(\d+)/4"),
    "market_scope":      re.compile(r"(?m)^\|\s*market_scope\s*\|\s*(\d+)/3"),
    "company_type":      re.compile(r"(?m)^\|\s*company_type\s*\|\s*(\d+)/3"),
    "company_stage_fit": re.compile(r"(?m)^\|\s*company_stage_fit\s*\|\s*(\d+)/3"),
    "domain_score":      re.compile(r"(?m)^\|\s*domain_score\s*\|\s*(\d+)/5"),
    "remote_policy":     re.compile(r"(?m)^\|\s*remote_policy\s*\|\s*(\d+)/3"),
    "compensation":      re.compile(r"(?m)^\|\s*compensation\s*\|\s*(\d+)/3"),
}

# Phase 1 §1.7 prose line: "**VScore:** 8.4/10" — the LLM derives this by hand in
# free text; it can drift from the dim table it wrote just above. See
# _reconcile_vacancy_score() — DB always uses the deterministic value computed
# from the dim table, this regex lets us make the saved markdown match it too.
_VSCORE_LINE_RE = re.compile(r"(\*\*VScore:\*\*\s*)\d+(?:\.\d+)?(\s*/\s*10)", re.IGNORECASE)

# Phase 2 Internal Analysis fit table: "| Domain fit | 7 | comment |"
_FIT_DIM_PATTERNS: dict[str, re.Pattern] = {
    "domain_fit":      re.compile(r"(?im)^\|\s*Domain fit\s*\|\s*(\d+(?:\.\d+)?)\s*\|"),
    "execution_fit":   re.compile(r"(?im)^\|\s*Execution fit\s*\|\s*(\d+(?:\.\d+)?)\s*\|"),
    "strategy_fit":    re.compile(r"(?im)^\|\s*Strategy fit\s*\|\s*(\d+(?:\.\d+)?)\s*\|"),
    "systems_fit":     re.compile(r"(?im)^\|\s*Systems(?:/platform)? fit\s*\|\s*(\d+(?:\.\d+)?)\s*\|"),
    "stakeholder_fit": re.compile(r"(?im)^\|\s*Stakeholder fit\s*\|\s*(\d+(?:\.\d+)?)\s*\|"),
    "overall_fit":     re.compile(r"(?im)^\|\s*\*{0,2}Overall fit\*{0,2}\s*\|\s*(\d+(?:\.\d+)?)\s*\|"),
}

_NORTH_STAR_RE     = re.compile(r"\*\*North Star:\*\*\s*(.+?)(?:\n|$)")
_ARCHETYPE_RE      = re.compile(r"\*\*Primary archetype:\*\*\s*`?(.+?)`?(?:\n|$)", re.IGNORECASE)
_ROLE_BALANCE_RE   = {
    "strategy":    re.compile(r"Strategy[^:\n]*:\s*(\d+)%", re.IGNORECASE),
    "discovery":   re.compile(r"^\s*[-–]?\s*Discovery[^:\n]*:\s*(\d+)%", re.IGNORECASE | re.MULTILINE),
    "execution":   re.compile(r"Execution[^:\n]*:\s*(\d+)%", re.IGNORECASE),
    "stakeholder": re.compile(r"Stakeholder[^:\n]*:\s*(\d+)%", re.IGNORECASE),
    "operational": re.compile(r"Operational[^:\n]*:\s*(\d+)%", re.IGNORECASE),
}
_CULTURE_KEYWORDS  = {"speed", "ownership", "alignment", "process", "autonomy", "predictability", "innovation"}

# Accept decimals ("8.5/10") — smaller/local models emit them; rounded in the parser.
_FIT_SCORE_RE      = re.compile(r"\*\*Fit score:\*\*\s*(\d+(?:\.\d+)?)/10", re.IGNORECASE)
_RECOMMENDATION_RE = re.compile(r"\*\*Recommendation:\*\*\s*(.+?)(?:\n|$)", re.IGNORECASE)
_KEY_BARRIERS_RE   = re.compile(r"\*\*Key Barriers:\*\*\s*(.+?)(?:\n|$)", re.IGNORECASE)
_HIDDEN_RISKS_RE   = re.compile(r"\*\*Hidden Risks:\*\*\s*(.+?)(?:\n|$)", re.IGNORECASE)
_WARNINGS_RE       = re.compile(r"\*\*Warnings:\*\*\s*(.+?)(?:\n|$)", re.IGNORECASE)
_CATEGORY_RE       = re.compile(r"\*\*Category:\*\*\s*(.+?)(?:\n|$)", re.IGNORECASE)
_WHO_RE            = re.compile(r"\*\*Who they want:\*\*\s*(.+?)(?:\n|$)", re.IGNORECASE)
_WHY_APPLY_RE      = re.compile(r"\*\*Why apply:\*\*\s*(.+?)(?:\n|$)", re.IGNORECASE)
_WHY_NOT_APPLY_RE  = re.compile(r"\*\*Why not apply:\*\*\s*(.+?)(?:\n|$)", re.IGNORECASE)
_TRACK_NOTE_RE     = re.compile(r"\*\*Track note:\*\*\s*(.+?)(?:\n|$)", re.IGNORECASE)


def _parse_vacscore_dims(phase1: str) -> VacScoreDims | None:
    """Extract all 8 VacScore dim scores from Phase 1 §1.7 table."""
    values: dict[str, int] = {}
    for dim, pat in _DIM_PATTERNS.items():
        m = pat.search(phase1)
        if not m:
            return None
        values[dim] = int(m.group(1))
    try:
        return VacScoreDims(**values)
    except Exception:
        return None


def _reconcile_vacancy_score(phase1: str) -> str:
    """Overwrite the §1.7 '**VScore:** X.X/10' prose line with the value computed
    deterministically from the dim table on the same page. The LLM writes both by
    hand in one pass and the two can disagree (found live on vacancies #1268 and
    #1192, 2026-08-25 — DB always had the correct script-computed value, the saved
    markdown didn't). Returns phase1 unchanged if dims or the VScore line aren't
    found, so this never fails the pipeline — it only fixes what it can verify.
    """
    dims = _parse_vacscore_dims(phase1)
    if dims is None or not _VSCORE_LINE_RE.search(phase1):
        return phase1
    correct_score = compute_vacancy_score(dims)
    return _VSCORE_LINE_RE.sub(rf"\g<1>{correct_score:.1f}\g<2>", phase1, count=1)


def _parse_company_type(company_type_score: int) -> str:
    """Infer company_type enum from dim score (1=outsourcing, 2=hybrid, 3=product)."""
    if company_type_score == 3:
        return "product"
    if company_type_score == 2:
        return "hybrid"
    return "outsourcing"


def _parse_role_balance(phase1: str) -> dict[str, int]:
    """Extract role balance percentages from Phase 1 §1.4."""
    balance: dict[str, int] = {}
    for key, pat in _ROLE_BALANCE_RE.items():
        m = pat.search(phase1)
        if m:
            balance[key] = int(m.group(1))
    return balance or {"strategy": 25, "discovery": 25, "execution": 25, "stakeholder": 15, "operational": 10}


def _parse_dominant_culture(phase1: str) -> str:
    """Scan Phase 1 §1.6 for dominant culture keyword."""
    lower = phase1.lower()
    for kw in sorted(_CULTURE_KEYWORDS):
        if kw in lower:
            return kw
    return "unknown"


def _parse_phase1_data(phase1: str) -> Phase1Data | None:
    """Parse Phase1Data from Phase 1 LLM output. Returns None on parse failure."""
    dims = _parse_vacscore_dims(phase1)
    if dims is None:
        return None

    role_m    = _ROLE_RE.search(phase1)
    company_m = _COMPANY_RE.search(phase1)
    arch_m    = _ARCHETYPE_RE.search(phase1)
    ns_m      = _NORTH_STAR_RE.search(phase1)

    if not (role_m and company_m):
        return None

    try:
        score = compute_vacancy_score(dims)
        return Phase1Data(
            role=role_m.group(1).strip(),
            company=company_m.group(1).strip(),
            north_star=(ns_m.group(1).strip() if ns_m else ""),
            primary_archetype=(arch_m.group(1).strip() if arch_m else ""),
            company_type=_parse_company_type(dims.company_type),
            role_balance=_parse_role_balance(phase1),
            dominant_culture=_parse_dominant_culture(phase1),
            vacscore_dims=dims,
            vacancy_score=score,
        )
    except Exception:
        return None


def _split_semicolons(raw: str) -> list[str]:
    """Split semicolon-separated list; filter 'нет', 'none', empty."""
    skip = {"нет", "none", "—", "-", ""}
    items = [i.strip().rstrip(".") for i in raw.split(";")]
    return [i for i in items if i.lower() not in skip and len(i) > 2]


def _rec_label_to_base(label: str) -> str | None:
    """Map recommendation display label to base enum value."""
    ll = label.strip().lower()
    if ll.startswith("apply"):
        return "apply"
    if ll.startswith("take a chance"):
        return "take_a_chance"
    if ll.startswith("decline"):
        return "decline"
    return None


def _parse_fit_dimensions(phase2: str) -> FitDimensions | None:
    """Extract FitDimensions from Phase 2 Internal Analysis table."""
    values: dict[str, float] = {}
    for field, pat in _FIT_DIM_PATTERNS.items():
        m = pat.search(phase2)
        if m:
            values[field] = float(m.group(1))
    if len(values) < 6:
        return None
    try:
        return FitDimensions(**values)
    except Exception:
        return None


def _parse_phase2_data(phase2: str, dims: VacScoreDims | None) -> Phase2Data | None:
    """Parse Phase2Data from Phase 2 LLM output."""
    fit_m = _FIT_SCORE_RE.search(phase2)
    rec_m = _RECOMMENDATION_RE.search(phase2)
    if not (fit_m and rec_m):
        return None

    fit_score      = round(float(fit_m.group(1)))  # tolerate "8.5/10" → 8
    rec_label      = rec_m.group(1).strip()
    rec_base       = _rec_label_to_base(rec_label)
    if rec_base is None:
        return None

    key_barriers_m = _KEY_BARRIERS_RE.search(phase2)
    hidden_risks_m = _HIDDEN_RISKS_RE.search(phase2)
    warnings_m     = _WARNINGS_RE.search(phase2)
    category_m     = _CATEGORY_RE.search(phase2)
    who_m          = _WHO_RE.search(phase2)
    why_apply_m    = _WHY_APPLY_RE.search(phase2)
    why_not_m      = _WHY_NOT_APPLY_RE.search(phase2)
    track_m        = _TRACK_NOTE_RE.search(phase2)

    fit_dims = _parse_fit_dimensions(phase2)

    # Fallback FitDimensions if not parseable
    if fit_dims is None:
        fit_dims = FitDimensions(
            domain_fit=float(fit_score), execution_fit=float(fit_score),
            strategy_fit=float(fit_score), systems_fit=float(fit_score),
            stakeholder_fit=float(fit_score), overall_fit=float(fit_score),
        )

    # If Python vacscore available, re-compute recommendation (B2 override)
    if dims is not None:
        vacscore = compute_vacancy_score(dims)
        rec_base, rec_label = compute_recommendation(fit_score, vacscore)

    try:
        return Phase2Data(
            fit_score=fit_score,
            recommendation=rec_base,
            recommendation_label=rec_label,
            category=(category_m.group(1).strip() if category_m else ""),
            who_they_want=(who_m.group(1).strip() if who_m else ""),
            key_barriers=(_split_semicolons(key_barriers_m.group(1)) if key_barriers_m else []),
            hidden_risks=(_split_semicolons(hidden_risks_m.group(1)) if hidden_risks_m else []),
            warnings=(_split_semicolons(warnings_m.group(1)) if warnings_m else []),
            why_apply=(_split_semicolons(why_apply_m.group(1)) if why_apply_m else []),
            why_not_apply=(_split_semicolons(why_not_m.group(1)) if why_not_m else []),
            track_note=(track_m.group(1).strip() if track_m else None),
            fit_dimensions=fit_dims,
        )
    except Exception as exc:
        # Don't swallow the real reason — fit/rec parsed fine, so a None here is
        # almost always a Phase2Data validation error (e.g. label capitalisation).
        log.warning("cv_analyze: Phase2Data build failed: %s", exc)
        return None


def _build_analysis_json(phase1: str, phase2: str) -> AnalysisJson:
    """Build AnalysisJson from Phase 1+2 LLM output strings.

    Parsing is best-effort: partial results are valid (e.g. p1 parsed, p2 failed).
    Never raises — callers wrap in try/except as an extra guard.
    """
    p1 = _parse_phase1_data(phase1)
    dims = p1.vacscore_dims if p1 else None
    p2 = _parse_phase2_data(phase2, dims)
    return AnalysisJson(p1=p1, p2=p2)
