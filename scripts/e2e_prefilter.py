#!/usr/bin/env python3
"""
scripts/e2e_prefilter.py — Manual test for the Critical Blocker pre-filter (EPIC-27).

PURPOSE
-------
Direct, in-process test of tools.cv_prefilter.cv_prefilter() — no Flutter, no
HTTP layer, no client-side timeout. Built after repeated confusion (2026-07-17)
testing the pre-filter through the Flutter "Check blockers" button: the client
timeout fired before slow local models finished, the UI gave no sense of
elapsed time, and it was hard to tell "still computing" from "stuck". This
script prints a live progress tick and the full raw model output, unfiltered.

It calls the REAL cv_prefilter() — same DB writes (blocker_flag/reasons/
raw_output, pipeline_runs, llm_usage) as the Flutter button. This is not a
dry-run/preview tool; it exercises the actual pipeline path.

ROUTING
-------
By default, resolves the LLM exactly like the app does — through
core.config_store's phase_llm_config for phase="prefilter" (whatever is
currently pinned via Settings → Advanced: Per-Phase Routing, or the global
default if nothing is pinned). Pass --provider/--model/--effort to bypass
that and try something else for THIS run only — it does not touch the
persisted phase_llm_config row.

USAGE
-----
    python scripts/e2e_prefilter.py --id 716
    python scripts/e2e_prefilter.py --id 716 --provider ollama_api --model gemma4:e2b
    python scripts/e2e_prefilter.py --id 716 --provider claude_api --model claude-haiku-4-5-20251001
"""

import argparse
import asyncio
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Windows cp1252 → force UTF-8 output so emoji don't crash
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Ensure project root on sys.path
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env", override=True)
except ImportError:
    pass

from core.settings import load_settings, ConfigError
from core import config_store
from core.deps import AgentDeps
from db import database


@dataclass
class _Ctx:
    """Minimal stand-in for PydanticAI RunContext."""
    deps: AgentDeps


async def _build_llm_override(phase: str, provider: str, model: str | None, effort: str, settings) -> object:
    """Build an LLM client for provider/model given directly on the CLI —
    bypasses phase_llm_config entirely, does not persist anything. Mirrors
    config_store.build_llm_client()'s branches (kept separate deliberately:
    this script needs to construct a client the DB-backed config was never
    told about, config_store's job is resolving what IS persisted)."""
    from core.llm_client import ClaudeCodeProvider, ClaudeProvider, OllamaProvider

    profile_md = ""
    if settings.profile_md_path.exists():
        profile_md = settings.profile_md_path.read_text(encoding="utf-8")
        if phase == "prefilter":
            profile_md = config_store._extract_critical_blockers(profile_md)

    resolved_model = config_store.effective_model(provider, model)

    if provider == "claude_cli":
        return ClaudeCodeProvider(profile_md=profile_md, model=resolved_model, timeout=settings.claude_cli_timeout, effort=effort)
    if provider == "ollama_api":
        num_ctx = 4096 if phase == "prefilter" else None
        return OllamaProvider(
            base_url=settings.ollama_base_url, model=resolved_model, profile_md=profile_md,
            max_tokens=settings.max_tokens, timeout=settings.ollama_timeout, effort=effort,
            num_ctx=num_ctx,
        )
    return ClaudeProvider(api_key=settings.anthropic_api_key, model=resolved_model, profile_md=profile_md, max_tokens=settings.max_tokens)


async def _watch_progress(task: "asyncio.Task", tick_seconds: float = 5.0) -> None:
    """Print elapsed time every tick_seconds while cv_prefilter is in flight.

    The whole point of this script: local model calls that legitimately run
    for minutes look indistinguishable from "stuck" without this (found the
    hard way testing via Flutter, 2026-07-17 — no progress indication there
    beyond a static "running" label and a spinner).
    """
    t0 = time.monotonic()
    while not task.done():
        await asyncio.sleep(tick_seconds)
        if not task.done():
            print(f"  ... still running ({time.monotonic() - t0:.0f}s elapsed)")


async def run(
    vacancy_id: int,
    provider: str | None,
    model: str | None,
    effort: str,
    user_id: int,
    tick_seconds: float,
) -> None:
    print(f"\n{'='*60}")
    print(f"  career-agent e2e prefilter test")
    print(f"  vacancy_id : #{vacancy_id}")
    print(f"{'='*60}\n")

    try:
        settings = load_settings()
    except ConfigError as e:
        print(f"❌  Config error: {e}")
        sys.exit(1)

    database.configure(settings.db_path)
    await database.init_db()

    row = await database.get_vacancy_by_id(vacancy_id)
    if not row:
        print(f"❌  Vacancy #{vacancy_id} not found in DB")
        sys.exit(1)
    if not row["markdown_path"]:
        print(f"❌  Vacancy #{vacancy_id} has no JD.md yet — fetch it first")
        sys.exit(1)
    print(f"  Vacancy    : {row['title'] or row['url']}")
    print(f"  JD.md      : {row['markdown_path']}")

    user_row = await database.get_user_by_id(user_id)
    skill_type = (user_row["skill_type"] if user_row and "skill_type" in user_row.keys() else None) or settings.default_skill_type
    print(f"  skill_type : {skill_type}")

    # Captured so we can print last_thinking after the call — cv_prefilter() builds
    # the client internally via ctx.deps.get_llm(), the script never otherwise sees it.
    _built_llm: list[object] = []

    if provider:
        print(f"  Routing    : CLI override — provider={provider} model={model or '(env default)'} effort={effort}\n")

        async def _get_llm(_phase: str):
            llm = await _build_llm_override(_phase, provider, model, effort, settings)
            _built_llm.append(llm)
            return llm
    else:
        print(f"  Routing    : phase_llm_config (same as the app) — phase='prefilter'\n")

        async def _get_llm(phase: str):
            llm = await config_store.build_llm_client(phase, settings)
            _built_llm.append(llm)
            return llm

    deps = AgentDeps(
        parser_adapter=None,  # type: ignore[arg-type]  # cv_prefilter never touches this
        get_llm=_get_llm,
        vacancies_path=settings.vacancies_path,
        candidate_name=settings.candidate_name,
        cv_adapter=None,  # type: ignore[arg-type]  # cv_prefilter never touches this
        user_id=user_id,
        skill_type=skill_type,
    )
    ctx = _Ctx(deps=deps)

    from tools.cv_prefilter import cv_prefilter

    print("🔍  Running pre-filter…\n")
    t0 = time.monotonic()
    call_task = asyncio.ensure_future(cv_prefilter(ctx, vacancy_id))  # type: ignore[arg-type]
    await asyncio.gather(call_task, _watch_progress(call_task, tick_seconds))
    result = call_task.result()
    elapsed = time.monotonic() - t0

    print(f"\n{'─'*60}")
    print(f"  Elapsed         : {elapsed:.1f}s")
    print(f"  ok              : {result['ok']}")
    print(f"  blocked         : {result['blocked']}")
    print(f"  format_ok       : {result['format_ok']}")
    print(f"  provider_unavailable : {result['provider_unavailable']}")
    if result["error"]:
        print(f"  error           : {result['error']}")
    if result["reasons"]:
        print(f"  reasons         :")
        for r in result["reasons"]:
            print(f"    - {r}")
    last_thinking = getattr(_built_llm[-1], "last_thinking", None) if _built_llm else None
    if last_thinking:
        print(f"{'─'*60}")
        print(f"  Reasoning trace (message.thinking — not sent to the parser):")
        print(f"{'─'*60}")
        print(last_thinking)
    print(f"{'─'*60}")
    print(f"  Raw model output:")
    print(f"{'─'*60}")
    print(result["raw_output"] or "(none)")
    print(f"{'─'*60}\n")

    print("✅  e2e prefilter test complete")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manual e2e test for the Critical Blocker pre-filter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/e2e_prefilter.py --id 716
  python scripts/e2e_prefilter.py --id 716 --provider ollama_api --model gemma4:e2b
  python scripts/e2e_prefilter.py --id 716 --provider claude_api --model claude-haiku-4-5-20251001
        """,
    )
    parser.add_argument("--id", dest="vacancy_id", type=int, required=True, metavar="N",
                        help="Existing DB vacancy ID (must already have JD.md)")
    parser.add_argument("--user-id", dest="user_id", type=int, default=1,
                        help="career-agent DB user_id (default: 1)")
    parser.add_argument("--provider", default=None, choices=["claude_api", "ollama_api", "claude_cli"],
                        help="Override provider for this run only (default: use phase_llm_config, same as the app)")
    parser.add_argument("--model", default=None,
                        help="Override model (only meaningful together with --provider)")
    parser.add_argument("--effort", default="off",
                        help="thinking_effort when --provider is given (default: off)")
    parser.add_argument("--tick", dest="tick_seconds", type=float, default=5.0,
                        help="Seconds between progress prints while waiting (default: 5)")
    args = parser.parse_args()

    asyncio.run(run(
        vacancy_id=args.vacancy_id,
        provider=args.provider,
        model=args.model,
        effort=args.effort,
        user_id=args.user_id,
        tick_seconds=args.tick_seconds,
    ))


if __name__ == "__main__":
    main()
