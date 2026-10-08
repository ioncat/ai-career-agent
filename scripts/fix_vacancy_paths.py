"""
scripts/fix_vacancy_paths.py — repair `vacancies.markdown_path` after a folder was renamed by hand.

The same rule the backend applies at startup (core/vacancy_paths.py), runnable on demand and
safe by default: a row is repaired only when exactly one folder `<vacancies>/inbox/<user_id>/{id} — *`
exists and holds a JD.md. Rows with several or no matching folder are listed, never guessed.

What it writes: ONLY `vacancies.markdown_path`, on the planned rows. Not `status`, not `updated_at`.

DRY-RUN by default: the plan is applied to a COPY of the database and every table and column of
the copy is diffed against the live DB; anything other than `markdown_path` changing on exactly
the planned rows is listed as unexpected (bulk-data rule). The live DB is opened read-only.
--apply takes a backup first (refuses to overwrite one), writes, then diffs the live DB against
that backup. Safe to re-run: rows with an existing path are not selected.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:  # run as `python scripts/fix_vacancy_paths.py`
    sys.path.insert(0, str(_ROOT))

from core.vacancy_paths import find_repairs  # noqa: E402
from scripts.analyzed_at_backfill import _connect_ro, diff_databases, snapshot  # noqa: E402


def read_rows(db_path: Path) -> list[dict]:
    con = _connect_ro(db_path)
    try:
        cur = con.execute(
            "SELECT id, user_id, markdown_path FROM vacancies "
            "WHERE markdown_path IS NOT NULL AND markdown_path != '' ORDER BY id")
        return [dict(r) for r in cur.fetchall()]
    finally:
        con.close()


def apply_repairs(db_path: Path, repairs: list[dict]) -> None:
    """Only `markdown_path` (see the module docstring)."""
    con = sqlite3.connect(db_path)
    try:
        con.executemany("UPDATE vacancies SET markdown_path = ? WHERE id = ?",
                        [(r["new"], r["id"]) for r in repairs])
        con.commit()
    finally:
        con.close()


def unexpected_changes(diff: dict[str, dict], repairs: list[dict]) -> list[str]:
    expected = {r["id"] for r in repairs}
    problems: list[str] = []
    for table, d in diff.items():
        if d["added"]:
            problems.append(f"{table}: {len(d['added'])} rows added")
        if d["removed"]:
            problems.append(f"{table}: {len(d['removed'])} rows removed")
        for rid, cols in d["changed"].items():
            if table == "vacancies" and cols == ["markdown_path"]:
                continue
            problems.append(f"{table} rowid {rid}: columns changed {cols}")
    changed = set(diff.get("vacancies", {}).get("changed", {}))
    if changed != expected:
        problems.append(f"vacancies changed {sorted(changed)}, planned {sorted(expected)}")
    return problems


def build_report(*, mode: str, repairs: list[dict], unresolved: list[dict],
                 diff: dict[str, dict], problems: list[str]) -> str:
    lines = [f"# vacancy path repair — {mode}", ""]
    lines.append(f"- rows to repair: **{len(repairs)}**")
    lines.append(f"- left alone, no single matching folder or no JD.md: **{len(unresolved)}** "
                 f"{[u['id'] for u in unresolved]}")
    lines += ["", "## Full diff, every table and column (live DB vs copy/backup)", ""]
    if not diff:
        lines.append("no differences")
    for t, d in diff.items():
        cols = sorted({c for cs in d["changed"].values() for c in cs})
        lines.append(f"- `{t}`: {len(d['added'])} added, {len(d['removed'])} removed, "
                     f"{len(d['changed'])} changed (columns: {cols})")
    lines += ["", "## Unexpected changes", ""]
    lines += [f"- {p}" for p in problems] or ["none"]
    if repairs:
        lines += ["", "## Repairs", "", "| vacancy | old path | new path |", "|---|---|---|"]
        lines += [f"| #{r['id']} | {r['old']} | {r['new']} |" for r in repairs]
    if unresolved:
        lines += ["", "## Left alone", ""]
        lines += [f"- #{u['id']}: {u['reason']} (path: {u['old']})" for u in unresolved]
    return "\n".join(lines) + "\n"


def run(db_path: Path, *, apply: bool, vacancies_root: Path | None = None, project_root: Path = _ROOT,
        backup_dir: Path | None = None, report_path: Path | None = None) -> dict:
    db_path = Path(db_path)
    vacancies_root = Path(vacancies_root) if vacancies_root else project_root / "vacancies"
    repairs, unresolved = find_repairs(read_rows(db_path), vacancies_root, project_root)
    if apply:
        backup_dir = backup_dir or db_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"{db_path.name}.bak-{datetime.now():%Y-%m-%d_%H%M%S}-pre-fix-vacancy-paths"
        snapshot(db_path, backup)
        apply_repairs(db_path, repairs)
        diff = diff_databases(backup, db_path)
        mode = "APPLIED"
    else:
        backup = None
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "copy.db"
            snapshot(db_path, copy)
            apply_repairs(copy, repairs)
            diff = diff_databases(db_path, copy)
        mode = "DRY RUN (applied to a copy; live DB untouched)"
    problems = unexpected_changes(diff, repairs)
    report = build_report(mode=mode, repairs=repairs, unresolved=unresolved, diff=diff, problems=problems)
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
    return {"repairs": repairs, "unresolved": unresolved, "diff": diff, "problems": problems,
            "backup": backup, "report": report}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(_ROOT / "db" / "agent.db"), help="Path to agent.db")
    ap.add_argument("--vacancies", default=None, help="Vacancies folder (default: <project>/vacancies)")
    ap.add_argument("--apply", action="store_true",
                    help="back up, then WRITE the repairs (default: dry run on a copy)")
    ap.add_argument("--report", default=None, help="where to write the report (default: research/)")
    args = ap.parse_args()

    stamp = datetime.now().strftime("%Y-%m-%d")
    kind = "apply" if args.apply else "dryrun"
    report_path = Path(args.report) if args.report else _ROOT / "research" / f"fix-vacancy-paths-{kind}-{stamp}.md"
    res = run(Path(args.db), apply=args.apply,
              vacancies_root=Path(args.vacancies) if args.vacancies else None, report_path=report_path)
    print(res["report"].split("## Repairs")[0].split("## Left alone")[0])
    if res["backup"]:
        print(f"backup: {res['backup']}")
    print(f"full report: {report_path}")
    if not args.apply:
        print("dry run — live DB untouched (use --apply to write)")
    if res["problems"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
