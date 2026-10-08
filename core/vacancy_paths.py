"""
core/vacancy_paths.py — repair `vacancies.markdown_path` after a folder was renamed by hand.

Inbox folders are named `{id} — {role} — {company}`. When the user renames one after the
fetch (typically to append the company), the DB keeps the old path, and
`GET /api/vacancies/{id}/jd` answers 404 "JD not found" while the vacancy card still renders.

Repair rule (no guessing): for a row whose `markdown_path` is set but does not exist, look in
`<vacancies>/inbox/<user_id>/` for folders whose name starts with `{id} — `. Exactly one such
folder, and it holds a `JD.md` -> point `markdown_path` at it. Anything else (no folder, several
folders, no JD.md inside) is reported and left alone. Rows with an empty `markdown_path`
(never fetched) are not touched.

Only `markdown_path` is written, through `database.update_vacancy_fields`, which does not touch
`status` or `updated_at`.
"""
from __future__ import annotations

import logging
from pathlib import Path

from db import database

log = logging.getLogger(__name__)

JD_FILE = "JD.md"


def _resolve(path_text: str, project_root: Path) -> Path:
    p = Path(path_text)
    return p if p.is_absolute() else project_root / p


def _same_style(new_path: Path, old_text: str, project_root: Path) -> str:
    """The new path relative to the project root, with the separator style of the old value
    (the table holds both backslash and forward-slash paths)."""
    try:
        text = str(new_path.relative_to(project_root))
    except ValueError:
        text = str(new_path)
    if "\\" in old_text:
        return text.replace("/", "\\")
    if "/" in old_text:
        return text.replace("\\", "/")
    return text


def find_repairs(rows, vacancies_root: Path, project_root: Path) -> tuple[list[dict], list[dict]]:
    """rows: dicts with id, user_id, markdown_path.
    Returns (repairs, unresolved). A repair is {id, old, new}; an unresolved row is
    {id, old, reason} and must be looked at by a human."""
    repairs: list[dict] = []
    unresolved: list[dict] = []
    for r in rows:
        old = r["markdown_path"]
        if not old or _resolve(old, project_root).exists():
            continue
        user_dir = vacancies_root / "inbox" / str(r["user_id"])
        prefix = f"{r['id']} — "
        matches = (
            [d for d in user_dir.iterdir() if d.is_dir() and d.name.startswith(prefix)]
            if user_dir.is_dir() else []
        )
        if len(matches) != 1:
            unresolved.append({"id": r["id"], "old": old,
                               "reason": f"{len(matches)} folders named '{r['id']} — *'"})
            continue
        jd = matches[0] / JD_FILE
        if not jd.is_file():
            unresolved.append({"id": r["id"], "old": old,
                               "reason": f"folder '{matches[0].name}' has no {JD_FILE}"})
            continue
        repairs.append({"id": r["id"], "old": old, "new": _same_style(jd, old, project_root)})
    return repairs, unresolved


async def read_rows() -> list[dict]:
    async with database.get_db() as db:
        cur = await db.execute(
            "SELECT id, user_id, markdown_path FROM vacancies "
            "WHERE markdown_path IS NOT NULL AND markdown_path != '' ORDER BY id"
        )
        return [dict(r) for r in await cur.fetchall()]


async def repair_markdown_paths(vacancies_root: Path, project_root: Path) -> dict:
    """Startup hygiene (same family as database.reset_stuck_statuses): repair what is
    unambiguous, log the rest. Returns {"repaired": [...], "unresolved": [...]}."""
    vacancies_root = vacancies_root if vacancies_root.is_absolute() else project_root / vacancies_root
    repairs, unresolved = find_repairs(await read_rows(), vacancies_root, project_root)
    for item in repairs:
        await database.update_vacancy_fields(item["id"], markdown_path=item["new"])
        log.warning("DB recovery: v#%d markdown_path repaired -> %s", item["id"], item["new"])
    if unresolved:
        log.warning(
            "DB recovery: %d vacancies have a missing JD file and no single matching folder, "
            "left as they are: %s",
            len(unresolved), [u["id"] for u in unresolved],
        )
    return {"repaired": repairs, "unresolved": unresolved}
