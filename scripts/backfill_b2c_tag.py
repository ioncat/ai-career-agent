"""
scripts/backfill_b2c_tag.py — one-off backfill for the 2026-09-08 "b2c" tag
addition to core/vacancy_tags.py's taxonomy.

Re-classifies every vacancy's JD.md against the current taxonomy and merges
"b2c" into the DB `tags` column wherever it applies — existing tags (manual
or previously auto-assigned) are preserved, never overwritten (merge_tags()
semantics, same as the live fetch path).

Read-only by default; pass --apply to write changes.
See core/vacancy_tags.py's "b2c added 2026-09-08" docstring note for the
full false-positive rationale behind the classifier itself.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.vacancy_tags import classify, merge_tags  # noqa: E402

DB_PATH = _ROOT / "db" / "agent.db"


def main() -> None:
    # Windows console defaults to cp1252 — vacancy titles routinely contain
    # Cyrillic/emoji and would otherwise crash the dry-run print loop.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH), help="Path to agent.db")
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    args = parser.parse_args()

    db = sqlite3.connect(args.db)
    rows = db.execute(
        "SELECT id, title, tags, markdown_path FROM vacancies "
        "WHERE markdown_path IS NOT NULL AND markdown_path != ''"
    ).fetchall()

    touched = 0
    missing_files = 0
    for vid, title, tags, path in rows:
        jd_path = Path(path)
        if not jd_path.exists():
            missing_files += 1
            continue
        jd_text = jd_path.read_text(encoding="utf-8", errors="replace")
        matched = classify(jd_text)
        if "b2c" not in matched:
            continue
        existing_tags = [t.strip().lower() for t in (tags or "").split(",") if t.strip()]
        if "b2c" in existing_tags:
            continue  # already tagged (e.g. re-run after a partial --apply)
        touched += 1
        new_tags = merge_tags(tags, ["b2c"])
        if args.apply:
            db.execute("UPDATE vacancies SET tags = ? WHERE id = ?", (new_tags, vid))
        else:
            print(f"#{vid} {title!r}: {tags!r} -> {new_tags!r}")

    if args.apply:
        db.commit()
        print(f"\nApplied: {touched} vacancies tagged b2c.")
    else:
        print(f"\nDry run: {touched} vacancies would be tagged b2c (no changes written).")
        print("Re-run with --apply to write.")
    print(f"Vacancies with no JD.md on disk (skipped): {missing_files}.")

    db.close()


if __name__ == "__main__":
    main()
