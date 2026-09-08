# /ai-vacancy-report — AI-Related Product Vacancy Market Analysis

Recurring personal market-research snapshot: what do AI-related Product Manager/Owner
vacancies in the local DB actually ask for (technologies, skills, requirements, tools),
ranked by frequency. **Not career-agent product discovery** — this is the candidate's
own job-search intelligence, kept in `research/`, not `docs/discovery/`.

Full methodology (filter logic, dictionary caveats, why each step exists):
`research/ai-product-vacancy-market-analysis-methodology.md` — **read it before running
this**, don't rely on memory of it from a previous session.

---

## Step 0 — Ask report language (every run, confirmed 2026-09-08)

Before doing anything else, ask:

```
На каком языке готовить отчёт?
  [1] Оба (EN — уходит в гит, RU — для чтения) — по умолчанию
  [2] Только English
  [3] Только русский (не попадёт в гит — research/*_RU.md гитигнорится, а без EN-файла
      трекать в этом прогоне будет нечего)
```

Wait for the answer before Step 1. Default to [1] only if the user says something like
"как обычно"/"по умолчанию" — don't silently assume it, this is a real per-run choice,
not a fixed setting.

## Step 1 — Run the deterministic scan

```bash
python scripts/ai_vacancy_report.py
```

Writes `research/ai_vacancy_report_raw.json` (corpus + per-vacancy matched terms +
frequency table) plus a dated snapshot `research/ai_vacancy_report_raw_YYYY-MM-DD.json`
(never overwritten — future trend-feature insurance, not read by Step 2). Read-only
against the DB — safe to re-run anytime, always regenerates from current data.

Report the corpus size (`ai_related_corpus_size` in the output) before continuing —
if it looks wildly different from the previous run (methodology doc's own history,
or a prior dated report in `research/`), sanity-check *why* before trusting the rest.

## Step 2 — Open-coding pass (this is the part that needs real reading, not just the script)

Per the methodology doc's Step 2 section:
1. Sample JD.md files from the filtered corpus (`research/ai_vacancy_report_raw.json`
   → `corpus[].jd_path`) — don't trust the dictionary counts blindly, spot-check them.
   Prioritize: top term-match-density vacancies, a handful of `match_reason: "body"`
   ones (higher false-positive risk than title matches), and any category whose count
   looks surprisingly high or low.
2. Note any recurring term the dictionary in `scripts/ai_vacancy_report.py` missed —
   add it to the relevant `TECHNOLOGIES`/`SKILLS`/`REQUIREMENTS`/`TOOLS` dict so future
   runs catch it automatically. If the dictionary changes, re-run Step 1 once more
   before writing the report, so the numbers reflect the updated dictionary.
3. For terms that matter, note whether they tend to sit in a Requirements-shaped
   section vs. a Nice-to-have one across the sampled JDs.
4. If a previous dated report exists in `research/`, read the most recent one and
   note what changed.

## Step 3 — Write the dated report

Per the Step 0 answer:
- `research/ai-product-vacancy-market-analysis-YYYY-MM-DD.md` (English — tracked in git; `research/` is git-tracked, unlike `docs/discovery/`, specifically so this file has real version history)
- `research/ai-product-vacancy-market-analysis-YYYY-MM-DD_RU.md` (Russian — gitignored via `research/*_RU.md`, local only)

If both were requested: write English first (it's the source), then translate
faithfully — don't independently re-derive the Russian version's numbers/wording.
If the user picked Russian-only, tell them plainly in Step 4 that this run has no
English file and won't be trackable in git — don't just do it silently.

Structure: see the methodology doc's "Report structure" template — four ranked
sections (Technologies/Skills/Requirements/Tools) with vacancy counts + % of corpus,
short narrative per section, a "notable patterns / changes since last run" section
(only if a previous report exists), and a "dictionary changes this run" section
(only if step 2.2 added anything).

## Step 4 — Report back in chat

Short summary of the top findings per category (not the full report text — link to
the saved file). If this isn't the first run, lead with what changed.
