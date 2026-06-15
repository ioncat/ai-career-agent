#!/usr/bin/env python3
"""
scripts/inbox_scan.py — Canonical inbox scanner for the local skill pipeline.

PURPOSE
-------
Single source of truth for "what is in vacancies/inbox_manual/?".
Called by Claude Code /analyze (Step 1 — inbox check) so the scan logic
lives in code, not in hand-rolled `ls`/`find` commands that miss the
folder-based layout.

LAYOUT (folder-based — NOT flat files)
--------------------------------------
    vacancies/inbox_manual/
    ├── .gitkeep                         ← ignored
    ├── processed/                       ← ignored
    └── Role — Company/                  ← raw staging folder (user drops here)
        └── <anything>.md | .txt         ← the JD file(s)

A drop may also be a flat `.md`/`.txt` directly under inbox_manual/.
Both forms are reported.

DEDUP
-----
For each drop, the `Source:` URL (first 5 lines) is matched against
`vacancies/inbox/{user_id}/*/JD.md`. A hit means the vacancy was already
processed for this user.

USAGE
-----
    # Human-readable list (default)
    python scripts/inbox_scan.py [--user-id 1]

    # Machine-readable JSON (for /analyze to parse)
    python scripts/inbox_scan.py --json [--user-id 1]

EXIT CODES
----------
    0 — scan ran (even if inbox empty)
    1 — error (message on stderr)
"""

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = Path(__file__).parent.parent
_INBOX_MANUAL = _ROOT / "vacancies" / "inbox_manual"

_HEADER_LINES = 5  # how many leading lines to scan for title / Source URL


def _read_head(path: Path, n: int = _HEADER_LINES) -> list[str]:
    lines: list[str] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for _ in range(n):
                line = fh.readline()
                if not line:
                    break
                lines.append(line.rstrip("\n"))
    except OSError:
        pass
    return lines


def _parse_title(head: list[str], fallback: str) -> str:
    for line in head:
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return fallback


def _parse_source(head: list[str]) -> str:
    for line in head:
        s = line.strip()
        if s.lower().startswith("source:"):
            url = s.split(":", 1)[1].strip()
            if url.startswith("http"):
                return url
    return ""


def _find_drops() -> list[dict]:
    """Return every JD drop file under inbox_manual/, with its raw folder name.

    raw_folder = top-level entry under inbox_manual/ (folder name for nested
    drops, filename for flat drops) — exactly what `vacancy_track.py
    delete-inbox --folder` expects.
    """
    drops: list[dict] = []
    if not _INBOX_MANUAL.is_dir():
        return drops

    for path in sorted(_INBOX_MANUAL.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in (".md", ".txt"):
            continue
        if path.name == ".gitkeep":
            continue
        # skip the processed/ archive
        rel_parts = path.relative_to(_INBOX_MANUAL).parts
        if rel_parts and rel_parts[0] == "processed":
            continue
        raw_folder = rel_parts[0]  # folder for nested, filename for flat
        drops.append({"path": path, "raw_folder": raw_folder})

    return drops


def _seen_path_for(url: str, raw_folder: str, user_id: int) -> str:
    """Check if this drop was already processed for user_id.

    URL present  → scan JD.md and JD_analysis.md in every vacancy folder for URL.
    URL absent   → folder-name match: vacancies/inbox/{user_id}/{raw_folder}/ exists?
    Returns path (relative to repo root) of the matched file/folder, or "".
    """
    base = _ROOT / "vacancies" / "inbox" / str(user_id)
    if not base.is_dir():
        return ""

    if url:
        for candidate in sorted(base.glob("*/*.md")):
            if candidate.name not in ("JD.md", "JD_analysis.md"):
                continue
            try:
                text = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if url in text:
                return str(candidate.relative_to(_ROOT)).replace("\\", "/")
        # URL present but no match — still try folder-name fallback
        # (same vacancy may be listed on multiple job boards with different URLs)

    # Folder-name fallback: vacancies/inbox/{user_id}/{raw_folder}/ exists?
    target = base / raw_folder
    if target.is_dir():
        for fname in ("JD_analysis.md", "JD.md"):
            p = target / fname
            if p.exists():
                return str(p.relative_to(_ROOT)).replace("\\", "/")
        return str(target.relative_to(_ROOT)).replace("\\", "/")
    return ""


def scan(user_id: int) -> list[dict]:
    results: list[dict] = []
    for idx, drop in enumerate(_find_drops(), start=1):
        path: Path = drop["path"]
        head = _read_head(path)
        title = _parse_title(head, fallback=path.stem)
        url = _parse_source(head)
        seen_path = _seen_path_for(url, drop["raw_folder"], user_id)
        results.append({
            "index": idx,
            "title": title,
            "source_url": url,
            "file": str(path.relative_to(_ROOT)).replace("\\", "/"),
            "raw_folder": drop["raw_folder"],
            "seen": bool(seen_path),
            "seen_path": seen_path,
        })
    return results


def _print_human(results: list[dict]) -> None:
    if not results:
        print("📥 Inbox пуст — vacancies/inbox_manual/")
        return
    print(f"📥 Inbox — vacancies/inbox_manual/ ({len(results)} шт.):")
    print()
    for r in results:
        status = f"♻️ уже обработана → {r['seen_path']}" if r["seen"] else "🆕 новая"
        print(f"  {r['index']}. {r['title']}")
        print(f"     Source: {r['source_url'] or '— (нет URL)'}")
        print(f"     File:   {r['file']}")
        print(f"     Status: {status}")
        print()


def main() -> int:
    ap = argparse.ArgumentParser(description="Scan vacancies/inbox_manual/ for JD drops.")
    ap.add_argument("--user-id", type=int, default=1, help="user id for dedup (default 1)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of human table")
    args = ap.parse_args()

    try:
        results = scan(args.user_id)
    except Exception as exc:  # noqa: BLE001 — CLI boundary, report and exit 1
        print(f"inbox_scan error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        _print_human(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
