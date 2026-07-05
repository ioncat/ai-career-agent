"""
scripts/profile_merge.py — Merge Phase 2.5 evidence into progressive_profile via LLM.

Usage:
    python scripts/profile_merge.py --user-id 1 --evidence-file /path/to/evidence.txt
    python scripts/profile_merge.py --user-id 1 --evidence "Resolved: managed 12-person team..."

Called automatically by SKILL.md after Phase 2.5 completes.
Uses claude CLI (LLM_PROVIDER=claude_cli) — no API key cost.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
_PROMPT_PATH = _PROJECT_ROOT / "prompts" / "pm" / "phase2_5_writeback.md"

# DB access via sqlite3 directly (no asyncio needed in a script)
import sqlite3

def _get_db_path() -> Path:
    try:
        from dotenv import load_dotenv
        load_dotenv(_PROJECT_ROOT / ".env")
    except ImportError:
        pass
    import os
    return Path(os.getenv("DB_PATH", str(_PROJECT_ROOT / "db" / "agent.db")))


def _load_profile(user_id: int) -> dict:
    db_path = _get_db_path()
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        row = con.execute("SELECT progressive_profile FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            print(f"[profile_merge] User {user_id} not found in DB", file=sys.stderr)
            sys.exit(1)
        pp = row["progressive_profile"]
        return json.loads(pp) if pp else {"meta": {}, "roles": []}
    finally:
        con.close()


def _save_profile(user_id: int, profile: dict) -> None:
    db_path = _get_db_path()
    con = sqlite3.connect(str(db_path))
    try:
        con.execute(
            "UPDATE users SET progressive_profile = ? WHERE id = ?",
            (json.dumps(profile, ensure_ascii=False, indent=2), user_id),
        )
        con.commit()
    finally:
        con.close()


def _call_llm(system: str, user: str) -> str:
    """Call claude CLI subprocess and return output text."""
    import os
    timeout = int(os.getenv("CLAUDE_CLI_TIMEOUT", "300"))
    cmd = ["claude", "-p", user, "--system-prompt", system]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(_PROJECT_ROOT),
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI failed (exit {result.returncode}): {result.stderr[:300]}")
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge Phase 2.5 evidence into progressive_profile")
    parser.add_argument("--user-id", type=int, default=1)
    parser.add_argument("--evidence", type=str, default="", help="Evidence text inline")
    parser.add_argument("--evidence-file", type=str, default="", help="Path to evidence text file")
    parser.add_argument("--dry-run", action="store_true", help="Print merged JSON, don't save")
    args = parser.parse_args()

    # Load evidence
    if args.evidence_file:
        evidence_text = Path(args.evidence_file).read_text(encoding="utf-8").strip()
    elif args.evidence:
        evidence_text = args.evidence.strip()
    else:
        print("[profile_merge] Error: provide --evidence or --evidence-file", file=sys.stderr)
        sys.exit(1)

    if not evidence_text:
        print("[profile_merge] Error: evidence is empty", file=sys.stderr)
        sys.exit(1)

    # Load current profile
    current_profile = _load_profile(args.user_id)
    print(f"[profile_merge] Loaded profile: {len(current_profile.get('roles', []))} roles")

    # Build LLM input
    system_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    user_message = (
        f"## Current Profile JSON\n\n"
        f"```json\n{json.dumps(current_profile, ensure_ascii=False, indent=2)}\n```\n\n"
        f"---\n\n"
        f"## New Evidence (Phase 2.5 Resolved Objections)\n\n"
        f"{evidence_text}"
    )

    print("[profile_merge] Calling LLM to merge evidence...")
    try:
        raw_output = _call_llm(system_prompt, user_message)
    except RuntimeError as exc:
        print(f"[profile_merge] LLM error: {exc}", file=sys.stderr)
        sys.exit(1)

    # Parse JSON from output (strip possible markdown fences)
    json_text = raw_output
    if "```json" in json_text:
        start = json_text.index("```json") + 7
        end = json_text.index("```", start)
        json_text = json_text[start:end].strip()
    elif "```" in json_text:
        start = json_text.index("```") + 3
        end = json_text.index("```", start)
        json_text = json_text[start:end].strip()

    try:
        updated_profile = json.loads(json_text)
    except json.JSONDecodeError as exc:
        print(f"[profile_merge] Failed to parse LLM output as JSON: {exc}", file=sys.stderr)
        print("[profile_merge] Raw output:", file=sys.stderr)
        print(raw_output[:500], file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print("[profile_merge] DRY RUN — updated profile:")
        print(json.dumps(updated_profile, ensure_ascii=False, indent=2))
        return

    _save_profile(args.user_id, updated_profile)
    roles_count = len(updated_profile.get("roles", []))
    print(f"[profile_merge] ✅ Saved — {roles_count} roles in profile")


if __name__ == "__main__":
    main()
