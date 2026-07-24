"""
tools/cv_prefilter.py — Critical Blocker pre-filter (EPIC-27).

Runs right after a vacancy is fetched, before Phase 1+2. Cheap, advisory-only check:
does the JD contain an explicit hard requirement conflicting with the candidate's
## Critical Blockers (PROFILE.md)? Never blocks the pipeline — just flags the
vacancy so the user can decide whether to bother reviewing it.

Fail-open: any error (LLM unreachable, timeout, unparseable output) is treated as
"no blockers found" and logged, never surfaced as a false blocker.

Tool registered in agent.py via ToolRegistry.
Receives shared dependencies via RunContext[AgentDeps].
"""

import asyncio
import logging
import re
import time
from pathlib import Path

from pydantic_ai import RunContext

from core.deps import AgentDeps
from core.llm_client import LLMUnavailableError
from db import database

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

_BLOCKED_RE = re.compile(r"(?im)^BLOCKED:\s*(yes|no)\s*$")
_REASON_RE = re.compile(r"(?m)^-\s*(.+)$")

# Mirrors the fit-list in PROFILE.md's `title:` Critical Blockers line. Kept
# here (not read from PROFILE.md) because this is a deterministic code path,
# not a prompt — see docs/discovery/prefilter-local-model-selection.md
# (2026-07-23): letting an LLM judge a literal substring match against ~9
# known terms produced errors an LLM should never make ("Product Owner Lead"
# flagged despite containing "Product Owner") because the title verdict got
# blended with unrelated JD-body signal (domain, seniority) in the same call.
_TITLE_ALLOWLIST = [
    "product manager",
    "product owner",
    "project manager",
    "delivery manager",
    "program manager",
    "business analyst",
    "operations manager",
    "technical product manager",
    "technical project manager",
]

# A word immediately BEFORE a matched allowlist term that changes the actual
# function of the role, not just its domain/platform — "Growth Product
# Manager" contains "Product Manager" as a literal substring but is a
# distinct discipline (growth marketing), same reason the candidate flagged
# it as its own denylist item before the allowlist rewrite. Found 2026-07-23
# via a 50-vacancy audit (#779 "Growth Product Manager (iGaming)" — real
# mismatch, wrongly passed by substring-only matching). A word AFTER the
# term (iGaming, Mobile, Adtech, in parens or after a dash) is a domain
# modifier, not a function modifier — #776 "Product Manager (iGaming)" is a
# genuine fit, iGaming there says nothing about the role's function.
_TITLE_PREFIX_DENYLIST = {
    "growth", "crm", "retention", "marketing", "sales", "bizdev",
    "risk", "compliance", "antifraud", "gamification", "community", "smm",
    "vip", "payment", "payments", "ppc",
}

_WORD_RE = re.compile(r"[a-z]+")


def _check_title_allowlist(title: str) -> str | None:
    """Deterministic pre-check: does the vacancy title contain one of the
    candidate's fit-list terms, without a function-changing prefix directly
    in front of it? Returns None if it fits (proceed to the LLM content
    check), or a reason string if it's a mismatch (short-circuit, never call
    the LLM).
    """
    if not title:
        return None
    low = title.lower()
    for term in _TITLE_ALLOWLIST:
        idx = low.find(term)
        if idx == -1:
            continue
        preceding_words = _WORD_RE.findall(low[:idx])
        if preceding_words and preceding_words[-1] in _TITLE_PREFIX_DENYLIST:
            continue  # substring matched, but a function-changing prefix sits right before it — keep scanning other terms
        return None
    return f'title: "{title.strip()}" does not contain a fitting role term (Product Manager/Owner, Project/Delivery/Program Manager, Business Analyst, Operations Manager, Technical Product/Project Manager)'


# Fast-path for the `domain`/`igaming` Critical Blockers — NOT a new blocker
# category, same verdict the LLM would reach reading the JD body, caught
# earlier (and for free) on the ~common cases where the title names the
# domain outright (usually a parenthetical suffix: "Product Manager
# (iGaming)", "Product Manager (Mobile Apps)"). Kept deliberately small per
# user's explicit call (2026-07-23) — not meant to replace the LLM's JD-body
# read for domain signal, just skip the round-trip when the title already
# gives it away. Unlike `title:`, `domain`/`igaming` stay in what the LLM
# sees too (`_extract_critical_blockers` doesn't strip them) — a title
# without the domain in it still needs the LLM to catch it from the body.
_TITLE_DOMAIN_DENYLIST = {
    "igaming": "igaming",
    "gambling": "igaming",
    "betting": "igaming",
    "mobile": "domain",
}


def _check_title_domain_signals(title: str) -> str | None:
    """Deterministic pre-check: does the title itself name a blocked domain
    (iGaming, Mobile)? Returns None if clean (or ambiguous — let the LLM
    decide from the JD body), or a reason string to short-circuit on.
    """
    if not title:
        return None
    low = title.lower()
    for term, category in _TITLE_DOMAIN_DENYLIST.items():
        if term in low:
            return f'{category}: title "{title.strip()}" names the domain directly'
    return None


def _parse_prefilter_output(text: str) -> tuple[bool, list[str], bool]:
    """Parse the BLOCKED:/REASONS: format.

    Returns (blocked, reasons, format_ok). format_ok=False means either the
    model's output didn't contain a recognizable "BLOCKED: yes|no" line at all
    — distinct from format_ok=True + blocked=False, which means the model
    correctly followed the format and explicitly said no blocker. Collapsing
    these two into one "no blocker" result is exactly what hid the real bug on
    vacancy #716 (2026-07-17): a small model rambled instead of following the
    format, and the caller had no way to tell "checked, clean" from "couldn't
    parse what it said".

    format_ok is ALSO False when MULTIPLE "BLOCKED:" lines appear — a sign the
    model leaked self-correction into the final output instead of keeping it
    to the hidden reasoning channel (found 2026-07-23, vacancy #725: model
    wrote "BLOCKED: yes" ... "Wait — ... No title conflict" ... "BLOCKED: no").
    The LAST match is used as the verdict (the self-corrected answer is more
    likely the model's real final judgment), but the anomaly is still flagged
    rather than silently treated as a clean run — same principle as the
    single-match case above.
    """
    matches = list(_BLOCKED_RE.finditer(text))
    if not matches:
        return False, [], False
    clean_format = len(matches) == 1
    last = matches[-1]
    if last.group(1).lower() != "yes":
        return False, [], clean_format
    reasons = [r.strip() for r in _REASON_RE.findall(text[last.end():])]
    if not reasons:
        # some models put REASONS before the final BLOCKED line — fall back
        # to scanning the whole text rather than reporting an empty list.
        reasons = [r.strip() for r in _REASON_RE.findall(text)]
    return True, reasons[:5], clean_format


async def apply_title_stage(vacancy_id: int, title: str) -> bool:
    """Run the deterministic title/domain check (Stage 1 — no LLM) and write
    a blocker immediately if it fails. Returns True if a blocker was set.

    Called automatically on vacancy ingestion (RSSWatcher, import-jd) when
    the "Auto-check title" setting is on — see db.database.get_auto_check_title().
    Free and instant, so unlike Stage 2 (the LLM content check, still manual-
    trigger-only) there's no cost/reliability reason to gate it behind a
    per-vacancy button; the setting exists only so the user can turn the
    write off entirely, not to control cost.

    Safe to call again later — `cv_prefilter()` re-runs the same check first
    and short-circuits identically, so there's no risk of a mismatched verdict
    between the automatic write and a later manual "Check blockers" run.
    """
    reason = _check_title_domain_signals(title) or _check_title_allowlist(title)
    if reason is None:
        return False
    log.info("apply_title_stage: v#%d flagged at ingestion (no LLM call): %s", vacancy_id, reason)
    await database.set_vacancy_blocker(
        vacancy_id, True, [reason],
        raw_output=f"BLOCKED: yes\n- {reason}\n(deterministic title check — no LLM call)",
        stage="title",
    )
    return True


async def cv_prefilter(ctx: RunContext[AgentDeps], vacancy_id: int) -> dict:
    """Run the critical blocker pre-filter on a freshly-fetched vacancy.

    Never raises — always returns a result dict describing what happened:
        {"ok": bool, "blocked": bool, "reasons": list[str],
         "raw_output": str | None, "format_ok": bool, "error": str | None,
         "provider_unavailable": bool}
    "ok" distinguishes "we actually got and parsed a real answer" from any
    failure (LLM unreachable, model not found, parse mismatch) — callers that
    want fail-open automatic behavior can just ignore "ok"/"error" and treat
    blocked=False as "don't flag it"; callers debugging the pipeline (the manual
    trigger endpoint) can surface the distinction instead of a misleading "no
    blockers" for a call that never actually ran.
    "provider_unavailable" flags the specific case of "the LLM service itself
    couldn't be reached" (Ollama not running, Claude API down/rate-limited,
    `claude` CLI missing) — every provider already raises the same
    core.llm_client.LLMUnavailableError for this, regardless of which one is
    configured. Distinguishing it from other failures (bad prompt, parse
    mismatch, vacancy not found) lets the UI say something actionable
    ("provider unavailable — check it's running") instead of a generic
    "something went wrong" (found missing 2026-07-17: Ollama being down looked
    identical to any other error).
    """
    log.info("cv_prefilter: vacancy_id=%d", vacancy_id)

    def _fail(error: str, raw_output: str | None = None, provider_unavailable: bool = False) -> dict:
        return {"ok": False, "blocked": False, "reasons": [], "raw_output": raw_output,
                "format_ok": False, "error": error, "provider_unavailable": provider_unavailable}

    vacancy = await database.get_vacancy_by_id(vacancy_id)
    if not vacancy or not vacancy["markdown_path"]:
        log.warning("cv_prefilter: vacancy_id=%d not found or no JD.md — skipping", vacancy_id)
        return _fail("Vacancy not found or has no JD.md")

    jd_path = Path(vacancy["markdown_path"])
    if not jd_path.exists():
        log.warning("cv_prefilter: JD.md not found at %s — skipping", jd_path)
        return _fail(f"JD.md not found at {jd_path}")

    run_id = await database.insert_pipeline_run(vacancy_id, phase="prefilter")

    title = vacancy["title"] or ""
    deterministic_reason = _check_title_domain_signals(title) or _check_title_allowlist(title)
    if deterministic_reason is not None:
        log.info("cv_prefilter: v#%d deterministic match (no LLM call): %s", vacancy_id, deterministic_reason)
        await database.set_vacancy_blocker(
            vacancy_id, True, [deterministic_reason],
            raw_output=f"BLOCKED: yes\n- {deterministic_reason}\n(deterministic title check — no LLM call)",
            stage="title",
        )
        await database.update_pipeline_run(run_id, status="done")
        return {
            "ok": True,
            "blocked": True,
            "reasons": [deterministic_reason],
            "raw_output": None,
            "format_ok": True,
            "error": None,
            "provider_unavailable": False,
        }

    jd_text = jd_path.read_text(encoding="utf-8")
    skill_dir = _PROMPTS_DIR / ctx.deps.skill_type
    prompt_path = skill_dir / "prefilter.md"
    if not prompt_path.exists():
        prompt_path = _PROMPTS_DIR / "generic" / "prefilter.md"
    prefilter_prompt = prompt_path.read_text(encoding="utf-8")

    await database.update_pipeline_run(run_id, status="running")

    try:
        t0 = time.monotonic()
        llm = await ctx.deps.get_llm("prefilter")
        output = await llm.complete(jd_text, system=prefilter_prompt)
        log.info("cv_prefilter: done — vacancy_id=%d elapsed=%.1fs", vacancy_id, time.monotonic() - t0)
        if u := llm.last_call_usage:
            await database.insert_llm_usage(phase="prefilter", vacancy_id=vacancy_id, user_id=ctx.deps.user_id, **u)
    except asyncio.CancelledError:
        # BaseException, not Exception (Python 3.8+) — `except Exception` below
        # never catches it. Happens when the client disconnects mid-request
        # (closed the app, navigated away) — found the hard way on vacancy #716
        # (2026-07-17): the row sat at status='running' for 3+ hours, forever,
        # because nothing ever recorded the interruption. Record it, then
        # re-raise — swallowing cancellation silently breaks asyncio semantics.
        log.warning("cv_prefilter: cancelled v#%d (client disconnected?)", vacancy_id)
        await database.update_pipeline_run(run_id, status="error", error_message="Cancelled — client disconnected or request interrupted")
        raise
    except LLMUnavailableError as exc:
        # Every provider (Ollama/Claude API/claude CLI) raises this SAME class
        # for "the service itself couldn't be reached" — Ollama not running,
        # Claude API down/rate-limited, claude CLI missing. Distinguished from
        # generic errors so the UI can say something actionable instead of a
        # bare "some error happened" (gap found 2026-07-17).
        err = str(exc)[:500]
        log.warning("cv_prefilter: provider unavailable v#%d: %s", vacancy_id, err)
        await database.update_pipeline_run(run_id, status="error", error_message=err)
        return _fail(err, provider_unavailable=True)
    except Exception as exc:
        # Fail-open for the caller's blocker decision (never a false blocker), but
        # the failure itself is NOT hidden — recorded on pipeline_runs and returned.
        err = str(exc)[:500]
        log.warning("cv_prefilter: failed v#%d (fail-open, no blocker recorded): %s", vacancy_id, err)
        await database.update_pipeline_run(run_id, status="error", error_message=err)
        return _fail(err)

    blocked, reasons, format_ok = _parse_prefilter_output(output)
    await database.set_vacancy_blocker(vacancy_id, blocked, reasons, raw_output=output, stage="content")
    await database.update_pipeline_run(
        run_id,
        status="done" if format_ok else "error",
        error_message=None if format_ok else "Model output didn't match the expected BLOCKED: format",
    )
    log.info(
        "cv_prefilter: v#%d blocked=%s reasons=%d format_ok=%s",
        vacancy_id, blocked, len(reasons), format_ok,
    )
    return {
        "ok": format_ok,
        "blocked": blocked,
        "reasons": reasons,
        "raw_output": output,
        "format_ok": format_ok,
        "error": None if format_ok else "Model output didn't match the expected BLOCKED: format",
        "provider_unavailable": False,
    }
