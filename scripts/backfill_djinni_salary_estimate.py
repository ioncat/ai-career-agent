#!/usr/bin/env python3
"""
scripts/backfill_djinni_salary_estimate.py — Estimate real (undisclosed)
salary for Djinni vacancies via services/parser's public search-filter
probe (see services/parser/salary_probe.py for the technique).

Scope: site='djinni', salary IS NULL/empty, status != 'declined' — Archive
is deliberately excluded, same precedent as every prior salary/company
backfill in this project (already-declined vacancies get no further value
from an estimate). Re-run later to cover newly-analyzed vacancies; already
has a real `salary` or is declined → skipped automatically by the query.

Sequential, one vacancy at a time — jd-parser's own probe already spaces
its requests out (crawler.fetch()'s polite delay), running vacancies
concurrently here would defeat that. ~15-35s per vacancy is expected and
fine — this is an offline backfill, not a user-facing wait.

USAGE
-----
    python scripts/backfill_djinni_salary_estimate.py --dry-run   # preview, no writes
    python scripts/backfill_djinni_salary_estimate.py             # write results

Back up db/agent.db before running for real — this writes to the `salary`
column directly.
"""

import argparse
import asyncio
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.djinni_salary_adapter import DjinniSalaryAdapter  # noqa: E402
from core.settings import load_settings  # noqa: E402
from db import database  # noqa: E402

_ESTIMATE_FMT = "~${ceiling}+ (Djinni filter estimate)"


def _candidates(db_path: str) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """
            SELECT id, title, url FROM vacancies
            WHERE site = 'djinni' AND (salary IS NULL OR salary = '') AND status != 'declined'
            ORDER BY id
            """
        )
        return cur.fetchall()
    finally:
        conn.close()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print results, write nothing")
    args = parser.parse_args()

    settings = load_settings()
    rows = _candidates(settings.db_path)
    if not rows:
        print("No candidates — nothing to do.")
        return

    print(f"{len(rows)} candidate(s) — {'DRY RUN, no writes' if args.dry_run else 'WILL WRITE to salary column'}\n")

    adapter = DjinniSalaryAdapter(base_url=settings.parser_url)
    determined = 0
    for row in rows:
        print(f"#{row['id']:>5}  {row['title'][:60]:<60}", end="  ", flush=True)
        ceiling = await adapter.find_salary_ceiling(row["url"])
        if ceiling is None:
            print("undetermined")
            continue
        determined += 1
        estimate = _ESTIMATE_FMT.format(ceiling=ceiling)
        print(estimate)
        if not args.dry_run:
            await database.set_vacancy_salary(row["id"], estimate)

    print(f"\n{determined}/{len(rows)} determined" + (" (dry run — nothing written)" if args.dry_run else " — written"))


if __name__ == "__main__":
    asyncio.run(main())
