#!/usr/bin/env python3
"""
scripts/import_seen_jobs.py — Import seen_jobs.json from job-board-monitor into career-agent DB.

PURPOSE
-------
One-time or recurring import of vacancies seen by the original job-board-monitor Telegram bot
into the career-agent DB for tracking and pipeline processing.

Status inserted: 'new' — visible in tracker, not auto-processed by rss_watcher.py.
RSSWatcher only picks up status='queued'; 'new' sits until user triggers pipeline manually.

USAGE
-----
    # Import only today's vacancies (default user_id=1)
    python scripts/import_seen_jobs.py --today

    # Import all entries from custom path
    python scripts/import_seen_jobs.py --seen-jobs /path/to/seen_jobs.json

    # Dry run — see what would be imported without writing
    python scripts/import_seen_jobs.py --today --dry-run

    # Different user
    python scripts/import_seen_jobs.py --today --user-id 2

STATUS VALUES AFTER IMPORT
--------------------------
    new — in DB, not yet processed by career-agent pipeline.
    Use /analyze -v [id] to start pipeline for any imported vacancy.

EXIT CODES
----------
    0 — success (summary printed to stdout)
    1 — error   (message on stderr)
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env", override=True)
except ImportError:
    pass

from db import database

_DEFAULT_SEEN_JOBS = Path(r"E:\My files\0 My_Dev\my_prj\job-board-monitor\seen_jobs.json")
_IMPORT_STATUS = "new"


async def _import(
    seen_jobs_path: Path,
    user_id: int,
    today_only: bool,
    dry_run: bool,
) -> None:
    db_path = os.environ.get("DB_PATH", str(_ROOT / "db" / "agent.db"))
    database.configure(db_path)
    await database.init_db()

    data: dict = json.loads(seen_jobs_path.read_text(encoding="utf-8"))

    today_str = date.today().isoformat()
    imported = skipped_dup = skipped_date = 0

    for url, meta in data.items():
        first_seen: str = meta.get("first_seen", "")
        if today_only and not first_seen.startswith(today_str):
            skipped_date += 1
            continue

        title: str | None = meta.get("title") or None

        existing = await database.get_vacancy_by_url(url)
        if existing:
            skipped_dup += 1
            continue

        if dry_run:
            print(f"  [DRY] {title or url}")
            imported += 1
            continue

        try:
            vid = await database.insert_vacancy(
                url=url,
                title=title,
                user_id=user_id,
                status=_IMPORT_STATUS,
            )
            print(f"  #{vid}: {title or url}")
            imported += 1
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                skipped_dup += 1
            else:
                print(f"  ERROR {url}: {exc}", file=sys.stderr)

    tag = "[DRY RUN] " if dry_run else ""
    print(
        f"\n{tag}imported: {imported}  duplicate: {skipped_dup}  date-filtered: {skipped_date}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import seen_jobs.json from job-board-monitor into career-agent DB"
    )
    parser.add_argument(
        "--seen-jobs",
        type=Path,
        default=_DEFAULT_SEEN_JOBS,
        metavar="PATH",
        help="Path to seen_jobs.json (default: job-board-monitor repo)",
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=1,
        metavar="N",
        help="career-agent user_id to assign imported vacancies (default: 1)",
    )
    parser.add_argument(
        "--today",
        action="store_true",
        help="Only import entries whose first_seen date = today",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be imported without writing to DB",
    )
    args = parser.parse_args()

    if not args.seen_jobs.exists():
        print(f"Error: file not found: {args.seen_jobs}", file=sys.stderr)
        sys.exit(1)

    asyncio.run(
        _import(
            seen_jobs_path=args.seen_jobs,
            user_id=args.user_id,
            today_only=args.today,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
