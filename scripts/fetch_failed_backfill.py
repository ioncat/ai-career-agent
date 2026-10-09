"""
scripts/fetch_failed_backfill.py — move vacancies that RSSWatcher gave up fetching from
status 'declined' (Archive) to status 'fetch_failed' (stays in Inbox, marked as failed).

Why: `database.give_up_fetch()` used to write status='declined'; it now writes
'fetch_failed' so a vacancy without a JD is not silently archived. Rows given up before
that change still sit in Archive.

Which rows: ONLY those that match all of these, so a deliberately declined or imported
vacancy is never touched:
  - status = 'declined'
  - analysis_error starts with 'Fetch failed ' (the text give_up_fetch writes)
  - no markdown_path (the JD was never fetched), no analysis_json, applied = 0
Old declined rows without a JD but with no such error (imported tracker rows) do not match.

What it writes: `vacancies.status` -> 'fetch_failed' and `vacancies.declined_at` -> NULL on
the matched rows. Nothing else; in particular not `updated_at` (kept as it was).

DRY-RUN by default: the plan is applied to a COPY of the database and every table and
column of the copy is diffed against the live DB; anything other than status/declined_at
changing on exactly the planned rows is listed as unexpected (bulk-data rule). The live DB
is opened read-only. --apply takes a backup first, writes, then diffs the live DB against
that backup. Safe to re-run: migrated rows are no longer 'declined'.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:  # run as `python scripts/fetch_failed_backfill.py`
    sys.path.insert(0, str(_ROOT))

from scripts.analyzed_at_backfill import _connect_ro, diff_databases, snapshot  # noqa: E402

_ALLOWED_COLUMNS = {"status", "declined_at"}


def read_rows(db_path: Path) -> list[dict]:
    con = _connect_ro(db_path)
    try:
        cur = con.execute(
            "SELECT id, status, site, applied, declined_at, fetch_attempts, analysis_error "
            "FROM vacancies "
            "WHERE status = 'declined' AND analysis_error LIKE 'Fetch failed %' "
            "AND (markdown_path IS NULL OR markdown_path = '') "
            "AND analysis_json IS NULL AND applied = 0 ORDER BY id")
        return [dict(r) for r in cur.fetchall()]
    finally:
        con.close()


def apply_updates(db_path: Path, rows: list[dict]) -> None:
    """Only `status` and `declined_at`; never `updated_at` (see the module docstring)."""
    con = sqlite3.connect(db_path)
    try:
        con.executemany(
            "UPDATE vacancies SET status = 'fetch_failed', declined_at = NULL "
            "WHERE id = ? AND status = 'declined'", [(r["id"],) for r in rows])
        con.commit()
    finally:
        con.close()


def unexpected_changes(diff: dict[str, dict], rows: list[dict]) -> list[str]:
    expected = {r["id"] for r in rows}
    problems: list[str] = []
    for table, d in diff.items():
        if d["added"]:
            problems.append(f"{table}: {len(d['added'])} rows added")
        if d["removed"]:
            problems.append(f"{table}: {len(d['removed'])} rows removed")
        for rid, cols in d["changed"].items():
            if table == "vacancies" and set(cols) <= _ALLOWED_COLUMNS:
                continue
            problems.append(f"{table} rowid {rid}: columns changed {cols}")
    changed = set(diff.get("vacancies", {}).get("changed", {}))
    if changed != expected:
        problems.append(f"vacancies changed {sorted(changed)}, planned {sorted(expected)}")
    return problems


def build_report(*, mode: str, rows: list[dict], diff: dict[str, dict], problems: list[str]) -> str:
    lines = [f"# fetch_failed backfill — {mode}", "", f"- rows to move: **{len(rows)}**"]
    lines += ["", "## Full diff, every table and column (live DB vs copy/backup)", ""]
    if not diff:
        lines.append("no differences")
    for t, d in diff.items():
        cols = sorted({c for cs in d["changed"].values() for c in cs})
        lines.append(f"- `{t}`: {len(d['added'])} added, {len(d['removed'])} removed, "
                     f"{len(d['changed'])} changed (columns: {cols})")
    lines += ["", "## Unexpected changes", ""]
    lines += [f"- {p}" for p in problems] or ["none"]
    lines += ["", "## Rows", "", "| vacancy | site | attempts | error |", "|---|---|---|---|"]
    lines += [f"| #{r['id']} | {r['site']} | {r['fetch_attempts']} | "
              f"{(r['analysis_error'] or '').splitlines()[0][:80]} |" for r in rows]
    return "\n".join(lines) + "\n"


def run(db_path: Path, *, apply: bool, backup_dir: Path | None = None,
        report_path: Path | None = None) -> dict:
    db_path = Path(db_path)
    rows = read_rows(db_path)
    if apply:
        backup_dir = backup_dir or db_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"{db_path.name}.bak-{datetime.now():%Y-%m-%d_%H%M%S}-pre-fetch-failed-backfill"
        snapshot(db_path, backup)
        apply_updates(db_path, rows)
        diff = diff_databases(backup, db_path)
        mode = "APPLIED"
    else:
        backup = None
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "copy.db"
            snapshot(db_path, copy)
            apply_updates(copy, rows)
            diff = diff_databases(db_path, copy)
        mode = "DRY RUN (applied to a copy; live DB untouched)"
    problems = unexpected_changes(diff, rows)
    report = build_report(mode=mode, rows=rows, diff=diff, problems=problems)
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
    return {"rows": rows, "diff": diff, "problems": problems, "backup": backup, "report": report}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(_ROOT / "db" / "agent.db"), help="Path to agent.db")
    ap.add_argument("--apply", action="store_true",
                    help="back up, then WRITE the changes (default: dry run on a copy)")
    ap.add_argument("--report", default=None, help="where to write the report (default: research/)")
    args = ap.parse_args()

    stamp = datetime.now().strftime("%Y-%m-%d")
    kind = "apply" if args.apply else "dryrun"
    report_path = Path(args.report) if args.report else _ROOT / "research" / f"fetch-failed-backfill-{kind}-{stamp}.md"
    res = run(Path(args.db), apply=args.apply, report_path=report_path)
    print(res["report"].split("## Rows")[0])
    if res["backup"]:
        print(f"backup: {res['backup']}")
    print(f"full report: {report_path}")
    if not args.apply:
        print("dry run — live DB untouched (use --apply to write)")
    if res["problems"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
