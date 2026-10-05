"""
scripts/dedup_backfill.py — re-evaluate every vacancy currently flagged
`duplicate_of` under the EPIC-26 dedup rework (2026-10-05) rules.

Replays ingestion order: each vacancy is classified against OLDER rows only
(`before_id`), as when it was first fetched, using the same
`database.classify_duplicate()` the live pipeline uses (without this, hash twins
would point at each other in a cycle):

  - content-hash match                         -> confirmed (unchanged semantics)
  - title+company match, best containment
    >= core.dedup.CONFIRM_THRESHOLD            -> confirmed (original = best-scoring, not lowest id)
  - title+company match, containment below / file unreadable -> POSSIBLE
    (possible_duplicate_of), not a duplicate any more

DRY-RUN by default: reads the DB and JD files, writes only the markdown diff
report (default research/dedup-backfill-dryrun-2026-10-05_RU.md — gitignored).
When research/dedup-audit-verdicts-2026-10-05_RU.md exists, the report also
cross-checks the owner-approved 30 verdicts (Д = duplicate, Н = not).

Legacy-link fallback: stored title/company drift after ingest (manual edits,
re-fetches), so a link made by the old rule may no longer match on title+company;
a few legacy links also point at a NEWER row. When classify finds nothing, the row's OLD original is scored directly with the
same containment/threshold (reason "legacy_link") instead of being reported lost.

--apply writes the new state (init_db() migration first — adds the
possible_duplicate_of column). Take a DB backup before using it. Rows where the
new rules find no match at all are NOT touched by --apply (reported for review).
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.dedup import CONFIRM_THRESHOLD, containment as containment_of, read_jd_text  # noqa: E402
from db import database  # noqa: E402

DEFAULT_REPORT = _ROOT / "research" / "dedup-backfill-dryrun-2026-10-05_RU.md"
VERDICTS_FILE = _ROOT / "research" / "dedup-audit-verdicts-2026-10-05_RU.md"


async def _evaluate() -> list[dict]:
    async with database.get_db() as db:
        cur = await db.execute("SELECT * FROM vacancies WHERE duplicate_of IS NOT NULL ORDER BY id")
        rows = [dict(r) for r in await cur.fetchall()]
        old_hash: dict[int, str | None] = {}
        for r in rows:
            c = await db.execute("SELECT content_hash FROM vacancies WHERE id = ?", (r["duplicate_of"],))
            o = await c.fetchone()
            old_hash[r["id"]] = o["content_hash"] if o else None

    async def _jd_text_of(vid: int) -> str | None:
        async with database.get_db() as db2:
            c2 = await db2.execute("SELECT markdown_path FROM vacancies WHERE id = ?", (vid,))
            row = await c2.fetchone()
        return await read_jd_text(row["markdown_path"], _ROOT) if row else None

    results: list[dict] = []
    for r in rows:
        text = await read_jd_text(r["markdown_path"], _ROOT)
        verdict = await database.classify_duplicate(
            r["user_id"], r["content_hash"],
            database._normalize_title(r["title"] or "", r["company"]), r["company"] or "",
            exclude_id=r["id"], new_text=text, before_id=r["id"],
        )
        old = r["duplicate_of"]
        old_basis = "hash" if (r["content_hash"] and r["content_hash"] == old_hash[r["id"]]) else "title+company"
        reason, containment = verdict.reason, verdict.containment
        confirmed_id, possible_id = verdict.confirmed_id, verdict.possible_id
        if confirmed_id is None and possible_id is None:
            # Legacy-link fallback (see module docstring).
            old_text = await _jd_text_of(old)
            if text is not None and old_text is not None:
                containment = containment_of(text, old_text)
                reason = "legacy_link"
                if containment >= CONFIRM_THRESHOLD:
                    confirmed_id = old
                else:
                    possible_id = old
        if confirmed_id is not None:
            # A hash twin is an unconditional link; which twin is irrelevant.
            same = confirmed_id == old or (reason == "hash" and old_basis == "hash")
            category = "unchanged" if same else "original_changed"
            new_state, new_id = "confirmed", confirmed_id
        elif possible_id is not None:
            category, new_state, new_id = "downgraded", "possible", possible_id
        else:
            category, new_state, new_id = "lost", "none", None
        results.append({
            "id": r["id"], "title": r["title"] or "", "company": r["company"] or "",
            "old": old,
            "old_basis": old_basis,
            "category": category, "new_state": new_state, "new_id": new_id,
            "containment": containment, "reason": reason,
            "text_readable": text is not None,
        })
    return results


def _parse_verdicts(path: Path) -> list[tuple[int, int, str]]:
    """(dup_id, orig_id, 'Д'|'Н') rows from the owner's verdicts table."""
    out = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 5:
            continue
        m = re.fullmatch(r"(\d+)\s*→\s*(\d+)", cells[1])
        if m and cells[3] in ("Д", "Н"):
            out.append((int(m.group(1)), int(m.group(2)), cells[3]))
    return out


def _fmt_c(c: float | None) -> str:
    return "—" if c is None else f"{c:.2f}"


def _crosscheck(results: list[dict], verdicts: list[tuple[int, int, str]]) -> tuple[list[str], dict]:
    by_id = {r["id"]: r for r in results}
    lines = [
        "| Пара (дубль → оригинал) | Вердикт | Новое состояние | Вложенность | Согласовано |",
        "|---|---|---|---|---|",
    ]
    stats: Counter = Counter()
    for dup, orig, v in verdicts:
        r = by_id.get(dup)
        if r is None:
            lines.append(f"| {dup} → {orig} | {v} | (нет в выборке) | — | ? |")
            stats["missing"] += 1
            continue
        state = {"confirmed": f"подтверждён → #{r['new_id']}", "possible": f"возможный → #{r['new_id']}",
                 "none": "связь снята"}[r["new_state"]]
        if v == "Н":
            ok = not (r["new_state"] == "confirmed" and r["new_id"] == orig)
            mark = "да" if ok else "НЕТ"
            if ok and r["new_state"] == "confirmed":
                mark = "да (подтверждён ДРУГОЙ оригинал, проверить)"
            stats["Н_ok" if ok else "Н_fail"] += 1
        else:
            if r["new_state"] == "confirmed":
                mark, key = "да (идеально)", "Д_confirmed"
            elif r["new_state"] == "possible":
                mark, key = "да (хотя бы возможный)", "Д_possible"
            else:
                mark, key = "НЕТ", "Д_fail"
            stats[key] += 1
        lines.append(f"| {dup} → {orig} | {v} | {state} | {_fmt_c(r['containment'])} | {mark} |")
    return lines, stats


def _table(rows: list[dict], with_new: bool = True) -> list[str]:
    head = "| Дубль | Название / компания | Было | Стало | Вложенность | Основа раньше → сейчас |"
    out = [head, "|---|---|---|---|---|---|"]
    for r in rows:
        new = {"confirmed": f"подтверждён → #{r['new_id']}", "possible": f"возможный → #{r['new_id']}",
               "none": "совпадений нет"}[r["new_state"]]
        if not r["text_readable"]:
            new += " (JD не читается)"
        out.append(
            f"| #{r['id']} | {r['title'][:50]} / {r['company'][:30]} | → #{r['old']} | {new} "
            f"| {_fmt_c(r['containment'])} | {r['old_basis']} → {r['reason']} |"
        )
    return out


def build_report(results: list[dict], verdicts: list[tuple[int, int, str]]) -> str:
    groups: dict[str, list[dict]] = {k: [] for k in ("unchanged", "original_changed", "downgraded", "lost")}
    for r in results:
        groups[r["category"]].append(r)
    link = {r["id"]: r["new_id"] for r in results if r["new_id"] is not None}
    cycles = sorted({tuple(sorted((a, b))) for a, b in link.items() if link.get(b) == a})
    possible_same = sum(1 for r in groups["downgraded"] if r["new_id"] == r["old"])

    out = [
        "# Dry-run бэкфилла дублей (EPIC-26, 2026-10-05)",
        "",
        f"Пересчитаны все {len(results)} вакансии с `duplicate_of` по новым правилам "
        f"(порог подтверждения вложенности {CONFIRM_THRESHOLD:.2f}; оригинал = лучший по тексту, не минимальный id; "
        "кандидаты — только более старые вакансии, как при реальном приёме). **Ничего не записано в БД.**",
        "",
        "## Итого",
        "",
        f"- Без изменений (тот же оригинал, подтверждён): **{len(groups['unchanged'])}**",
        f"- Оригинал сменился (подтверждён другой): **{len(groups['original_changed'])}**",
        f"- Понижены до «возможного дубля»: **{len(groups['downgraded'])}** "
        f"(из них тот же кандидат: {possible_same}, другой: {len(groups['downgraded']) - possible_same})",
        f"- Совпадений не найдено совсем (при --apply не трогаются): **{len(groups['lost'])}**",
        f"- Взаимные ссылки (A→B и B→A, оба помечены): **{len(cycles)}** пар"
        + (": " + ", ".join(f"#{a}↔#{b}" for a, b in cycles) if cycles else ""),
        "",
    ]
    if verdicts:
        lines, st = _crosscheck(results, verdicts)
        n_n = sum(1 for _, _, v in verdicts if v == "Н")
        n_d = sum(1 for _, _, v in verdicts if v == "Д")
        consistent = st["Н_ok"] + st["Д_confirmed"] + st["Д_possible"]
        out += [
            "## Сверка с 30 вердиктами владельца",
            "",
            f"Согласованы **{consistent} из {len(verdicts)}**: "
            f"Н (не дубль) не подтверждены к прежнему оригиналу — {st['Н_ok']} из {n_n}; "
            f"Д (дубль) подтверждены — {st['Д_confirmed']}, хотя бы возможные — {st['Д_possible']}, "
            f"потеряны — {st['Д_fail']} (из {n_d}).",
            "",
        ] + lines + [""]
    titles = {
        "unchanged": "## Без изменений",
        "original_changed": "## Оригинал сменился",
        "downgraded": "## Понижены до «возможного дубля»",
        "lost": "## Совпадений не найдено",
    }
    for key in ("original_changed", "downgraded", "lost", "unchanged"):
        out += [titles[key], ""]
        out += _table(groups[key]) if groups[key] else ["(пусто)"]
        out.append("")
    return "\n".join(out)


async def _apply(results: list[dict]) -> int:
    await database.init_db()
    n = 0
    for r in results:
        if r["new_state"] == "confirmed":
            await database.set_duplicate_of(r["id"], r["new_id"])
        elif r["new_state"] == "possible":
            await database.set_possible_duplicate_of(r["id"], r["new_id"])
        else:
            continue
        n += 1
    return n


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(_ROOT / "db" / "agent.db"), help="Path to agent.db")
    ap.add_argument("--report", default=str(DEFAULT_REPORT), help="Where to write the diff report")
    ap.add_argument("--apply", action="store_true", help="WRITE the new state to the DB (default: dry run)")
    args = ap.parse_args()

    database.configure(args.db)
    results = asyncio.run(_evaluate())
    report = build_report(results, _parse_verdicts(VERDICTS_FILE))
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(report, encoding="utf-8")
    counts = Counter(r["category"] for r in results)
    print(f"{len(results)} rows evaluated: {dict(counts)}")
    print(f"report: {args.report}")

    if args.apply:
        print(f"applied {asyncio.run(_apply(results))} rows")
    else:
        print("dry run — DB untouched (use --apply to write)")


if __name__ == "__main__":
    main()
