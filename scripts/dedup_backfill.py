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

--scan-missed (company identity + text-first rules, 2026-10-05) is a SEPARATE,
always-dry-run mode: it scans the vacancies that have NO duplicate flag at all
against OLDER vacancies (replaying ingestion order, as_of = the row's own
created_at) with the current classify_duplicate() — text containment >= 0.90
across any company/title, title+company with same-company identity — and writes
research/dedup-missed-scan-2026-10-05_RU.md, grouped confirmed / possible. It
never writes to the DB and refuses to combine with --apply. --watch 206,863
adds a pair-by-pair check of the listed vacancy ids to the report.
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

from core.dedup import (  # noqa: E402
    CONFIRM_THRESHOLD,
    TEXT_CONFIRM_THRESHOLD,
    containment as containment_of,
    profile_key,
    read_jd_text,
)
from db import database  # noqa: E402

DEFAULT_REPORT = _ROOT / "research" / "dedup-backfill-dryrun-2026-10-05_RU.md"
DEFAULT_MISSED_REPORT = _ROOT / "research" / "dedup-missed-scan-2026-10-05_RU.md"
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


# ── --scan-missed: find duplicates among rows that carry no flag ───────────────

async def _scan_missed() -> tuple[list[dict], dict[int, dict]]:
    """Classify every unflagged vacancy against OLDER rows (ingestion replay).
    Returns (findings, all_rows_by_id). Read-only."""
    async with database.get_db() as db:
        cur = await db.execute("PRAGMA table_info(vacancies)")
        if not any(r["name"] == "company_profile_url" for r in await cur.fetchall()):
            raise SystemExit(
                "company_profile_url column missing — run scripts/company_profile_backfill.py --apply "
                "first (additive schema migration)."
            )
        cur = await db.execute("SELECT * FROM vacancies ORDER BY id")
        all_rows = [dict(r) for r in await cur.fetchall()]
    by_id = {r["id"]: r for r in all_rows}
    findings: list[dict] = []
    for r in all_rows:
        if r["duplicate_of"] is not None or r["possible_duplicate_of"] is not None:
            continue
        text = await read_jd_text(r["markdown_path"], _ROOT)
        verdict = await database.classify_duplicate(
            r["user_id"], r["content_hash"],
            database._normalize_title(r["title"] or "", r["company"]), r["company"] or "",
            exclude_id=r["id"], new_text=text, before_id=r["id"],
            profile_key=profile_key(r["site"], r["company_profile_url"]),
            as_of=r["created_at"],
        )
        if verdict.confirmed_id is None and verdict.possible_id is None:
            continue
        findings.append({
            "id": r["id"],
            "state": "confirmed" if verdict.confirmed_id is not None else "possible",
            "orig": verdict.confirmed_id if verdict.confirmed_id is not None else verdict.possible_id,
            "containment": verdict.containment, "reason": verdict.reason,
        })
    return findings, by_id


async def _pair_containment(by_id: dict[int, dict], a: int, b: int) -> float | None:
    ta = await read_jd_text(by_id[a]["markdown_path"], _ROOT) if a in by_id else None
    tb = await read_jd_text(by_id[b]["markdown_path"], _ROOT) if b in by_id else None
    return None if ta is None or tb is None else containment_of(ta, tb)


def _desc(by_id: dict[int, dict], vid: int) -> str:
    r = by_id.get(vid)
    if r is None:
        return f"#{vid} (нет в БД)"
    ap = ", applied" if r["applied"] else ""
    return f"#{vid} {(r['title'] or '')[:45]} / {(r['company'] or '')[:25]} / {r['site']}{ap}"


async def build_missed_report(findings: list[dict], by_id: dict[int, dict], watch: list[int]) -> str:
    conf = [f for f in findings if f["state"] == "confirmed"]
    poss = [f for f in findings if f["state"] == "possible"]
    unflagged = sum(1 for r in by_id.values() if r["duplicate_of"] is None and r["possible_duplicate_of"] is None)
    reasons = ", ".join(f"{k}: {v}" for k, v in sorted(Counter(f["reason"] for f in conf).items()))
    out = [
        "# Скан пропущенных дублей (EPIC-26, 2026-10-05) — dry-run",
        "",
        f"Проверены все {unflagged} вакансий без флага дубля (из {len(by_id)}) против более СТАРЫХ вакансий "
        f"(порядок приёма, окно по тексту — 120 дней до created_at вакансии). Правила: текст с вложенностью "
        f">= {TEXT_CONFIRM_THRESHOLD:.2f} при любых названии/компании = подтверждённый дубль; название+компания "
        f"(та же компания по профилю/нормализованному имени) с вложенностью >= {CONFIRM_THRESHOLD:.2f} = подтверждённый, "
        "ниже = возможный. **Ничего не записано в БД** — ждёт решения владельца.",
        "",
        "## Итого",
        "",
        f"- Подтверждённые дубли: **{len(conf)}** ({reasons})",
        f"- Возможные дубли: **{len(poss)}**",
        "",
    ]
    if watch:
        out += ["## Контрольные пары", "", "| Пара | Вложенность | Что нашёл скан |", "|---|---|---|"]
        found = {f["id"]: f for f in findings}
        for i, a in enumerate(watch):
            for b in watch[i + 1:]:
                c = await _pair_containment(by_id, a, b)
                lo, hi = sorted((a, b))
                f = found.get(hi)
                if f and f["orig"] == lo:
                    verdict = f"#{hi} -> #{lo}: {f['state']} ({f['reason']})"
                elif lo in found and found[lo]["orig"] == hi:
                    verdict = f"#{lo} -> #{hi}: {found[lo]['state']} ({found[lo]['reason']})"
                else:
                    verdict = "связь не найдена"
                out.append(f"| #{a} / #{b} | {_fmt_c(c)} | {verdict} |")
        out.append("")
        for w in watch:
            f = next((x for x in findings if x["id"] == w), None)
            if f:
                out.append(f"- #{w} как новая вакансия: {f['state']} -> #{f['orig']} ({f['reason']}, {_fmt_c(f['containment'])})")
            else:
                out.append(f"- #{w} как новая вакансия: без флага (ничего старше не найдено)")
        out.append("")
    for title, group in (("## Подтверждённые", conf), ("## Возможные", poss)):
        out += [title, "", "| Новая (позже) | Оригинал (раньше) | Вложенность | Основание |", "|---|---|---|---|"]
        for f in sorted(group, key=lambda x: (-(x["containment"] or 0), x["id"])):
            out.append(f"| {_desc(by_id, f['id'])} | {_desc(by_id, f['orig'])} | {_fmt_c(f['containment'])} | {f['reason']} |")
        if not group:
            out.append("| (пусто) | | | |")
        out.append("")
    return "\n".join(out)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(_ROOT / "db" / "agent.db"), help="Path to agent.db")
    ap.add_argument("--report", default=str(DEFAULT_REPORT), help="Where to write the diff report")
    ap.add_argument("--apply", action="store_true", help="WRITE the new state to the DB (default: dry run)")
    ap.add_argument("--scan-missed", action="store_true",
                    help="dry-run scan of vacancies WITHOUT a duplicate flag (never writes)")
    ap.add_argument("--watch", default="", help="comma-separated vacancy ids to pair-check in the --scan-missed report")
    args = ap.parse_args()

    database.configure(args.db)
    if args.scan_missed:
        if args.apply:
            raise SystemExit("--scan-missed is dry-run only and cannot be combined with --apply")
        report_path = Path(args.report) if args.report != str(DEFAULT_REPORT) else DEFAULT_MISSED_REPORT
        watch = [int(x) for x in args.watch.split(",") if x.strip()]

        async def _go() -> tuple[str, list[dict]]:
            findings, by_id = await _scan_missed()
            return await build_missed_report(findings, by_id, watch), findings

        report, findings = asyncio.run(_go())
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
        print(f"{len(findings)} findings: {dict(Counter(f['state'] for f in findings))}")
        print(f"report: {report_path}")
        print("dry run — DB untouched")
        return
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
