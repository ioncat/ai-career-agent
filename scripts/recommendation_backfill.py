"""
scripts/recommendation_backfill.py — normalize non-canonical `p2.recommendation`
values in `vacancies.analysis_json`.

Why: the stored recommendation is one of `apply | take_a_chance | decline`
(contracts/pipeline.py `Recommendation`). Early analyses stored `take a chance`
(with spaces) and `skip`. Consumers compare the canonical values: the Flutter
chip (`recommendation_chip.dart`, `app_theme.dart`) styles `take_a_chance` and
`decline` by exact match, and `web/api.py` `_rec_label()` falls back to the raw
text, so those rows render with the default chip and no proper label.

Mapping: a value that differs from a canonical one only by case, spaces or
hyphens is normalized (`take a chance` -> `take_a_chance`); `skip` -> `decline`
(same meaning: do not pursue). Any other unknown value is NOT changed and is
listed in the report for a human decision.

What it writes: ONLY `vacancies.analysis_json`, ONLY the one `recommendation`
value inside `p2`, by exact text substitution (the rest of the JSON stays
byte-for-byte). It deliberately does not touch `updated_at`: the Analyzed and
processed folders sort by it, so a bulk write through the normal setter
(`database.patch_analysis_json`, which bumps `updated_at`) would push every old
vacancy to the top of those lists.

Note: this does NOT make the rows pass strict `Phase2Data` validation. They are
legacy-shaped (no `recommendation_label`, `who_they_want`, `fit_dimensions`),
so they keep using the legacy parser in `web/api.py`; only the vocabulary and
the chip styling are fixed.

DRY-RUN by default: the plan is applied to a COPY of the database and every
table and column of the copy is diffed against the live DB; anything other than
the planned `analysis_json` changes is listed as unexpected (bulk-data rule).
The live DB is opened read-only. --apply takes a backup first (refuses to
overwrite one), writes, then diffs the live DB against that backup.
Safe to re-run: canonical rows are not selected.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:  # run as `python scripts/recommendation_backfill.py`
    sys.path.insert(0, str(_ROOT))

from scripts.analyzed_at_backfill import _connect_ro, diff_databases, snapshot  # noqa: E402

CANONICAL = ("apply", "take_a_chance", "decline")
# Non-spelling variants that need a human-chosen target. `skip` meant "do not pursue".
EXTRA_MAP = {"skip": "decline"}


# ── pure helpers ──────────────────────────────────────────────────────────────

def canonical_for(value: object) -> str | None:
    """Canonical value for a non-canonical `recommendation`, or None when there is
    no safe mapping (also None for a value that is already canonical)."""
    if not isinstance(value, str) or value in CANONICAL:
        return None
    key = re.sub(r"[\s\-]+", "_", value.strip().lower())
    if key in CANONICAL:
        return key
    return EXTRA_MAP.get(key)


def substitute(analysis_json: str, old: str, new: str) -> str | None:
    """Replace the one `"recommendation": "<old>"` pair by `<new>`, byte-for-byte
    elsewhere. None when the pair does not occur exactly once, or when the result
    is not the same document with only p2.recommendation changed."""
    pattern = re.compile(r'("recommendation"\s*:\s*)' + re.escape(json.dumps(old)))
    if len(pattern.findall(analysis_json)) != 1:
        return None
    result = pattern.sub(lambda m: m.group(1) + json.dumps(new), analysis_json)
    try:
        before, after = json.loads(analysis_json), json.loads(result)
        before["p2"]["recommendation"] = new
    except (ValueError, KeyError, TypeError):
        return None
    return result if before == after else None


def plan_updates(rows) -> tuple[list[dict], list[dict]]:
    """rows: dicts with id, status, applied, analysis_json.
    Returns (updates, unmapped); unmapped rows are listed, never written."""
    updates: list[dict] = []
    unmapped: list[dict] = []
    for r in rows:
        try:
            doc = json.loads(r["analysis_json"]) if r["analysis_json"] else None
        except ValueError:
            continue
        p2 = doc.get("p2") if isinstance(doc, dict) else None
        if not isinstance(p2, dict) or "recommendation" not in p2:
            continue
        old = p2["recommendation"]
        if old in CANONICAL:
            continue
        new = canonical_for(old)
        item = {"id": r["id"], "status": r["status"], "applied": r["applied"],
                "fit_score": p2.get("fit_score"), "old": old, "new": new}
        if new is None:
            unmapped.append({**item, "reason": "no safe mapping"})
            continue
        text = substitute(r["analysis_json"], old, new)
        if text is None:
            unmapped.append({**item, "reason": "pair not unique or document changed unexpectedly"})
            continue
        updates.append({**item, "analysis_json": text})
    return updates, unmapped


# ── database access ───────────────────────────────────────────────────────────

def read_rows(db_path: Path) -> list[dict]:
    con = _connect_ro(db_path)
    try:
        cur = con.execute(
            "SELECT id, status, applied, analysis_json FROM vacancies "
            "WHERE analysis_json IS NOT NULL ORDER BY id")
        return [dict(r) for r in cur.fetchall()]
    finally:
        con.close()


def apply_updates(db_path: Path, updates: list[dict]) -> None:
    """Only `analysis_json`; never `updated_at` (see the module docstring)."""
    con = sqlite3.connect(db_path)
    try:
        con.executemany("UPDATE vacancies SET analysis_json = ? WHERE id = ?",
                        [(u["analysis_json"], u["id"]) for u in updates])
        con.commit()
    finally:
        con.close()


def unexpected_changes(diff: dict[str, dict], updates: list[dict]) -> list[str]:
    """Anything except `analysis_json` changing on exactly the planned vacancies."""
    expected = {u["id"] for u in updates}
    problems: list[str] = []
    for table, d in diff.items():
        if d["added"]:
            problems.append(f"{table}: {len(d['added'])} rows added")
        if d["removed"]:
            problems.append(f"{table}: {len(d['removed'])} rows removed")
        for rid, cols in d["changed"].items():
            if table == "vacancies" and cols == ["analysis_json"]:
                continue
            problems.append(f"{table} rowid {rid}: columns changed {cols}")
    changed = set(diff.get("vacancies", {}).get("changed", {}))
    if changed != expected:
        problems.append(f"vacancies changed {sorted(changed)}, planned {sorted(expected)}")
    return problems


# ── report ────────────────────────────────────────────────────────────────────

def build_report(*, mode: str, updates: list[dict], unmapped: list[dict],
                 diff: dict[str, dict], problems: list[str]) -> str:
    lines = [f"# recommendation backfill — {mode}", ""]
    lines.append(f"- rows to normalize: **{len(updates)}**")
    by_map: dict[str, int] = {}
    for u in updates:
        key = f"{u['old']!r} -> {u['new']!r}"
        by_map[key] = by_map.get(key, 0) + 1
    for key, n in sorted(by_map.items()):
        lines.append(f"  - {key}: {n}")
    lines.append(f"- left unchanged, no safe mapping: {len(unmapped)} {[u['id'] for u in unmapped]}")
    lines += ["", "## Full diff, every table and column (live DB vs copy/backup)", ""]
    if not diff:
        lines.append("no differences")
    for t, d in diff.items():
        lines.append(f"- `{t}`: {len(d['added'])} added, {len(d['removed'])} removed, "
                     f"{len(d['changed'])} changed "
                     f"(columns: {sorted({c for cols in d['changed'].values() for c in cols})})")
    lines += ["", "## Unexpected changes", ""]
    lines += [f"- {p}" for p in problems] or ["none"]
    lines += ["", "## Rows", "", "| vacancy | status | applied | fit | old | new |", "|---|---|---|---|---|---|"]
    lines += [f"| #{u['id']} | {u['status']} | {u['applied']} | {u['fit_score']} | {u['old']} | {u['new']} |"
              for u in sorted(updates, key=lambda x: x["id"])]
    if unmapped:
        lines += ["", "## Not changed", ""]
        lines += [f"- #{u['id']}: {u['old']!r} ({u['reason']})" for u in unmapped]
    return "\n".join(lines) + "\n"


# ── orchestration ─────────────────────────────────────────────────────────────

def run(db_path: Path, *, apply: bool, backup_dir: Path | None = None,
        report_path: Path | None = None) -> dict:
    db_path = Path(db_path)
    updates, unmapped = plan_updates(read_rows(db_path))
    if apply:
        backup_dir = backup_dir or db_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"{db_path.name}.bak-{datetime.now():%Y-%m-%d_%H%M%S}-pre-recommendation-backfill"
        snapshot(db_path, backup)
        apply_updates(db_path, updates)
        diff = diff_databases(backup, db_path)
        mode = "APPLIED"
    else:
        backup = None
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "copy.db"
            snapshot(db_path, copy)
            apply_updates(copy, updates)
            diff = diff_databases(db_path, copy)
        mode = "DRY RUN (applied to a copy; live DB untouched)"
    problems = unexpected_changes(diff, updates)
    report = build_report(mode=mode, updates=updates, unmapped=unmapped, diff=diff, problems=problems)
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
    return {"updates": updates, "unmapped": unmapped, "diff": diff, "problems": problems,
            "backup": backup, "report": report}


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
    report_path = Path(args.report) if args.report else _ROOT / "research" / f"recommendation-backfill-{kind}-{stamp}.md"
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
