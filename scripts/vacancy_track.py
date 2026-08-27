#!/usr/bin/env python3
"""
scripts/vacancy_track.py — Lightweight DB operations for local skill pipeline.

PURPOSE
-------
Called by Claude Code /analyze during local-mode pipeline runs to:
1. Register or look up a vacancy in the DB (upsert by URL)
2. Update vacancy status as pipeline phases complete
3. Move processed inbox folders to inbox_manual/processed/

Writes vacancy history to DB so local-mode analysis appears in the web tracker.
Does NOT require ANTHROPIC_API_KEY — DB-only operations.

USAGE
-----
    # Register/find vacancy — prints vacancy_id to stdout
    python scripts/vacancy_track.py upsert \\
        --url "https://jobs.dou.ua/vacancies/123/" \\
        --title "Senior PM at Acme" \\
        [--user-id 1] [--path vacancies/001/Acme — PM/JD.md]

    # Update status (and optionally markdown_path) after phase completes
    python scripts/vacancy_track.py update \\
        --id 42 --status analyzed \\
        [--path vacancies/001/Acme — PM/JD.md]

    # Move inbox folder to processed/
    python scripts/vacancy_track.py move-processed \\
        --folder "SOLAR Digital — AI PM"

STATUS VALUES
-------------
    fetched | analyzed | generating | done | error

EXIT CODES
----------
    0 — success (upsert: vacancy_id printed to stdout)
    1 — error   (message on stderr, nothing on stdout)
"""

import argparse
import asyncio
import json
import os
import shutil
import sys
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


def _db_path() -> Path:
    return Path(os.getenv("DB_PATH", str(_ROOT / "db" / "agent.db")))


# ── upsert ────────────────────────────────────────────────────────────────────

async def cmd_upsert(url: str, title: str | None, user_id: int, path: str | None) -> None:
    """Insert vacancy if URL not seen before, or return existing id.

    Prints vacancy_id (int) to stdout. Idempotent — safe to call on every run.
    """
    database.configure(_db_path())
    await database.init_db()

    # Check for existing vacancy (normalized URL lookup)
    existing = await database.get_vacancy_by_url(url)
    if existing is not None:
        vid = existing["id"]
        # Update path if provided and not yet set
        if path and not existing["markdown_path"]:
            await database.update_vacancy_fields(vid, markdown_path=path)
        print(vid)
        return

    # Insert new vacancy — URL is normalised inside insert_vacancy
    vid = await database.insert_vacancy(
        url=url,
        title=title,
        markdown_path=path,
        user_id=user_id,
        status="fetched",
    )
    print(vid)


# ── update ────────────────────────────────────────────────────────────────────

async def cmd_update(vacancy_id: int, status: str, path: str | None, title: str | None, salary: str | None, tags: str | None = None) -> None:
    """Update vacancy status. Optionally set/update markdown_path, title, salary, tags."""
    database.configure(_db_path())
    await database.init_db()

    fields: dict = {}
    if path:
        fields["markdown_path"] = path
    if title:
        fields["title"] = title
    if salary:
        fields["salary"] = salary
    if tags:
        fields["tags"] = tags
    if fields:
        await database.update_vacancy_fields(vacancy_id, **fields)
    await database.update_vacancy_status(vacancy_id, status)


# ── update-json ──────────────────────────────────────────────────────────────

async def cmd_update_json(vacancy_id: int, phase: str, data_str: str) -> None:
    """Merge structured phase data into analysis_json column.

    Reads current analysis_json, sets analysis_json[phase] = data, writes back.
    Also writes analysis.json to the vacancy folder (best-effort — DB is canonical).
    data_str: JSON string for this phase, or '-' to read from stdin.
    """
    database.configure(_db_path())
    await database.init_db()

    if data_str == "-":
        data_str = sys.stdin.read()

    try:
        data = json.loads(data_str)
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    await database.patch_analysis_json(vacancy_id, phase, data)

    # Best-effort: write analysis.json to vacancy folder (DB is canonical)
    try:
        row = await database.get_vacancy_by_id(vacancy_id)
        if row and row["markdown_path"] and row["analysis_json"]:
            folder = Path(row["markdown_path"]).parent
            if not folder.is_absolute():
                folder = _ROOT / folder
            if folder.exists():
                (folder / "analysis.json").write_text(
                    json.dumps(json.loads(row["analysis_json"]), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
    except Exception as exc:
        print(f"WARNING: analysis.json file write failed: {exc}", file=sys.stderr)


# ── move-to-inbox ─────────────────────────────────────────────────────────────

def cmd_move_to_inbox(folder_name: str, user_id: int) -> None:
    """Move inbox_manual subfolder to vacancies/inbox/{user_id}/.

    After processing, the vacancy folder moves from the manual staging area
    to the permanent inbox location shared with the system pipeline.

    folder_name: exact folder name inside inbox_manual/ (not full path).
    user_id: numeric DB user id.
    """
    inbox_manual = _ROOT / "vacancies" / "inbox_manual"
    src = inbox_manual / folder_name

    if not src.exists():
        print(f"ERROR: folder not found: {src}", file=sys.stderr)
        sys.exit(1)

    dst_dir = _ROOT / "vacancies" / "inbox" / str(user_id)
    dst_dir.mkdir(parents=True, exist_ok=True)

    dst = dst_dir / folder_name
    if dst.exists():
        # Already moved — idempotent, nothing to do
        return

    shutil.move(str(src), str(dst))


# ── get ───────────────────────────────────────────────────────────────────────

async def cmd_get(vacancy_id: int) -> None:
    """Print vacancy record as JSON. Exits 1 with message on stderr if not found."""
    database.configure(_db_path())
    await database.init_db()

    row = await database.get_vacancy_by_id(vacancy_id)
    if row is None:
        print(f"ERROR: vacancy id={vacancy_id} not found", file=sys.stderr)
        sys.exit(1)

    data = dict(row)
    if data.get("analysis_json"):
        try:
            data["analysis_json"] = json.loads(data["analysis_json"])
        except (json.JSONDecodeError, TypeError):
            pass

    print(json.dumps(data, ensure_ascii=False, indent=2))


# ── delete-inbox ──────────────────────────────────────────────────────────────

def cmd_delete_inbox(folder_name: str) -> None:
    """Delete a raw inbox_manual folder after processing is complete.

    Use after batch/sequential pipeline when the clean 'Role — Company/'
    folder has already been created under vacancies/inbox/{user_id}/.
    Deletes the raw staging folder from inbox_manual/ — never touches inbox/.

    Idempotent: if folder already gone, exits silently.
    folder_name: exact folder name inside inbox_manual/ (not full path).
    """
    inbox_manual = _ROOT / "vacancies" / "inbox_manual"
    target = inbox_manual / folder_name

    # Safety: refuse to delete anything outside inbox_manual/ (path traversal guard)
    # Must run before the existence check so traversal attempts are always rejected.
    try:
        target.resolve().relative_to(inbox_manual.resolve())
    except ValueError:
        print(f"ERROR: folder not inside inbox_manual/: {target}", file=sys.stderr)
        sys.exit(1)

    if not target.exists():
        # Already deleted — idempotent, nothing to do
        return

    shutil.rmtree(target)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="DB operations for local skill pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # upsert
    p_upsert = sub.add_parser("upsert", help="Insert or get existing vacancy by URL")
    p_upsert.add_argument("--url", required=True, help="Vacancy URL (will be normalised)")
    p_upsert.add_argument("--title", default=None, help="Vacancy title")
    p_upsert.add_argument("--user-id", dest="user_id", type=int, default=1,
                          help="DB user id (default: 1)")
    p_upsert.add_argument("--path", default=None, help="Relative path to JD.md")

    # update
    p_update = sub.add_parser("update", help="Update vacancy status")
    p_update.add_argument("--id", dest="vacancy_id", type=int, required=True,
                          help="Vacancy DB id")
    p_update.add_argument("--status", required=True,
                          help="New status: fetched|analyzed|generating|done|error")
    p_update.add_argument("--path", default=None, help="Update markdown_path")
    p_update.add_argument("--title", default=None, help="Update vacancy title")
    p_update.add_argument("--salary", default=None, help="Salary info, e.g. '$4500'")
    p_update.add_argument("--tags", default=None, help="Comma-separated tags, e.g. 'deftech,ai'")

    # move-to-inbox
    p_move = sub.add_parser("move-to-inbox", help="Move inbox_manual folder to vacancies/inbox/{user_id}/")
    p_move.add_argument("--folder", required=True,
                        help="Exact folder name inside inbox_manual/")
    p_move.add_argument("--user-id", dest="user_id", type=int, default=1,
                        help="DB user id (default: 1)")

    # update-json
    p_ujson = sub.add_parser("update-json", help="Merge structured phase data into analysis_json")
    p_ujson.add_argument("--id", dest="vacancy_id", type=int, required=True,
                         help="Vacancy DB id")
    p_ujson.add_argument("--phase", required=True,
                         help="Phase key: p1 | p2 | p3 | p4")
    p_ujson.add_argument("--data", required=True,
                         help="JSON string for this phase, or '-' to read from stdin")

    # get
    p_get = sub.add_parser("get", help="Print vacancy record as JSON by DB id")
    p_get.add_argument("--id", dest="vacancy_id", type=int, required=True,
                       help="Vacancy DB id")

    # delete-inbox
    p_del = sub.add_parser("delete-inbox", help="Delete raw inbox_manual folder after pipeline processing")
    p_del.add_argument("--folder", required=True,
                       help="Exact folder name inside inbox_manual/ to delete")

    args = parser.parse_args()

    try:
        if args.cmd == "upsert":
            asyncio.run(cmd_upsert(
                url=args.url,
                title=args.title,
                user_id=args.user_id,
                path=args.path,
            ))
        elif args.cmd == "update":
            asyncio.run(cmd_update(
                vacancy_id=args.vacancy_id,
                status=args.status,
                path=args.path,
                title=args.title,
                salary=args.salary,
                tags=args.tags,
            ))
        elif args.cmd == "update-json":
            asyncio.run(cmd_update_json(
                vacancy_id=args.vacancy_id,
                phase=args.phase,
                data_str=args.data,
            ))
        elif args.cmd == "get":
            asyncio.run(cmd_get(vacancy_id=args.vacancy_id))
        elif args.cmd == "move-to-inbox":
            cmd_move_to_inbox(folder_name=args.folder, user_id=args.user_id)
        elif args.cmd == "delete-inbox":
            cmd_delete_inbox(folder_name=args.folder)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
