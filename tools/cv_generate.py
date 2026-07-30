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
from core.cv_metrics import (
    detect_repetition,
    format_freq_table,
    format_tools_table,
    scan_tools,
    top_n_words,
)
from core.deps import AgentDeps
from core.llm_client import LLMError
from core.translit import safe_filename_stem
from db import database

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

_ISO_LANGUAGE_NAMES = {
    "en": "English",
    "uk": "Ukrainian",
    "ru": "Russian",
    "pl": "Polish",
    "de": "German",
    "es": "Spanish",
}


def _detect_cv_language(jd_text: str, analysis_text: str) -> str:
    """Resolve CV language for 'auto' mode.

    Prefers the JD Language Phase 1 already computed (JD_analysis.md's
    `**JD Language:** xx` field, phase1_analysis.md section 1.0) — that
    detection explicitly ignores URL, page title, and localized date/location
    metadata. Falls back to a naive Cyrillic scan of the raw JD text only if
    the field is missing (malformed/legacy analysis file). A bare Cyrillic
    scan over the whole JD.md misfires on DOU-sourced JDs, which carry a
    localized date/"remote" label (e.g. "29 июля 2026", "удаленно") even when
    the JD body itself is English — found live on vacancy #915.
    """
    m = re.search(r"\*\*JD Language:\*\*\s*([a-zA-Z]{2})", analysis_text)
    if m:
        code = m.group(1).lower()
        return _ISO_LANGUAGE_NAMES.get(code, code.upper())
    return "Ukrainian" if any('Ѐ' <= c <= 'ӿ' for c in jd_text) else "English"


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

    # Auto-detect language from the Phase 1-computed JD Language field.
    if language.lower() == "auto":
        language = _detect_cv_language(jd_text, analysis_text)
        log.info("cv_generate: auto-detected language=%s for vacancy_id=%d", language, vacancy_id)

    # Candidate name follows CV language — PROFILE.md's own rule (English →
    # informal default, no asking; Ukrainian → Ukrainian-spelling variant).
    # Previously a single static candidate_name was used unconditionally
    # regardless of language, injected straight into the Phase 3 prompt as a
    # hard instruction — the LLM never got a chance to apply the profile's
    # own default-name rule. Found live 2026-07-27 (vacancy #844, English JD,
    # wrong formal-variant name used).
    candidate_display_name = (
        ctx.deps.candidate_name_uk if language == "Ukrainian" else ctx.deps.candidate_name
    )

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
        f"Candidate name: {candidate_display_name}"
    )
    if _pp_evidence:
        phase3_user += f"\n\n---\n\n## Candidate Evidence (DB Profile)\n\nUse the structured evidence below to enrich the CV with specific, accurate detail. This is the authoritative source for narratives, key results, and framing. Prefer this over the summary in PROFILE.md when both are present.\n\n{_pp_evidence}"

    try:
        log.info("cv_generate: Phase 3 start — vacancy_id=%d", vacancy_id)
        t0 = time.monotonic()
        llm3 = await ctx.deps.get_llm("phase3")
        phase3_draft = await llm3.complete(phase3_user, system=phase3_prompt)
        log.info("cv_generate: Phase 3 done — %d chars, elapsed=%.1fs", len(phase3_draft), time.monotonic() - t0)
        if u := llm3.last_call_usage:
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

    # Pre-compute metrics for Phase 3.5 (replaces LLM-side compute instructions)
    _jd_freq = top_n_words(jd_text, n=15)
    _cv_freq = top_n_words(phase3_draft, n=15)
    _freq_table = format_freq_table(_jd_freq, _cv_freq)
    _tool_rows = scan_tools(jd_text, phase3_draft)
    _tools_table = format_tools_table(_tool_rows)
    _repetitions = detect_repetition(phase3_draft)
    _rep_str = (
        ", ".join(f"`{w}`" for w in _repetitions) if _repetitions else "_none detected_"
    )

    phase35_user = (
        f"JD Text:\n\n{jd_text}\n\n"
        f"---\n\n"
        f"JD Analysis:\n\n{analysis_text}\n\n"
        f"---\n\n"
        f"CV Draft:\n\n{phase3_draft}\n\n"
        f"---\n\n"
        f"## Pre-computed Metrics\n\n"
        f"### Top-15 Word Frequency\n\n"
        f"```\n{_freq_table}\n```\n\n"
        f"### Tools & Technologies\n\n"
        f"```\n{_tools_table}\n```\n\n"
        f"### Repeated Terms (3+ occurrences across CV body)\n\n"
        f"{_rep_str}"
    )

    try:
        log.info("cv_generate: Phase 3.5 start — vacancy_id=%d", vacancy_id)
        t0 = time.monotonic()
        llm35 = await ctx.deps.get_llm("phase3_5")
        phase35_output = await llm35.complete(phase35_user, system=phase35_prompt)
        log.info("cv_generate: Phase 3.5 done — %d chars, elapsed=%.1fs", len(phase35_output), time.monotonic() - t0)
        if u := llm35.last_call_usage:
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
    # Filename is always Latin ASCII, even for Ukrainian/Russian CVs (Cyrillic
    # filenames break filesystems/sync/email); document content stays original.
    safe_name = safe_filename_stem(candidate_display_name)
    cv_md_path = _next_version_path(jd_path.parent / f"{safe_name}_CV.md")
    cv_md_path.write_text(final_cv, encoding="utf-8")
    log.info("cv_generate: saved CV.md → %s", cv_md_path)

    await database.update_pipeline_run(
        run35_id, status="done", result_path=str(cv_md_path)
    )

    # ── Write review to JD_analysis.md (overwrite — always single latest review) ──
    if review_block:
        current = analysis_path.read_text(encoding="utf-8")
        cutoff = current.find("\n\n---\n\n## Phase 3.5:")
        base = current[:cutoff] if cutoff != -1 else current
        analysis_path.write_text(
            base.rstrip() + f"\n\n---\n\n## Phase 3.5: CV Self-Review\n\n{review_block}\n",
            encoding="utf-8",
        )

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
    # Review sections are supposed to use ## / ### or plain text, but the LLM
    # doesn't always comply — found live 2026-07-27 (vacancy #844): review
    # sections used their own literal H1s ("# Top-15 Word Frequency",
    # "# 🛠️ Tools & Technologies"). Taking the FIRST H1 match landed on that
    # review heading instead of the CV's name header, tripped the old
    # `m.start() > 0` guard, and fell through to "use everything, unsplit".
    # The CV body itself never uses H1 after its own name header (SUMMARY/
    # EXPERIENCE/CERTIFICATIONS are always ##/###) — so the name header is
    # reliably the LAST H1 in the whole output, regardless of how many H1s
    # the review preamble uses. Unicode range Ѐ-ӿ covers Cyrillic uppercase
    # (Ukrainian/Russian names).
    matches = list(re.finditer(r"(?m)^# [A-ZЀ-ӿ]", phase35_output))
    if matches:
        m = matches[-1]
        review = phase35_output[: m.start()].strip()
        cv = phase35_output[m.start():].strip()
        return review, cv

    log.warning("cv_generate: no split anchor found in Phase 3.5 output — using full output as CV")
    return "", phase35_output.strip()
