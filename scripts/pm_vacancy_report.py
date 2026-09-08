"""
scripts/pm_vacancy_report.py — deterministic corpus filter + keyword-frequency
scan for the general Product Manager/Owner vacancy market report (sibling to
scripts/ai_vacancy_report.py — see research/pm-vacancy-market-analysis-methodology.md).

Unlike ai_vacancy_report.py, this has no AI-signal requirement: the corpus is
every vacancy with a Product-track title. AI-related Product vacancies are
included as a natural subset of the whole market, not filtered out — same
title-track filter, reused verbatim from ai_vacancy_report.py (kept as a
literal duplicate rather than a shared import, matching that script's own
standalone-by-design rationale).

Four categories instead of ai_vacancy_report.py's Technologies/Skills: for
the general PM/PO market, "technology" isn't the organizing axis —
Methodologies / Tools / Domains / Requirements is.

Read-only — never writes to the DB or to vacancy files.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "db" / "agent.db"

# Same allowlist as ai_vacancy_report.py's _is_product_track — literal
# duplicate, not imported (this script is standalone by the same design
# choice as its sibling).
_TITLE_PRODUCT_TRACK_RE = re.compile(
    r"product manager|product owner|project manager|delivery manager|"
    r"program manager|business analyst|operations manager|"
    r"technical product manager|technical project manager",
    re.IGNORECASE,
)


def _is_product_track(title: str) -> bool:
    return bool(_TITLE_PRODUCT_TRACK_RE.search(title or ""))


# ── Frequency dictionary ──────────────────────────────────────────────────
# Vacancy-level presence per term, same convention as ai_vacancy_report.py.
# Not exhaustive by design — see that script's own dictionary-limitations
# note, same principle applies here: the LLM open-coding pass is expected to
# extend this over time.

METHODOLOGIES: dict[str, str] = {
    "Agile / Scrum": r"\bagile\b|\bscrum\b",
    "Kanban": r"\bkanban\b",
    # Bare "safe" is an ordinary English word ("safe environment") — the
    # lesson from ai_vacancy_report.py's \bcv\b bug applies here just as
    # hard. Require the framework context explicitly, never bare "SAFe".
    "SAFe (Scaled Agile Framework)": r"scaled agile|\bsafe agile\b|\bsafe®|\bsafe certif|\bsafe popm\b",
    "OKR": r"\bokrs?\b|objectives and key results",
    "WSJF": r"\bwsjf\b|weighted shortest job first",
    "RICE / ICE prioritization": r"\brice (?:framework|score|method)|\bice (?:framework|score)",
    "Lean / Lean Startup": r"lean startup|lean methodology|lean product",
    "Design Thinking": r"design thinking",
    "JTBD (Jobs-to-be-Done)": r"\bjtbd\b|jobs.to.be.done",
    "Waterfall": r"\bwaterfall\b",
}

TOOLS: dict[str, str] = {
    "Jira / Confluence": r"\bjira\b|\bconfluence\b",
    "Trello": r"\btrello\b",
    "Notion": r"\bnotion\b",
    "Miro / Mural": r"\bmiro\b|\bmural\b",
    "Figma": r"\bfigma\b",
    "Google Analytics": r"google analytics|\bga4\b",
    "Amplitude / Mixpanel": r"\bamplitude\b|\bmixpanel\b",
    "SQL": r"\bsql\b",
    "Productboard": r"productboard",
    "Asana": r"\basana\b",
    # "monday" alone collides with the day of the week — only the product's
    # own distinctive spelling counts.
    "Monday.com": r"monday\.com",
    # Named AI-specific tools/features that show up even in NON-AI-focused
    # product roles — added 2026-09-08 per explicit user request to track
    # named technology/tool granularity in the general market too, not only
    # in the AI-specific report. Tracked separately from the base tool
    # (bare "Figma" above) so the two can be compared.
    "Figma AI": r"figma ai",
    "GitHub Copilot / AI coding assistants": r"copilot|cursor\.?sh|cursor ai",
    "Notion AI": r"notion ai",
}

DOMAINS: dict[str, str] = {
    "Fintech": r"\bfintech\b|financial technology",
    "Healthtech / Medtech": r"\bhealthtech\b|health tech|\bmedtech\b",
    "Edtech": r"\bedtech\b|education technology",
    # Bare "gaming" catches office-perk mentions ("lounge and gaming zones")
    # as often as the actual industry — found live 2026-09-08 (vacancy #70,
    # Mobilunity: "separate rooms... multiple lounge and gaming zones" is an
    # office-benefits line, not a domain signal). Exclude the perk-noun
    # pattern explicitly; igaming/gambling/casino/betting stay unconditional
    # (no comparable false-positive context found for those).
    "Gaming / iGaming": r"\bigaming\b|\bgambling\b|\bcasino\b|\bbetting\b|"
    r"\bgaming\b(?!\s*(?:zone|room|area|lounge|corner|chair|console|pc|setup|table))",
    "E-commerce / Marketplace": r"e.commerce|\bmarketplace\b",
    "B2B SaaS": r"\bsaas\b",
    "Adtech": r"\badtech\b|advertising technology",
    "Martech": r"\bmartech\b|marketing technology",
    "Logistics / Supply chain": r"logistics|supply chain",
    "HR tech": r"hr.?tech|human resources technology",
    "Cybersecurity": r"cybersecurity|cyber security",
    # Added 2026-09-08 per user pushback — B2C is a large, previously-missing
    # segment, and often pairs specifically with mobile + subscription
    # (matches PROFILE.md's own named `mobile_subscription` Critical Blocker
    # category, a distinct combo from generic `mobile` alone).
    "B2C": r"\bb2c\b",
    "Mobile app product": r"mobile app(?:s)?\b",
    "Mobile subscription (B2C recurring revenue)": r"mobile.{0,20}subscription|subscription.{0,20}mobile app|"
    r"mobile.{0,20}recurring revenue|recurring revenue.{0,20}mobile",
}

REQUIREMENTS: dict[str, str] = {
    "Senior/Lead level language (general — see caveat)": r"\bsenior\b|\blead\b(?!ership)",
    "Explicit years-of-experience threshold": r"\d+\+?\s*years?",
    "Explicit English level (CEFR)": r"(?:english|англ[іi]йськ\w*|английск\w*)\D{0,20}?\b(?:a1|a2|b1|b2|c1|c2)\b",
    "Commercial/technical background (CS/eng degree)": r"computer science degree|engineering degree|"
    r"technical background|cs degree",
    "Product certification (CSPO/PSPO/SAFe POPM/PMP)": r"\bcspo\b|\bpspo\b|\bpmp\b|safe.{0,10}(?:po.?pm)|"
    r"certified scrum product owner",
    "Startup/Scaleup stage signal": r"\bstartup\b|\bscale.?up\b",
}

CATEGORIES: dict[str, dict[str, str]] = {
    "methodologies": METHODOLOGIES,
    "tools": TOOLS,
    "domains": DOMAINS,
    "requirements": REQUIREMENTS,
}


def _compile(cat: dict[str, str]) -> dict[str, re.Pattern]:
    return {label: re.compile(pattern, re.IGNORECASE) for label, pattern in cat.items()}


_COMPILED_CATEGORIES = {name: _compile(cat) for name, cat in CATEGORIES.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH), help="Path to agent.db")
    parser.add_argument("--out", default=None, help="Output JSON path")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, title, company, site, markdown_path FROM vacancies "
        "WHERE markdown_path IS NOT NULL AND markdown_path != ''"
    ).fetchall()

    corpus: list[dict] = []
    freq: dict[str, dict[str, int]] = {name: {label: 0 for label in cat} for name, cat in CATEGORIES.items()}
    scanned = 0
    missing_files = 0
    not_product_track = 0

    for row in rows:
        jd_path = Path(row["markdown_path"])
        if not jd_path.exists():
            missing_files += 1
            continue
        scanned += 1

        if not _is_product_track(row["title"] or ""):
            not_product_track += 1
            continue

        jd_text = jd_path.read_text(encoding="utf-8", errors="replace")

        matched_terms: dict[str, list[str]] = {name: [] for name in CATEGORIES}
        for cat_name, compiled in _COMPILED_CATEGORIES.items():
            for label, pat in compiled.items():
                if pat.search(jd_text):
                    freq[cat_name][label] += 1
                    matched_terms[cat_name].append(label)

        corpus.append(
            {
                "id": row["id"],
                "title": row["title"],
                "company": row["company"],
                "site": row["site"],
                "jd_path": str(jd_path),
                "matched_terms": matched_terms,
            }
        )

    result = {
        "total_vacancies_in_db": len(rows),
        "vacancies_scanned": scanned,
        "vacancies_missing_jd_file": missing_files,
        "vacancies_not_product_track": not_product_track,
        "pm_corpus_size": len(corpus),
        "term_frequency": freq,
        "corpus": corpus,
    }

    research_dir = Path(__file__).resolve().parent.parent / "research"
    out_path = Path(args.out) if args.out else research_dir / "pm_vacancy_report_raw.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    out_path.write_text(payload, encoding="utf-8")

    # Dated snapshot alongside the overwritten working copy — same rationale
    # as ai_vacancy_report.py's own dated snapshot, added same session
    # (2026-09-08): a future trend feature needs parseable historical JSON,
    # not just the numbers baked into each dated report's markdown tables.
    today = datetime.date.today().isoformat()
    dated_path = research_dir / f"pm_vacancy_report_raw_{today}.json"
    dated_path.write_text(payload, encoding="utf-8")

    print(f"Scanned: {scanned}/{len(rows)} (missing JD.md: {missing_files})")
    print(f"Not Product-track title (excluded): {not_product_track}")
    print(f"PM/PO corpus: {len(corpus)}")
    print(f"Written: {out_path}")
    print(f"Dated snapshot: {dated_path}")


if __name__ == "__main__":
    main()
