"""
tools/cv_generate.py — CV pipeline Phase 3 + 3.5: draft → self-review → final CV + PDF.

Pipeline step 2:
    Phase 3  — hidden CV draft (not shown to user).
    Phase 3.5 — self-review; produces a self-critique block + the revised CV.
    Output   — [Name]_CV.md + [Name]_CV.pdf saved to vacancy folder.

Phase 3.5 output structure:
    CV SELF-REVIEW        ← review block (shown to user + appended to JD_analysis.md)
    ——————————————
    ❌ Remove / doesn't fit:
    ⚠️ Weaken / compress:
    🔧 Strengthen / reframe:
    ✅ Strong — keep as is:

    [Name]                ← final CV starts here (name/headline/contacts)
    [Headline]
    [Contacts]

    SUMMARY               ← anchor used to split review from CV
    ...

Tool registered in agent.py via ToolRegistry.
Receives shared dependencies via RunContext[AgentDeps].
"""

import json
import logging
import re
import time
from pathlib import Path

from pydantic_ai import RunContext

from adapters.cv_adapter import CVAdapterError
from core.deps import AgentDeps
from core.llm_client import LLMError
from db import database

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


async def cv_generate(
    ctx: RunContext[AgentDeps],
    vacancy_id: int,
    language: str = "English",
) -> str:
    """Generate a tailored CV for a fetched and analysed vacancy.

    Runs Phase 3 (hidden draft) then Phase 3.5 (self-review). Saves the final
    reviewed CV as [Name]_CV.md and generates a PDF. Returns the self-review
    block so the user can see what was changed and why.

    Args:
        vacancy_id: DB id of the vacancy (must be status 'analyzed').
        language:   Target CV language — 'English', 'Ukrainian', or 'both'.

    Returns:
        Self-review critique block + file paths confirmation.
    """
    log.info("cv_generate: vacancy_id=%d language=%s", vacancy_id, language)

    # ── Load vacancy from DB ──────────────────────────────────────────────────
    vacancy = await database.get_vacancy_by_id(vacancy_id)
    if not vacancy:
        return (
            f"⚠️ Вакансия #{vacancy_id} не найдена в базе.\n"
            f"Сначала сохрани URL (fetch) и запусти анализ (analyze)."
        )

    title = vacancy["title"] or "Без названия"
    markdown_path = vacancy["markdown_path"]

    # ── Read source files ─────────────────────────────────────────────────────
    jd_path = Path(markdown_path)
    if not jd_path.exists():
        return f"⚠️ Файл JD.md не найден:\n<code>{jd_path}</code>"

    analysis_path = jd_path.parent / "JD_analysis.md"
    if not analysis_path.exists():
        return (
            f"⚠️ JD_analysis.md не найден. Сначала запусти анализ для вакансии #{vacancy_id}."
        )

    jd_text = jd_path.read_text(encoding="utf-8")
    analysis_text = analysis_path.read_text(encoding="utf-8")

    # Auto-detect language from JD: any Cyrillic → Ukrainian, else English
    if language.lower() == "auto":
        language = "Ukrainian" if any('Ѐ' <= c <= 'ӿ' for c in jd_text) else "English"
        log.info("cv_generate: auto-detected language=%s for vacancy_id=%d", language, vacancy_id)

    # ── Load progressive_profile evidence (EPIC-24 T6) ───────────────────────
    _pp_evidence: str | None = None
    user_row = await database.get_user_by_id(ctx.deps.user_id)
    if user_row:
        pp_str = user_row["progressive_profile"] if "progressive_profile" in user_row.keys() else None
        if pp_str:
            try:
                pp_data = json.loads(pp_str)
                roles = pp_data.get("roles", [])
                if roles:
                    _pp_evidence = _format_pp_evidence(roles)
                    log.info("cv_generate: loaded %d roles from progressive_profile", len(roles))
            except Exception as exc:
                log.warning("cv_generate: failed to load progressive_profile: %s", exc)

    # ── Load prompts (skill_type-routed) ─────────────────────────────────────
    skill_dir = _PROMPTS_DIR / ctx.deps.skill_type
    phase3_prompt = (skill_dir / "phase3_cv_draft.md").read_text(encoding="utf-8")
    phase35_prompt = (skill_dir / "phase3_5_review.md").read_text(encoding="utf-8")

    # ── Phase 3: CV Draft (hidden) ────────────────────────────────────────────
    run3_id = await database.insert_pipeline_run(vacancy_id, phase="phase3")
    await database.update_pipeline_run(run3_id, status="running")

    phase3_user = (
        f"JD Text:\n\n{jd_text}\n\n"
        f"---\n\n"
        f"JD Analysis:\n\n{analysis_text}\n\n"
        f"---\n\n"
        f"Target language: {language}\n"
        f"Candidate name: {ctx.deps.candidate_name}"
    )
    if _pp_evidence:
        phase3_user += f"\n\n---\n\n## Candidate Evidence (DB Profile)\n\nUse the structured evidence below to enrich the CV with specific, accurate detail. This is the authoritative source for narratives, key results, and framing. Prefer this over the summary in PROFILE.md when both are present.\n\n{_pp_evidence}"

    try:
        log.info("cv_generate: Phase 3 start — vacancy_id=%d", vacancy_id)
        t0 = time.monotonic()
        phase3_draft = await ctx.deps.llm.complete(phase3_user, system=phase3_prompt)
        log.info("cv_generate: Phase 3 done — %d chars, elapsed=%.1fs", len(phase3_draft), time.monotonic() - t0)
        if u := ctx.deps.llm.last_call_usage:
            await database.insert_llm_usage(phase="phase3", vacancy_id=vacancy_id, user_id=ctx.deps.user_id, **u)
    except LLMError as exc:
        await database.update_pipeline_run(run3_id, status="error", error_message=str(exc))
        log.error("cv_generate: Phase 3 LLM error: %s", exc)
        raise

    await database.update_pipeline_run(run3_id, status="done")

    # Save raw draft for debugging (not shown to user)
    draft_path = jd_path.parent / "CV_draft_p3.md"
    draft_path.write_text(phase3_draft, encoding="utf-8")

    # ── Phase 3.5: Self-Review ────────────────────────────────────────────────
    run35_id = await database.insert_pipeline_run(vacancy_id, phase="phase3_5")
    await database.update_pipeline_run(run35_id, status="running")

    phase35_user = (
        f"JD Text:\n\n{jd_text}\n\n"
        f"---\n\n"
        f"JD Analysis:\n\n{analysis_text}\n\n"
        f"---\n\n"
        f"CV Draft:\n\n{phase3_draft}"
    )

    try:
        log.info("cv_generate: Phase 3.5 start — vacancy_id=%d", vacancy_id)
        t0 = time.monotonic()
        phase35_output = await ctx.deps.llm.complete(phase35_user, system=phase35_prompt)
        log.info("cv_generate: Phase 3.5 done — %d chars, elapsed=%.1fs", len(phase35_output), time.monotonic() - t0)
        if u := ctx.deps.llm.last_call_usage:
            await database.insert_llm_usage(phase="phase3_5", vacancy_id=vacancy_id, user_id=ctx.deps.user_id, **u)
    except LLMError as exc:
        await database.update_pipeline_run(run35_id, status="error", error_message=str(exc))
        log.error("cv_generate: Phase 3.5 LLM error: %s", exc)
        raise

    # ── Split review block from final CV ──────────────────────────────────────
    review_block, final_cv = _split_review_and_cv(phase35_output)

    if not final_cv:
        log.warning("cv_generate: could not extract CV from Phase 3.5 output — using full output")
        final_cv = phase35_output

    # ── Save [Name]_CV.md (versioned if already exists) ──────────────────────
    safe_name = re.sub(r"[^\w\-]", "_", ctx.deps.candidate_name)
    cv_md_path = _next_version_path(jd_path.parent / f"{safe_name}_CV.md")
    cv_md_path.write_text(final_cv, encoding="utf-8")
    log.info("cv_generate: saved CV.md → %s", cv_md_path)

    await database.update_pipeline_run(
        run35_id, status="done", result_path=str(cv_md_path)
    )

    # ── Append review to JD_analysis.md ──────────────────────────────────────
    if review_block:
        with analysis_path.open("a", encoding="utf-8") as f:
            f.write(f"\n\n---\n\n## Phase 3.5: CV Self-Review\n\n{review_block}\n")

    # ── Update vacancy status ─────────────────────────────────────────────────
    await database.update_vacancy_status(vacancy_id, "cv_generated")

    # ── Generate PDF (best-effort) ────────────────────────────────────────────
    pdf_msg = ""
    try:
        pdf_path = await ctx.deps.cv_adapter.generate_pdf(cv_md_path)
        pdf_msg = f"PDF: <code>{pdf_path}</code>\n"
    except (CVAdapterError, FileNotFoundError, Exception) as exc:
        log.warning("cv_generate: PDF generation failed: %s", exc)
        pdf_msg = "PDF: не удалось сгенерировать (проверь логи)\n"

    # ── Build Telegram reply ──────────────────────────────────────────────────
    return (
        f"✅ CV готов — <b>{title}</b>\n\n"
        f"{review_block or '(self-review block not extracted)'}\n\n"
        f"---\n\n"
        f"MD: <code>{cv_md_path}</code>\n"
        f"{pdf_msg}"
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _next_version_path(base_path: Path) -> Path:
    """Return base_path if it doesn't exist; else base_path with _v2/_v3/... suffix."""
    if not base_path.exists():
        return base_path
    stem, suffix, parent = base_path.stem, base_path.suffix, base_path.parent
    n = 2
    while True:
        candidate = parent / f"{stem}_v{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def _format_pp_evidence(roles: list) -> str:
    """Format progressive_profile roles[] into a structured evidence block for Phase 3."""
    parts: list[str] = []
    for role in roles:
        lines: list[str] = []
        title = role.get("title", "")
        company = role.get("company", "")
        dates = role.get("dates", "")
        header = f"### {title} — {company}"
        if dates:
            header += f" ({dates})"
        lines.append(header)

        if role.get("narrative"):
            lines.append(role["narrative"])

        krs = role.get("key_results", [])
        if krs:
            lines.append("**Key Results:**")
            lines.extend(f"- {kr}" for kr in krs)

        for f_item in role.get("framing", []):
            label = f_item.get("label", "")
            emphasis = f_item.get("emphasis", "")
            de_emphasis = f_item.get("de_emphasis", "")
            if label:
                lines.append(f"**Framing — {label}:**")
                if emphasis:
                    lines.append(f"Emphasise: {emphasis}")
                if de_emphasis:
                    lines.append(f"De-emphasise: {de_emphasis}")

        caveats = role.get("caveats", [])
        if caveats:
            lines.append("**Caveats (internal — do not disclose):**")
            lines.extend(f"- {c}" for c in caveats)

        tags = role.get("tags", [])
        if tags:
            lines.append(f"**Tags:** {', '.join(tags)}")

        parts.append("\n".join(lines))

    return "\n\n---\n\n".join(parts)


def _split_review_and_cv(phase35_output: str) -> tuple[str, str]:
    """Split Phase 3.5 output into (review_block, final_cv).

    Tries three strategies in order:

    1. Explicit separator  ---CV---  (preferred, added to prompt).
    2. Markdown heading   # UPDATED CV DRAFT  (LLM fallback).
    3. Bare SUMMARY line (original format).

    Returns:
        (review_block, final_cv) — either may be empty string on parse failure.
    """
    # ── Strategy 1: explicit ---CV--- separator (prompt-enforced) ────────────
    m = re.search(r"(?m)^---CV---\s*$", phase35_output)
    if m:
        review = phase35_output[: m.start()].strip()
        cv = phase35_output[m.end():].strip()
        return review, cv

    # ── Strategy 2: "# UPDATED CV DRAFT" heading ─────────────────────────────
    m = re.search(r"(?m)^#{1,3}\s*UPDATED CV", phase35_output, re.IGNORECASE)
    if m:
        review = phase35_output[: m.start()].strip()
        after_heading = phase35_output[m.end():]
        # Strip the optional --- separator line after the heading
        cv = re.sub(r"^\s*-{3,}\s*\n", "", after_heading).strip()
        return review, cv

    # ── Strategy 3: bare SUMMARY anchor (original) ───────────────────────────
    m = re.search(r"(?m)^SUMMARY$", phase35_output)
    if m:
        before_summary = phase35_output[: m.start()]
        before_stripped = before_summary.rstrip("\n")
        last_para_break = before_stripped.rfind("\n\n")
        if last_para_break != -1:
            review = before_stripped[:last_para_break].strip()
            name_block = before_stripped[last_para_break + 2:].strip()
            cv = name_block + "\n\n" + phase35_output[m.start():]
        else:
            review = ""
            cv = phase35_output.strip()
        return review, cv.strip()

    # ── Strategy 4: H1 heading — CV always starts with "# FirstName LastName" ─
    # Review sections use ## / ### or plain text; H1 only appears as CV header.
    m = re.search(r"(?m)^# [A-Z]", phase35_output)
    if m and m.start() > 0:
        review = phase35_output[: m.start()].strip()
        cv = phase35_output[m.start():].strip()
        return review, cv

    log.warning("cv_generate: no split anchor found in Phase 3.5 output — using full output as CV")
    return "", phase35_output.strip()
