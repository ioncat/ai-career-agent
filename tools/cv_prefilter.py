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


def _parse_prefilter_output(text: str) -> tuple[bool, list[str], bool]:
    """Parse the BLOCKED:/REASONS: format.

    Returns (blocked, reasons, format_ok). format_ok=False means the model's
    output didn't contain a recognizable "BLOCKED: yes|no" line at all — distinct
    from format_ok=True + blocked=False, which means the model correctly followed
    the format and explicitly said no blocker. Collapsing these two into one
    "no blocker" result is exactly what hid the real bug on vacancy #716 (2026-07-17):
    a small model rambled instead of following the format, and the caller had no
    way to tell "checked, clean" from "couldn't parse what it said".
    """
    m = _BLOCKED_RE.search(text)
    if not m:
        return False, [], False
    if m.group(1).lower() != "yes":
        return False, [], True
    reasons = [r.strip() for r in _REASON_RE.findall(text)][:5]
    return True, reasons, True


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

    jd_text = jd_path.read_text(encoding="utf-8")
    skill_dir = _PROMPTS_DIR / ctx.deps.skill_type
    prompt_path = skill_dir / "prefilter.md"
    if not prompt_path.exists():
        prompt_path = _PROMPTS_DIR / "generic" / "prefilter.md"
    prefilter_prompt = prompt_path.read_text(encoding="utf-8")

    run_id = await database.insert_pipeline_run(vacancy_id, phase="prefilter")
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
    await database.set_vacancy_blocker(vacancy_id, blocked, reasons, raw_output=output)
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
