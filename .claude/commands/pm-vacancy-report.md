# /pm-vacancy-report — General Product Manager/Owner Vacancy Market Analysis

Recurring personal market-research snapshot: what does the whole Product Manager/Owner
vacancy market in the local DB ask for (methodologies, tools, domains, requirements),
ranked by frequency. Sibling to `/ai-vacancy-report` — same class of task, no AI-signal
filter (the whole PM/PO market, AI-related roles included as a natural subset).
**Not career-agent product discovery** — kept in `research/`, not `docs/discovery/`.

Full methodology (why the categories differ from the AI report, dictionary
false-positive lessons already learned, caveats): `research/pm-vacancy-market-analysis-methodology.md`
— **read it before running this**, don't rely on memory of it from a previous session.

---

## Step 0 — Ask report language (every run, confirmed 2026-09-08 — same rule as `/ai-vacancy-report`)

Before doing anything else, ask:

```
На каком языке готовить отчёт?
  [1] Оба (EN — уходит в гит, RU — для чтения) — по умолчанию
  [2] Только English
  [3] Только русский (не попадёт в гит — research/*_RU.md гитигнорится, а без EN-файла
      трекать в этом прогоне будет нечего)
```

Wait for the answer before Step 1. Don't silently assume [1] — this is a real
per-run choice.

## Step 1 — Run the deterministic scan

```bash
python scripts/pm_vacancy_report.py
```

Writes `research/pm_vacancy_report_raw.json` plus a dated snapshot
`research/pm_vacancy_report_raw_YYYY-MM-DD.json` (never overwritten — future
trend-feature insurance, not read by Step 2). Read-only against the DB — safe to
re-run anytime.

Report the corpus size (`pm_corpus_size`) before continuing.

## Step 2 — Open-coding pass

Per the methodology doc:
1. Sample JD.md files from the corpus (`research/pm_vacancy_report_raw.json` →
   `corpus[].jd_path`) — spot-check dictionary counts, especially any short/common
   word term (the methodology doc's "false-positive discipline" section lists the
   ones already caught: SAFe, Monday.com, Gaming).
2. Add missing recurring terms to `scripts/pm_vacancy_report.py`'s dictionaries.
   Re-run Step 1 if the dictionary changed.
3. Note Requirements-shaped vs Nice-to-have-shaped placement for terms that matter.
4. If a previous dated report exists in `research/`, read the most recent one and
   note what changed.
5. If `research/ai-product-vacancy-market-analysis-*.md` has a report from the same
   or a nearby date, note what's specific to AI-related demand vs. this general
   baseline (that comparison is the whole point of running both).

## Step 3 — Write the dated report

Per the Step 0 answer:
- `research/pm-vacancy-market-analysis-YYYY-MM-DD.md` (English — tracked in git; `research/` is git-tracked, unlike `docs/discovery/`, specifically so this file has real version history)
- `research/pm-vacancy-market-analysis-YYYY-MM-DD_RU.md` (Russian — gitignored via `research/*_RU.md`, local only)

If both were requested: write English first (source), then translate faithfully —
never independently re-derive the Russian numbers/wording. If the user picked
Russian-only, tell them plainly in Step 4 that this run has no English file and
won't be trackable in git.

New file every run, never overwrite a previous date. Structure: four ranked
sections (Methodologies/Tools/Domains/Requirements) with counts + % of corpus,
short narrative per section, notable patterns, dictionary changes this run.

## Step 4 — Report back in chat

Short summary of top findings per category — link to the saved file, don't paste it.
