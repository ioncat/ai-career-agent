"""
scripts/company_profile_backfill.py — fill `vacancies.company_profile_url` for
existing DOU rows (company identity, 2026-10-05).

A DOU vacancy URL already contains the company's profile page:
`https://jobs.dou.ua/companies/{slug}/vacancies/{id}` -> `https://jobs.dou.ua/companies/{slug}/`
(same rule as services/parser `_extract_company_profile_url`). The parser
extracts it at fetch time for new vacancies; this script derives it for the
rows ingested before the column existed.

Only `site = 'dou'` rows with an empty `company_profile_url` and a URL of that
shape are touched. Djinni rows are NOT backfilled (its company link lives in
the page DOM and needs a re-fetch; they get it on their next fetch/re-fetch).
Import placeholders (`import://...`) and other shapes are reported as unmatched.

DRY-RUN by default (read-only, never modifies the DB — not even the schema).
--apply runs init_db() first (additive migration: the new column + the
company_profile_links table) and then fills the column. Take a DB backup before
using --apply.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from db import database  # noqa: E402

_DOU_PROFILE_RE = re.compile(r"^(https?://[^/]+/companies/[^/]+/)")
# DefTech category pages live on their own host with an extra "/jobs" segment
# (database.normalize_url treats deftech.dou.ua as the twin of jobs.dou.ua).
_DEFTECH_PROFILE_RE = re.compile(r"^https?://deftech\.dou\.ua/jobs/companies/([^/]+)/", re.IGNORECASE)


def derive_dou_profile_url(url: str | None) -> str | None:
    """`https://jobs.dou.ua/companies/{slug}/vacancies/1` -> the `/companies/{slug}/` URL.
    A `deftech.dou.ua/jobs/companies/{slug}/...` URL maps to the same company on jobs.dou.ua."""
    if not url:
        return None
    url = url.strip()
    m = _DOU_PROFILE_RE.match(url)
    if m:
        return m.group(1)
    m = _DEFTECH_PROFILE_RE.match(url)
    return f"https://jobs.dou.ua/companies/{m.group(1)}/" if m else None


def plan_updates(rows) -> tuple[list[tuple[int, str]], dict[str, int]]:
    """From rows with id, site, url, company_profile_url -> (updates, counts)."""
    updates: list[tuple[int, str]] = []
    counts = {"dou_rows": 0, "already_set": 0, "to_fill": 0, "unmatched": 0, "other_sites": 0}
    for r in rows:
        if r["site"] != "dou":
            counts["other_sites"] += 1
            continue
        counts["dou_rows"] += 1
        if r["company_profile_url"]:
            counts["already_set"] += 1
            continue
        derived = derive_dou_profile_url(r["url"])
        if derived is None:
            counts["unmatched"] += 1
            continue
        counts["to_fill"] += 1
        updates.append((r["id"], derived))
    return updates, counts


async def _read_rows() -> list[dict]:
    async with database.get_db() as db:
        cur = await db.execute("PRAGMA table_info(vacancies)")
        has_col = any(r["name"] == "company_profile_url" for r in await cur.fetchall())
        col = "company_profile_url" if has_col else "NULL AS company_profile_url"
        cur = await db.execute(f"SELECT id, site, url, {col} FROM vacancies ORDER BY id")
        return [dict(r) for r in await cur.fetchall()]


async def run(db_path: str | Path, apply: bool) -> dict[str, int]:
    database.configure(db_path)
    if apply:
        await database.init_db()  # additive migration (column + links table)
    rows = await _read_rows()
    updates, counts = plan_updates(rows)
    if apply and updates:
        async with database.get_db() as db:
            await db.executemany(
                "UPDATE vacancies SET company_profile_url = ? WHERE id = ? "
                "AND (company_profile_url IS NULL OR company_profile_url = '')",
                [(url, vid) for vid, url in updates],
            )
            await db.commit()
    counts["applied"] = len(updates) if apply else 0
    return counts


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(_ROOT / "db" / "agent.db"), help="Path to agent.db")
    ap.add_argument("--apply", action="store_true", help="WRITE the profile URLs (default: dry run)")
    args = ap.parse_args()

    counts = asyncio.run(run(args.db, args.apply))
    print(f"DOU rows: {counts['dou_rows']} (other sites skipped: {counts['other_sites']})")
    print(f"  already set: {counts['already_set']}")
    print(f"  derivable from url: {counts['to_fill']}")
    print(f"  unmatched (no /companies/{{slug}}/ in url): {counts['unmatched']}")
    if args.apply:
        print(f"applied {counts['applied']} rows")
    else:
        print("dry run — DB untouched (use --apply to write)")


if __name__ == "__main__":
    main()
