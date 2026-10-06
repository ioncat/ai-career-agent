"""
scripts/analyzed_at_backfill.py — restore "analyzed on" dates for vacancies that
were analyzed but have no completed Phase 2 row in `pipeline_runs`.

Why: the Analytics screen shows when analyses happened. That date is the
`finished_at` of the latest successful `phase2` run (database.get_last_phase_completion).
207 vacancies carry a Phase 2 fit score, but 102 of them (the early ones, plus
those analyzed through the /analyze skill) have no such run row.

Source of the date: the last-modified time of the `JD_analysis.md` next to the
vacancy's `markdown_path`, converted to UTC (`pipeline_runs` stores UTC). Checked
against the vacancies that DO have a run row: median difference ~3 h, the report
prints the figures. NOT `vacancies.updated_at` — it is bumped by unrelated writes.

What it writes: ONE new `pipeline_runs` row per vacancy (phase='phase2',
status='done', finished_at = created_at = the file date, started_at NULL,
result_path = the analysis file). `started_at IS NULL` marks a backfilled row.
It never touches `vacancies` or any other table.

DRY-RUN by default: the plan is applied to a COPY of the database and every
table/column of the copy is diffed against the live DB; anything other than the
expected new `pipeline_runs` rows is listed as unexpected (Rule 11). The live DB
is opened read-only. --apply takes a backup first (refuses to overwrite one),
writes, then diffs the live DB against that backup and reports the same way.
Safe to re-run: vacancies that already have a done phase2 row are not selected.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import statistics
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

PHASE = "phase2"
ANALYSIS_FILE = "JD_analysis.md"


# ── pure helpers ──────────────────────────────────────────────────────────────

def has_fit_score(analysis_json: str | None) -> bool:
    """True when analysis_json carries a Phase 2 fit score (new or legacy shape)."""
    if not analysis_json:
        return False
    try:
        p2 = json.loads(analysis_json).get("p2") or {}
    except (ValueError, AttributeError):
        return False
    return isinstance(p2, dict) and p2.get("fit_score") is not None


def analysis_file_for(markdown_path: str | None, root: Path = _ROOT) -> Path | None:
    """`JD_analysis.md` beside the vacancy's JD, or None (no path / no such file).
    markdown_path is stored relative to the project root (or absolute)."""
    if not markdown_path:
        return None
    path = Path(markdown_path)
    if not path.is_absolute():
        path = root / path
    candidate = path.parent / ANALYSIS_FILE
    return candidate if candidate.is_file() else None


def file_date_utc(path: Path) -> str:
    """Last-modified time as a naive UTC 'YYYY-MM-DD HH:MM:SS' (the format
    pipeline_runs already uses). Independent of the machine's time zone."""
    dt = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def plan_inserts(rows, root: Path = _ROOT) -> tuple[list[dict], dict[str, list[int]]]:
    """rows: dicts with id, markdown_path, analysis_json, created_at, has_run.
    Returns (inserts, skipped) where skipped maps a reason to vacancy ids."""
    inserts: list[dict] = []
    skipped: dict[str, list[int]] = {"no_path": [], "no_file": []}
    for r in rows:
        if r["has_run"] or not has_fit_score(r["analysis_json"]):
            continue
        if not r["markdown_path"]:
            skipped["no_path"].append(r["id"])
            continue
        f = analysis_file_for(r["markdown_path"], root)
        if f is None:
            skipped["no_file"].append(r["id"])
            continue
        try:  # same convention as vacancies.markdown_path: relative to the project root
            result_path = str(f.relative_to(root))
        except ValueError:
            result_path = str(f)
        inserts.append({
            "vacancy_id": r["id"],
            "finished_at": file_date_utc(f),
            "result_path": result_path,
            "created_at": r["created_at"],
        })
    return inserts, skipped


# ── database access (plain sqlite3, one-off script) ───────────────────────────

def _connect_ro(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def read_rows(db_path: Path) -> list[dict]:
    con = _connect_ro(db_path)
    try:
        cur = con.execute(
            """
            SELECT v.id, v.markdown_path, v.analysis_json, v.created_at,
                   EXISTS (SELECT 1 FROM pipeline_runs p
                           WHERE p.vacancy_id = v.id AND p.phase = ? AND p.status = 'done') AS has_run
            FROM vacancies v ORDER BY v.id
            """,
            (PHASE,),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        con.close()


def snapshot(src: Path, dest: Path) -> None:
    """Consistent copy via the SQLite backup API (the live DB may be in WAL mode)."""
    if dest.exists():
        raise FileExistsError(f"refusing to overwrite existing file: {dest}")
    s = _connect_ro(src)
    d = sqlite3.connect(dest)
    try:
        s.backup(d)
    finally:
        d.close()
        s.close()


def apply_inserts(db_path: Path, inserts: list[dict]) -> None:
    con = sqlite3.connect(db_path)
    try:
        con.executemany(
            """
            INSERT INTO pipeline_runs
                (vacancy_id, phase, status, result_path, started_at, finished_at, created_at)
            VALUES (?, ?, 'done', ?, NULL, ?, ?)
            """,
            [(i["vacancy_id"], PHASE, i["result_path"], i["finished_at"], i["finished_at"])
             for i in inserts],
        )
        con.commit()
    finally:
        con.close()


def diff_databases(before: Path, after: Path) -> dict[str, dict]:
    """Every table, every column, matched by rowid. Returns only tables that differ:
    {table: {"added": [rowid], "removed": [rowid], "changed": {rowid: [columns]}}}."""
    b, a = _connect_ro(before), _connect_ro(after)
    out: dict[str, dict] = {}
    try:
        tables = [r[0] for r in b.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for t in tables:
            q = f'SELECT rowid AS _rowid_, * FROM "{t}"'
            rb = {r["_rowid_"]: dict(r) for r in b.execute(q)}
            ra = {r["_rowid_"]: dict(r) for r in a.execute(q)}
            added = sorted(set(ra) - set(rb))
            removed = sorted(set(rb) - set(ra))
            changed = {
                k: [c for c in rb[k] if rb[k][c] != ra[k][c]]
                for k in rb.keys() & ra.keys() if rb[k] != ra[k]
            }
            if added or removed or changed:
                out[t] = {"added": added, "removed": removed, "changed": changed}
    finally:
        b.close()
        a.close()
    return out


def unexpected_changes(diff: dict[str, dict], expected_new_runs: int) -> list[str]:
    """Anything except exactly `expected_new_runs` new pipeline_runs rows."""
    problems: list[str] = []
    for table, d in diff.items():
        if table == "pipeline_runs":
            if d["removed"]:
                problems.append(f"pipeline_runs: {len(d['removed'])} rows removed")
            if d["changed"]:
                problems.append(f"pipeline_runs: {len(d['changed'])} existing rows changed")
            if len(d["added"]) != expected_new_runs:
                problems.append(f"pipeline_runs: {len(d['added'])} rows added, expected {expected_new_runs}")
        else:
            if d["added"]:
                problems.append(f"{table}: {len(d['added'])} rows added")
            if d["removed"]:
                problems.append(f"{table}: {len(d['removed'])} rows removed")
            for rid, cols in d["changed"].items():
                problems.append(f"{table} rowid {rid}: columns changed {cols}")
    if expected_new_runs and "pipeline_runs" not in diff:
        problems.append(f"pipeline_runs: expected {expected_new_runs} new rows, none found")
    return problems


def method_accuracy(db_path: Path, root: Path = _ROOT) -> dict | None:
    """How close is the file date to the REAL date, on vacancies where both exist."""
    con = _connect_ro(db_path)
    try:
        rows = con.execute(
            """
            SELECT v.markdown_path, MAX(p.finished_at) AS f
            FROM vacancies v JOIN pipeline_runs p
              ON p.vacancy_id = v.id AND p.phase = ? AND p.status = 'done' AND p.started_at IS NOT NULL
            WHERE v.markdown_path IS NOT NULL GROUP BY v.id
            """,
            (PHASE,),
        ).fetchall()
    finally:
        con.close()
    diffs = []
    for r in rows:
        f = analysis_file_for(r["markdown_path"], root)
        if f is None:
            continue
        real = datetime.fromisoformat(r["f"])
        guess = datetime.fromisoformat(file_date_utc(f))
        diffs.append(abs((guess - real).total_seconds()) / 3600)
    if not diffs:
        return None
    diffs.sort()
    return {
        "n": len(diffs),
        "median_h": statistics.median(diffs),
        "within_24h": sum(d <= 24 for d in diffs),
        "within_7d": sum(d <= 168 for d in diffs),
        "max_h": diffs[-1],
    }


# ── report ────────────────────────────────────────────────────────────────────

def build_report(*, mode: str, inserts: list[dict], skipped: dict[str, list[int]],
                 diff: dict[str, dict], problems: list[str], accuracy: dict | None) -> str:
    lines = [f"# analyzed_at backfill — {mode}", ""]
    lines.append(f"- vacancies to get a `phase2` done row: **{len(inserts)}**")
    if inserts:
        dates = sorted(i["finished_at"] for i in inserts)
        lines.append(f"- date range to be written: {dates[0]} → {dates[-1]} (UTC)")
        early = [i for i in inserts if i["finished_at"] < i["created_at"]]
        lines.append(f"- file date EARLIER than the vacancy's created_at: {len(early)}"
                     + (f" — ids {[i['vacancy_id'] for i in early]}" if early else ""))
    for reason, ids in skipped.items():
        lines.append(f"- skipped, {reason}: {len(ids)} {ids}")
    if accuracy:
        lines.append(
            f"- method check on {accuracy['n']} vacancies with a real run date: median difference "
            f"{accuracy['median_h']:.1f} h, within 24 h: {accuracy['within_24h']}, "
            f"within 7 d: {accuracy['within_7d']}, worst {accuracy['max_h']:.0f} h")
    lines += ["", "## Full diff, every table and column (live DB vs copy/backup)", ""]
    if not diff:
        lines.append("no differences")
    for t, d in diff.items():
        lines.append(f"- `{t}`: {len(d['added'])} added, {len(d['removed'])} removed, "
                     f"{len(d['changed'])} changed")
    lines += ["", "## Unexpected changes", ""]
    lines += [f"- {p}" for p in problems] or ["none"]
    lines += ["", "## Rows", "", "| vacancy | created_at | analyzed (file date, UTC) |", "|---|---|---|"]
    lines += [f"| #{i['vacancy_id']} | {i['created_at']} | {i['finished_at']} |"
              for i in sorted(inserts, key=lambda x: x["vacancy_id"])]
    return "\n".join(lines) + "\n"


# ── orchestration ─────────────────────────────────────────────────────────────

def run(db_path: Path, *, apply: bool, backup_dir: Path | None = None,
        root: Path = _ROOT, report_path: Path | None = None) -> dict:
    db_path = Path(db_path)
    inserts, skipped = plan_inserts(read_rows(db_path), root)
    accuracy = method_accuracy(db_path, root)
    if apply:
        backup_dir = backup_dir or db_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"{db_path.name}.bak-{datetime.now():%Y-%m-%d}-pre-analyzed-at-backfill"
        snapshot(db_path, backup)
        apply_inserts(db_path, inserts)
        diff = diff_databases(backup, db_path)
        mode = "APPLIED"
    else:
        backup = None
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "copy.db"
            snapshot(db_path, copy)
            apply_inserts(copy, inserts)
            diff = diff_databases(db_path, copy)
        mode = "DRY RUN (applied to a copy; live DB untouched)"
    problems = unexpected_changes(diff, len(inserts))
    report = build_report(mode=mode, inserts=inserts, skipped=skipped, diff=diff,
                          problems=problems, accuracy=accuracy)
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
    return {"inserts": inserts, "skipped": skipped, "diff": diff, "problems": problems,
            "accuracy": accuracy, "backup": backup, "report": report}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(_ROOT / "db" / "agent.db"), help="Path to agent.db")
    ap.add_argument("--apply", action="store_true",
                    help="back up, then WRITE the rows (default: dry run on a copy)")
    ap.add_argument("--report", default=None, help="where to write the report (default: research/)")
    args = ap.parse_args()

    stamp = datetime.now().strftime("%Y-%m-%d")
    kind = "apply" if args.apply else "dryrun"
    report_path = Path(args.report) if args.report else _ROOT / "research" / f"analyzed-at-backfill-{kind}-{stamp}.md"
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
