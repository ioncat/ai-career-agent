#!/usr/bin/env python3
"""
scripts/ollama_model_bench.py — manual Ollama model comparison per pipeline phase.

Runs one phase prompt (phase1_analysis.md, phase2_fit.md, phase3_cv_draft.md, ...)
against several local Ollama models, saves each model's raw output + timing/usage
metadata to disk for side-by-side reading. Nothing is written to the DB.

USAGE
-----
    # Phase 1 on a JD file, three models
    python scripts/ollama_model_bench.py --phase phase1_analysis \
        --jd "vacancies/inbox/1/859 — AI Project Manager — Nak Oranta/JD.md" \
        --models qwen2.5:32b,llama3.3:70b,qwen3:30b

    # Phase 2 — needs JD + Phase 1 output. Point at an existing vacancy folder
    # and it will read JD.md + JD_analysis.md's Phase 1 section automatically.
    python scripts/ollama_model_bench.py --phase phase2_fit \
        --vacancy-dir "vacancies/inbox/1/859 — AI Project Manager — Nak Oranta" \
        --models qwen2.5:32b,llama3.3:70b

    # Any phase — supply the exact user-turn text yourself
    python scripts/ollama_model_bench.py --phase phase3_cv_draft \
        --user-file scratch/phase3_input.txt --models qwen2.5:32b

Options:
    --phase NAME        Prompt filename stem in prompts/[skill_type]/ (required)
    --skill-type NAME    Default: read from active user's PROFILE.md Settings
    --user-id ID         Default: read from skill/active_user
    --jd PATH             JD.md — used as the user turn verbatim (phase1-style)
    --vacancy-dir PATH   Vacancy folder — auto-builds JD + prior-phase user turn
    --user-file PATH      Raw text file used as the user turn verbatim
    --models CSV          Comma-separated Ollama model tags (required)
    --effort LEVEL        off|low|medium|high|xhigh|max (default: off)
    --num-ctx N           Explicit context window (default: model's own default)
    --max-tokens N        num_predict (default: 4096)
    --out-dir PATH         Default: vacancies/_ollama_bench/<phase>/<timestamp>/

OUTPUT
------
For each model, writes:
    <out-dir>/<model-sanitized>.md     — raw completion text
    <out-dir>/<model-sanitized>.json   — usage/timing/thinking metadata
    <out-dir>/summary.md               — comparison table across all models run
"""

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env", override=True)
except ImportError:
    pass

from core.llm_client import OllamaProvider, LLMError  # noqa: E402
from core.settings import load_settings  # noqa: E402


def _sanitize(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", model)


def _active_user_id() -> str:
    p = _ROOT / "skill" / "active_user"
    return p.read_text(encoding="utf-8").strip() if p.exists() else "1"


def _profile_path(user_id: str) -> Path:
    return _ROOT / "skill" / "users" / user_id / "PROFILE.md"


def _read_settings_field(profile_md: str, field: str, default: str) -> str:
    m = re.search(rf"^{field}:\s*(\S+)", profile_md, re.MULTILINE)
    return m.group(1) if m else default


def _extract_phase1_section(jd_analysis_md: str) -> str:
    """Pull everything from '### 1.0 Vacancy Header' (or start) up to '## Fit Breakdown'."""
    m = re.search(r"(### 1\.0 Vacancy Header.*?)(?=\n## Fit Breakdown)", jd_analysis_md, re.DOTALL)
    if m:
        return m.group(1).strip()
    return jd_analysis_md  # fallback: whole file


def build_user_turn(args, phase: str) -> str:
    if args.user_file:
        return Path(args.user_file).read_text(encoding="utf-8")

    if args.jd:
        return Path(args.jd).read_text(encoding="utf-8")

    if args.vacancy_dir:
        vdir = Path(args.vacancy_dir)
        jd_text = (vdir / "JD.md").read_text(encoding="utf-8")
        if phase == "phase1_analysis":
            return jd_text
        analysis_path = vdir / "JD_analysis.md"
        if not analysis_path.exists():
            raise SystemExit(f"phase requires JD_analysis.md (Phase 1 output) — not found: {analysis_path}")
        phase1_section = _extract_phase1_section(analysis_path.read_text(encoding="utf-8"))
        return f"{jd_text}\n\n---\n\nPhase 1 Analysis:\n\n{phase1_section}"

    raise SystemExit("Provide one of --jd / --vacancy-dir / --user-file")


async def run_one(model: str, system_prompt: str, profile_md: str, user_turn: str,
                   base_url: str, effort: str, num_ctx: int | None, max_tokens: int,
                   timeout: int, out_dir: Path) -> dict:
    llm = OllamaProvider(
        base_url=base_url, model=model, profile_md=profile_md,
        max_tokens=max_tokens, timeout=timeout, effort=effort, num_ctx=num_ctx,
    )
    print(f"→ running {model} ...")
    t0 = time.monotonic()
    try:
        text = await llm.complete(user_turn, system=system_prompt)
        elapsed = time.monotonic() - t0
    except LLMError as exc:
        elapsed = time.monotonic() - t0
        print(f"  ✗ {model} failed after {elapsed:.1f}s: {exc}")
        return {"model": model, "ok": False, "error": str(exc), "elapsed_s": round(elapsed, 1)}

    stem = _sanitize(model)
    (out_dir / f"{stem}.md").write_text(text, encoding="utf-8")
    meta = {
        "model": model,
        "ok": True,
        "elapsed_s": round(elapsed, 1),
        "usage": llm.last_call_usage,
        "thinking": llm.last_thinking,
    }
    (out_dir / f"{stem}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ {model} done in {elapsed:.1f}s — {len(text)} chars"
          + (" (with reasoning trace)" if llm.last_thinking else ""))
    return meta


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", required=True, help="prompt filename stem, e.g. phase1_analysis")
    ap.add_argument("--skill-type", default=None)
    ap.add_argument("--user-id", default=None)
    ap.add_argument("--jd", default=None)
    ap.add_argument("--vacancy-dir", default=None)
    ap.add_argument("--user-file", default=None)
    ap.add_argument("--models", required=True, help="comma-separated Ollama model tags")
    ap.add_argument("--effort", default="off")
    ap.add_argument("--num-ctx", type=int, default=None)
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    settings = load_settings()
    user_id = args.user_id or _active_user_id()
    profile_md = _profile_path(user_id).read_text(encoding="utf-8")
    skill_type = args.skill_type or _read_settings_field(profile_md, "skill_type", "pm")

    prompt_path = _ROOT / "prompts" / skill_type / f"{args.phase}.md"
    if not prompt_path.exists():
        raise SystemExit(f"Prompt not found: {prompt_path}")
    system_prompt = prompt_path.read_text(encoding="utf-8")

    user_turn = build_user_turn(args, args.phase)

    out_dir = Path(args.out_dir) if args.out_dir else (
        _ROOT / "vacancies" / "_ollama_bench" / args.phase / datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "_input_user_turn.md").write_text(user_turn, encoding="utf-8")
    (out_dir / "_input_system_prompt.md").write_text(system_prompt, encoding="utf-8")

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    print(f"Phase: {args.phase} · skill_type={skill_type} · models={models}")
    print(f"Output → {out_dir}\n")

    results = []
    for model in models:
        r = await run_one(
            model, system_prompt, profile_md, user_turn,
            base_url=settings.ollama_base_url, effort=args.effort, num_ctx=args.num_ctx,
            max_tokens=args.max_tokens, timeout=settings.ollama_timeout, out_dir=out_dir,
        )
        results.append(r)

    lines = [f"# Ollama bench — {args.phase}", "", f"skill_type: {skill_type}  ·  effort: {args.effort}", "",
             "| Model | Status | Elapsed | In | Out | Thinking |",
             "|---|---|---|---|---|---|"]
    for r in results:
        if r["ok"]:
            u = r["usage"] or {}
            lines.append(
                f"| {r['model']} | ✅ | {r['elapsed_s']}s | {u.get('input_tokens', 0)} "
                f"| {u.get('output_tokens', 0)} | {'yes' if r['thinking'] else 'no'} |"
            )
        else:
            lines.append(f"| {r['model']} | ❌ | {r['elapsed_s']}s | — | — | {r['error'][:60]} |")
    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"\nSummary → {out_dir / 'summary.md'}")


if __name__ == "__main__":
    asyncio.run(main())
