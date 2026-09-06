"""
scripts/backfill_role_balance_taxonomy.py — one-off backfill for the
2026-09-06 role_balance taxonomy rename.

Renames legacy role_balance keys in analysis_json.p1 to their canonical
2026-09-06 names (execution -> delivery, coordination -> stakeholder,
ops -> operational). Does NOT add a "growth" value to historical rows —
there is no way to derive it retroactively without re-running Phase 1.

Read-only by default; pass --apply to write changes.
See docs/discovery/role-balance-taxonomy-discovery-2026-09-06.md for the
full methodology behind the rename. contracts/pipeline.py already
normalizes these aliases on read (permanent safety net, not dependent on
this backfill) — this script is for data hygiene of the stored JSON itself,
so direct SQL/script consumers (not just the Pydantic-validated API path)
see canonical names too.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "db" / "agent.db"

ALIASES = {
    "execution": "delivery",
    "coordination": "stakeholder",
    "ops": "operational",
}


def normalize(role_balance: dict) -> tuple[dict, bool]:
    """Return (normalized_dict, changed) — changed=False if already canonical."""
    normalized: dict = {}
    changed = False
    for key, val in role_balance.items():
        canonical = ALIASES.get(key, key)
        if canonical != key:
            changed = True
        if canonical in normalized:
            continue
        normalized[canonical] = val
    return normalized, changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    args = parser.parse_args()

    db = sqlite3.connect(DB_PATH)
    rows = db.execute(
        "SELECT id, analysis_json FROM vacancies WHERE analysis_json IS NOT NULL"
    ).fetchall()

    touched = 0
    skipped_no_rb = 0
    for vid, aj_str in rows:
        try:
            aj = json.loads(aj_str)
        except (json.JSONDecodeError, TypeError):
            continue
        p1 = aj.get("p1")
        if not p1 or "role_balance" not in p1:
            skipped_no_rb += 1
            continue
        normalized, changed = normalize(p1["role_balance"])
        if not changed:
            continue
        touched += 1
        if args.apply:
            p1["role_balance"] = normalized
            db.execute(
                "UPDATE vacancies SET analysis_json = ? WHERE id = ?",
                (json.dumps(aj, ensure_ascii=False), vid),
            )
        else:
            print(f"#{vid}: {p1['role_balance']} -> {normalized}")

    if args.apply:
        db.commit()
        print(f"\nApplied: {touched} vacancies updated.")
    else:
        print(f"\nDry run: {touched} vacancies would be updated (no changes written).")
        print("Re-run with --apply to write.")
    print(f"Vacancies with p1 but no role_balance at all: {skipped_no_rb} (untouched, unrelated).")

    db.close()


if __name__ == "__main__":
    main()
