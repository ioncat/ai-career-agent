#!/usr/bin/env python3
"""
scripts/e2e_test.py — Manual end-to-end integration test.

PURPOSE
-------
Verify that all pipeline phases work correctly together with real services.
Unlike unit tests (which mock everything), this hits the actual Claude API,
real jd-parser, and real pdf-service. Run it when you need confidence that
the full stack is alive — not as a routine check (costs API tokens).

WHEN TO RUN
-----------
- After changes to: cv_generate, cv_cover, cv_analyze, ClaudeProvider, CVAdapter
- After merging a significant EPIC
- When something seems broken and you need to confirm it's fixed
- Before a "release" (sharing with new users)
- NOT on a schedule — use health_check.py (see scripts/health_check.py) for that

AGENT_MODE=testing (default)
-----------------------------
Before each Claude API call the script pauses and asks "Proceed? [y/N]".
This is a cost-control safety net. Options:
  - Run in interactive terminal: answer y/n manually
  - Pass --auto-confirm: skip all prompts (use when you've already decided to run)

WHAT IT DOES NOT DO
-------------------
- Does NOT send Telegram messages (output goes to stdout only)
- Does NOT affect production data (uses same DB as dev, but no Telegram delivery)

INPUT MODES
-----------
  --url URL         fetch JD from web → run pipeline phases
  --file PATH.md    read JD from local .md file (skips fetch)
  --id VACANCY_ID   reprocess existing DB vacancy (skips fetch)

PREREQUISITES
-------------
  - .env: ANTHROPIC_API_KEY set, AGENT_MODE=testing
  - jd-parser running on PARSER_URL (:8001) — required for --url mode
  - pdf-service running on :8002 — required for generate phase
  - DB at DB_PATH (default db/agent.db)

USAGE
-----
    python scripts/e2e_test.py
    python scripts/e2e_test.py --url https://jobs.dou.ua/companies/.../
    python scripts/e2e_test.py --file vacancies/1/dou/2026-06/123/JD.md
    python scripts/e2e_test.py --id 42
    python scripts/e2e_test.py --url https://... --phase fetch,analyze
    python scripts/e2e_test.py --id 42 --phase generate,cover
    python scripts/e2e_test.py --id 42 --phase generate,cover --auto-confirm
"""

import argparse
import asyncio
import sys
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
from core.llm_client import ClaudeProvider, ClaudeCodeProvider, OllamaProvider
from adapters.parser_adapter import ParserAdapter
from adapters.cv_adapter import CVAdapter
from core.deps import AgentDeps
from db import database


_DEFAULT_URL = "https://jobs.dou.ua/companies/solar-digital/vacancies/360005/"


@dataclass
class _Ctx:
    """Minimal stand-in for PydanticAI RunContext."""
    deps: AgentDeps


def _sync_user_from_yaml(user_id: int) -> tuple[str, str] | None:
    """Read skill/users.yaml and return (name, skill_type) for user_id, or None."""
    yaml_path = _ROOT / "skill" / "users.yaml"
    if not yaml_path.exists():
        return None
    try:
        import yaml  # type: ignore[import]
    except ImportError:
        return None
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    for u in data.get("users", []):
        if int(u.get("id", -1)) == user_id:
            name = u.get("name", f"User {user_id}")
            skill_type = u.get("skill_type", "pm")
            return name, skill_type
    return None


async def run_e2e(
    url: str | None,
    phases: list[str],
    file_path: Path | None = None,
    vacancy_id: int | None = None,
    user_id: int = 1,
    profile_path: Path | None = None,
    auto_confirm: bool = False,
) -> None:
    # Determine mode label for display
    if file_path:
        mode = f"file: {file_path}"
    elif vacancy_id is not None:
        mode = f"vacancy_id: #{vacancy_id}"
    else:
        mode = f"url: {url}"

    print(f"\n{'='*60}")
    print(f"  career-agent e2e test")
    print(f"  Input  : {mode}")
    print(f"  Phases : {', '.join(phases)}")
    print(f"  user_id: {user_id}")
    print(f"{'='*60}\n")

    # ── Settings & services ───────────────────────────────────────────────────
    try:
        settings = load_settings()
    except ConfigError as e:
        print(f"❌  Config error: {e}")
        sys.exit(1)

    print(f"  AGENT_MODE  : {settings.agent_mode}")
    print(f"  PARSER_URL  : {settings.parser_url}")
    print(f"  DB_PATH     : {settings.db_path}")
    print(f"  CANDIDATE   : {settings.candidate_name}")
    print()

    database.configure(settings.db_path)
    await database.init_db()

    # Sync user from skill/users.yaml → DB (upsert — safe to call every run)
    user_info = _sync_user_from_yaml(user_id)
    if user_info:
        name, skill_type_from_yaml = user_info
        await database.upsert_user(user_id, name=name, skill_type=skill_type_from_yaml)
        print(f"  User sync   : #{user_id} {name!r} (skill_type={skill_type_from_yaml})\n")
    else:
        print(f"  User sync   : skill/users.yaml not found or user #{user_id} not listed\n")

    # Profile: --profile arg overrides PROFILE_MD_PATH from settings
    effective_profile_path = profile_path or settings.profile_md_path
    if not effective_profile_path.exists():
        print(f"❌  PROFILE.md not found: {effective_profile_path}")
        sys.exit(1)
    profile_md = effective_profile_path.read_text(encoding="utf-8")
    print(f"  PROFILE.md  : {effective_profile_path} ({len(profile_md)} chars)\n")

    if settings.llm_provider == "claude_cli":
        llm = ClaudeCodeProvider(profile_md=profile_md, model=settings.llm_model, timeout=settings.claude_cli_timeout)
        print(f"  LLM         : claude_cli ({settings.llm_model}) timeout={settings.claude_cli_timeout}s\n")
    elif settings.llm_provider == "ollama_api":
        llm = OllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            profile_md=profile_md,
            max_tokens=settings.max_tokens,
            timeout=settings.ollama_timeout,
        )
        print(f"  LLM         : ollama ({settings.ollama_model})\n")
    else:
        llm = ClaudeProvider(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model,
            profile_md=profile_md,
            max_tokens=settings.max_tokens,
            testing_mode=(settings.agent_mode == "testing"),
            auto_confirm=auto_confirm,
        )
        print(f"  LLM         : claude_api ({settings.llm_model})\n")

    parser = ParserAdapter(base_url=settings.parser_url)
    cv_adapter = CVAdapter(pdf_service_url=settings.pdf_service_url)

    # Resolve skill_type for the given user_id
    user_row = await database.get_user_by_id(user_id)
    skill_type = user_row["skill_type"] if user_row else settings.default_skill_type

    # e2e_test builds one client from CLI args (--testing/--auto-confirm are
    # dev-only concerns, not part of core.config_store's production path) —
    # get_llm ignores the phase and always returns this same instance.
    async def _fixed_llm(_phase: str) -> object:
        return llm

    deps = AgentDeps(
        parser_adapter=parser,
        get_llm=_fixed_llm,
        vacancies_path=settings.vacancies_path,
        candidate_name=settings.candidate_name,
        cv_adapter=cv_adapter,
        user_id=user_id,
        skill_type=skill_type,
    )
    print(f"  skill_type  : {skill_type}\n")
    ctx = _Ctx(deps=deps)

    # ── Resolve vacancy_id from --id mode ─────────────────────────────────────
    resolved_vacancy_id: int | None = vacancy_id

    # ── Health check (only needed for URL fetch) ──────────────────────────────
    if "fetch" in phases and url and not file_path:
        print("🔍  Checking jd-parser health…")
        if not await parser.health():
            print(f"❌  jd-parser unreachable at {settings.parser_url}")
            print("    Start it: docker compose up jd-parser -d")
            sys.exit(1)
        print("✅  jd-parser healthy\n")

    # ── Phase: fetch (URL mode) ───────────────────────────────────────────────
    if "fetch" in phases and url and not file_path and resolved_vacancy_id is None:
        print("📄  Phase: cv_fetch_jd")
        from tools.cv_fetch_jd import cv_fetch_jd
        result = await cv_fetch_jd(ctx, url)  # type: ignore[arg-type]
        print(f"\n--- cv_fetch_jd result ---\n{result}\n")

        from db.database import get_vacancy_by_url
        row = await get_vacancy_by_url(url)
        if row:
            resolved_vacancy_id = row["id"]
            print(f"  DB vacancy_id: #{resolved_vacancy_id}\n")

    # ── Phase: fetch (file mode) ──────────────────────────────────────────────
    elif "fetch" in phases and file_path:
        print(f"📄  Phase: load JD from file — {file_path}")
        if not file_path.exists():
            print(f"❌  File not found: {file_path}")
            sys.exit(1)
        content = file_path.read_text(encoding="utf-8")
        # Extract title from first # heading
        title = "Vacancy"
        for line in content.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        synthetic_url = f"file://{file_path.resolve()}"
        from db.database import insert_vacancy, get_vacancy_by_url
        existing = await get_vacancy_by_url(synthetic_url)
        if existing:
            resolved_vacancy_id = existing["id"]
            print(f"  Already in DB: vacancy_id=#{resolved_vacancy_id}\n")
        else:
            resolved_vacancy_id = await insert_vacancy(
                url=synthetic_url,
                title=title,
                markdown_path=str(file_path.resolve()),
                user_id=1,
            )
            print(f"  Inserted into DB: vacancy_id=#{resolved_vacancy_id}\n")

    # ── --id mode: vacancy already in DB ─────────────────────────────────────
    elif resolved_vacancy_id is not None:
        from db.database import get_vacancy_by_id
        row = await get_vacancy_by_id(resolved_vacancy_id)
        if not row:
            print(f"❌  Vacancy #{resolved_vacancy_id} not found in DB")
            sys.exit(1)
        print(f"📂  Using existing vacancy #{resolved_vacancy_id}: {row['title'] or row['url']}\n")

    def _require_vacancy_id(phase_name: str) -> int:
        if resolved_vacancy_id is None:
            print(f"❌  No vacancy_id — run 'fetch' phase first or use --id")
            sys.exit(1)
        return resolved_vacancy_id

    # ── Phase: analyze ────────────────────────────────────────────────────────
    if "analyze" in phases:
        vid = _require_vacancy_id("analyze")
        print(f"🔬  Phase: cv_analyze (vacancy #{vid})")
        from tools.cv_analyze import cv_analyze
        result = await cv_analyze(ctx, vid)  # type: ignore[arg-type]
        print(f"\n--- cv_analyze result ---\n{result}\n")

    # ── Phase: generate ───────────────────────────────────────────────────────
    if "generate" in phases:
        vid = _require_vacancy_id("generate")
        print(f"📝  Phase: cv_generate (vacancy #{vid})")
        from tools.cv_generate import cv_generate
        result = await cv_generate(ctx, vid)  # type: ignore[arg-type]
        print(f"\n--- cv_generate result ---\n{result}\n")

    # ── Phase: cover ──────────────────────────────────────────────────────────
    if "cover" in phases:
        vid = _require_vacancy_id("cover")
        print(f"✉️   Phase: cv_cover (vacancy #{vid})")
        from tools.cv_cover import cv_cover
        result = await cv_cover(ctx, vid)  # type: ignore[arg-type]
        print(f"\n--- cv_cover result ---\n{result}\n")

    # ── Session cost summary ──────────────────────────────────────────────────
    s = getattr(llm, 'session_summary', None)
    if s and s.get("calls", 0) > 0:
        print(f"\n💰  Session cost: {s['calls']} calls | "
              f"in={s['input_tokens']} out={s['output_tokens']} "
              f"cache_write={s['cache_write_tokens']} cache_read={s['cache_read_tokens']} "
              f"| total=${s['cost_usd']:.4f}")

    print("\n✅  e2e test complete")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="End-to-end pipeline test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Input modes (mutually exclusive):
  --url URL       fetch from web (default if nothing specified)
  --file PATH.md  read JD from local file, skip fetch
  --id N          reprocess existing DB vacancy by ID, skip fetch

Examples:
  python scripts/e2e_test.py
  python scripts/e2e_test.py --url https://djinni.co/jobs/123/
  python scripts/e2e_test.py --file vacancies/djinni/2026-06/123/JD.md
  python scripts/e2e_test.py --id 42
  python scripts/e2e_test.py --id 42 --phase generate,cover
        """,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--url", default=None, help="Vacancy URL to process")
    group.add_argument("--file", dest="file_path", default=None, metavar="PATH",
                       help="Path to JD .md file (skips fetch phase)")
    group.add_argument("--id", dest="vacancy_id", type=int, default=None, metavar="N",
                       help="Existing DB vacancy ID (skips fetch phase)")
    parser.add_argument("--user-id", dest="user_id", type=int, default=1,
                        help="career-agent DB user_id (default: 1)")
    parser.add_argument("--profile", default=None, metavar="PATH",
                        help="Path to PROFILE.md (overrides PROFILE_MD_PATH from .env)")
    parser.add_argument("--auto-confirm", dest="auto_confirm", action="store_true",
                        help="Auto-confirm all testing-mode API prompts (use only after explicit user approval)")
    parser.add_argument(
        "--phase",
        default=None,
        help="Comma-separated phases: fetch,analyze,generate,cover "
             "(default: fetch,analyze for URL; analyze,generate,cover for file/id)",
    )
    args = parser.parse_args()

    # Defaults
    file_path = Path(args.file_path) if args.file_path else None
    url = args.url or (_DEFAULT_URL if not file_path and args.vacancy_id is None else None)

    if args.phase:
        phases = [p.strip() for p in args.phase.split(",")]
    elif file_path or args.vacancy_id is not None:
        phases = ["analyze", "generate", "cover"]
    else:
        phases = ["fetch", "analyze"]

    profile_path = Path(args.profile) if args.profile else None

    asyncio.run(run_e2e(
        url=url,
        phases=phases,
        file_path=file_path,
        vacancy_id=args.vacancy_id,
        user_id=args.user_id,
        profile_path=profile_path,
        auto_confirm=args.auto_confirm,
    ))


if __name__ == "__main__":
    main()
