# General Product Manager/Owner Vacancy Market Analysis — Methodology

**Type:** personal/operational market research — same class as `research/ai-product-vacancy-market-analysis-methodology.md`, not career-agent product discovery (`docs/discovery/`). Sibling task, confirmed 2026-09-08: same question ("what does the market want, what's worth prioritizing") minus the AI-specific angle, for the whole Product Manager/Owner market instead of just its AI-related slice.

**Purpose:** recurring snapshot of what Product Manager/Owner vacancies in the DB ask for — methodologies, tools, domains, requirements — ranked by frequency. Re-run periodically via `/pm-vacancy-report` as the vacancy DB grows.

---

## Relationship to the AI-related report

- **Corpus:** every vacancy with a Product-track title — **no AI-signal filter**. AI-related Product vacancies are included as a natural subset of the whole market, not excluded (confirmed 2026-09-08 — comparing the two reports side by side shows what's specific to AI-related demand vs. general market baseline).
- **Categories are different on purpose:** the AI report organizes around Technologies/Skills (because a specific technology stack is the differentiator there). For the general PM/PO market, technology isn't the organizing axis — **Methodologies / Tools / Domains / Requirements** is.
- **Same false-positive discipline, different pitfalls each time.** The AI report's dictionary bugs (`\bcv\b` matching résumé mentions, no Product-track title check at all) don't repeat here verbatim, but the *pattern* does — every short/common-word term needs its own specific false-positive check before being trusted:
  - **"SAFe"** — bare `\bsafe\b` collides with the ordinary English word "safe" ("safe environment," "safe workplace"). Requires explicit framework context (`scaled agile`, `SAFe agile`, `SAFe®`, `SAFe certif...`).
  - **"Monday.com"** — bare "monday" collides with the day of the week. Only the literal `monday.com` spelling counts.
  - **"Gaming / iGaming"** — bare "gaming" caught office-perk mentions ("lounge and gaming zones") as often as the actual industry (found live 2026-09-08, vacancy #70, Mobilunity). Fixed with a negative lookahead excluding `gaming (zone|room|area|lounge|corner|chair|console|pc|setup|table)`; `igaming`/`gambling`/`casino`/`betting` stay unconditional (no comparable false-positive context found for those).

## Known dictionary caveats (2026-09-08, first run)

- **"Senior/Lead level language" and "Explicit years-of-experience threshold" are both broad, general-market signals, not PM/PO-specific findings.** They measure whatever's in the JD text, same caveat as the AI report's "Senior/Lead" entry — report text must present them as general seniority/experience-threshold context, not a specific insight about the PM/PO discipline.
- **Domain terms measure *mention*, not *primary business*.** A company describing itself as spanning "cultural projects, capital markets, and gaming" (vacancy #57, Trilitech — a Web3 company) gets counted under Gaming/iGaming even though gaming is one of several stated areas, not the company's core business. This is an inherent limit of vacancy-level presence counting, not a bug to fix — worth an explicit caveat in the report rather than tighter regex, since there's no reliable way to detect "is this the PRIMARY domain" from text alone without LLM judgment (which the open-coding step, not the dictionary, is for).
- **"RICE / ICE prioritization" is scoped tightly (requires "framework"/"score"/"method" nearby) and may undercount** compared to a looser bare-acronym match — deliberate trade-off after the SAFe/gaming false-positive lessons above; a bare `\bice\b`/`\brice\b` match risked far more noise (ICE = immigration enforcement, weather; rice = food) than it was worth catching a few missed mentions.

## Pipeline

Same three-step shape as the AI report (`scripts/pm_vacancy_report.py` → open-coding spot-check → dated report). See `research/ai-product-vacancy-market-analysis-methodology.md`'s Step 2/3 sections for the full generic description — not duplicated here, the steps are identical in kind, only the script/dictionary/output paths differ:

1. `python scripts/pm_vacancy_report.py` → `research/pm_vacancy_report_raw.json` (overwritten working copy) + `research/pm_vacancy_report_raw_YYYY-MM-DD.json` (dated snapshot, added 2026-09-08 — same rationale as `/ai-vacancy-report`'s own snapshot, see that methodology doc's Step 1 for the full reasoning: insurance for a future trend feature, not read by anything yet)
2. Open-coding spot-check — sample JD.md files from the corpus, verify dictionary counts aren't false positives (the false-positive discipline section above exists because of exactly this step), extend the dictionary in `scripts/pm_vacancy_report.py` when a recurring term is missing.
3. Write `research/pm-vacancy-market-analysis-YYYY-MM-DD.md` — new dated file every run, never overwrite. Structure: four ranked category sections (Methodologies/Tools/Domains/Requirements) with vacancy counts + % of corpus, short narrative per section, notable patterns, dictionary changes this run.

## How to re-run this

Use `/pm-vacancy-report` (`.claude/commands/pm-vacancy-report.md`).
