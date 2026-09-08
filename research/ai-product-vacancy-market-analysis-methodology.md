# AI-Related Product Vacancy Market Analysis — Methodology

**Type:** personal/operational market research (candidate's own job-search intelligence) — **not** career-agent product discovery. Deliberately kept out of `docs/discovery/`, which is reserved for research about the career-agent tool itself (e.g. `docs/discovery/role-balance-taxonomy-discovery-2026-09-06.md`). This distinction was confirmed 2026-09-08 after the first draft of this file briefly lived under `docs/discovery/` by mistake.

**Purpose:** recurring snapshot of what AI-related Product Manager/Owner vacancies actually ask for — technologies, skills, requirements, tools — ranked by how common each is, so the candidate can prioritize what's worth learning/building evidence for. Re-run periodically (manually, via `/ai-vacancy-report`) as the vacancy DB grows, producing a new dated report each time so trend-over-time is visible.

**Precedent:** same hybrid methodology already used once for career-agent's own role-balance taxonomy discovery — keyword frequency (deterministic) + LLM open-coding (qualitative), triangulated together rather than trusting either alone.

---

## Pipeline

### Step 1 — Deterministic filter + frequency scan (`scripts/ai_vacancy_report.py`)

Read-only script, no LLM calls. Two jobs:

**1a. Corpus filter — which vacancies count as "AI-related Product"?**

- **Title match** (strong signal, no further check): title contains AI/ML/LLM/GenAI/GPT/"artificial intelligence"/"machine learning".
- **Body match** (needs a second signal — a single incidental mention must not qualify a vacancy that isn't actually about AI): the same term set appears 2+ times in the JD body, OR appears once **and** the JD has a Requirements/Responsibilities-shaped heading section at all (cheap proxy for "this is a structured JD, the mention is probably load-bearing, not a stray company-blurb line").

This mirrors the false-positive-guard principle already used in `tools/cv_prefilter.py`'s mobile-domain check (single mention ≠ requirement; needs corroborating context) — same idea, applied generically instead of to one fixed phrase.

**1b. Frequency dictionary — per-vacancy presence, not raw occurrence count**

Four categories (Technologies / Skills / Requirements / Tools), each a dict of `{label: regex}`. For the filtered corpus, count how many *vacancies* mention each term at least once (not how many times) — so one JD repeating a term ten times doesn't outweigh ten JDs mentioning it once.

**Known limitations of the dictionary (as of 2026-09-08, first run):**
- **Not exhaustive.** It only counts terms someone thought to add. Step 2 (open-coding) exists specifically to catch what it misses — when it finds a recurring term not in the dictionary, add it back in so the *next* run catches it for free (the dictionary should grow with each run, not stay frozen).
- **"Senior/Lead level required" measures general seniority language anywhere in the JD, not an AI-specific requirement.** Useful market context (are AI-related PM roles skewing senior?), but report text must not present it as "an AI-specific ask."
- **"A/B testing for AI features" actually measures any A/B-testing mention** — the dictionary can't tell whether the A/B testing is about AI features specifically or general product experimentation. Same caveat applies.
- **A hard bug already found and fixed once:** an early version matched bare `\bcv\b` intending "computer vision" and instead caught "send us your CV" (résumé) on 37 vacancies — a reminder that any 2-3 letter acronym needs an explicit false-positive check before trusting its count, not just after a report is published citing it.

Output: `research/ai_vacancy_report_raw.json` — corpus list (id/title/company/site/match_reason/matched_terms per vacancy) + frequency table. Overwritten fresh each run — this is the working copy Step 2 reads.

**Also writes a dated snapshot** (added 2026-09-08): `research/ai_vacancy_report_raw_YYYY-MM-DD.json`, identical content, never overwritten on a later run. Exists so a future trend feature (e.g. a Flutter chart of how a term's % changed over time) has clean parseable JSON per historical run to read, instead of having to scrape numbers back out of each dated report's markdown tables. Not read by anything yet as of 2026-09-08 — pure insurance for whenever 3+ dated reports exist and a trend view becomes worth building (at that point, per the earlier discussion, a small `agent.db` table — `report_date`/`category`/`term`/`count` — populated from these snapshots is the right next step, not a separate database).

Both JSON outputs are gitignored (`research/*_raw.json`, `research/*_raw_*.json`) — regenerable from the DB at any time, no reason to version the raw data itself.

### Step 2 — LLM open-coding pass (manual, by whoever runs `/ai-vacancy-report`)

Read `research/ai_vacancy_report_raw.json`, then:

1. **Spot-check a sample of the filtered corpus's JD.md files directly** (don't trust the dictionary counts blindly — the CV/computer-vision bug above is exactly the failure mode this step exists to catch). For a corpus this size (~300-400), reading every JD isn't practical in one pass — sample deliberately: the top few vacancies by term-match density, a handful of body-match-only ones (higher false-positive risk than title-matches), and any category whose count looks suspiciously high or suspiciously low relative to what AI-PM market knowledge would predict.
2. **Surface terms the dictionary missed** — read enough of the sampled JDs to notice patterns not already in `TECHNOLOGIES`/`SKILLS`/`REQUIREMENTS`/`TOOLS`. Add genuinely recurring ones back into `scripts/ai_vacancy_report.py`'s dictionaries for future runs.
3. **Classify importance, not just presence** — for each term that shows up meaningfully, note whether it tends to sit in a Requirements/must-have-shaped section vs. a Nice-to-have one, based on the sampled JDs. The frequency count alone doesn't distinguish "everyone requires this" from "everyone mentions this as a bonus."
4. **Write the narrative synthesis** — what's clearly dominant vs. genuinely rare, any surprising gaps, and (if this isn't the first run) what changed since the previous dated report.

### Step 3 — Write the dated report

`research/ai-product-vacancy-market-analysis-YYYY-MM-DD.md`. New file every run — never overwrite a previous date, so frequency shifts over time stay visible.

**Report structure:**

```markdown
# AI-Related Product Vacancy Market Analysis — YYYY-MM-DD

**Corpus:** N vacancies (of M total in DB) — title match: X, body match: Y

## Technologies
[ranked table: term | vacancy count | % of corpus]
[narrative: what's dominant, what's niche]

## Skills
[same shape]

## Requirements
[same shape — with the "Senior/Lead" and similar general-signal caveats stated explicitly]

## Tools
[same shape]

## Notable patterns / changes since last run
[only if a previous dated report exists to compare against]

## Dictionary changes this run
[terms added to scripts/ai_vacancy_report.py as a result of this run's open-coding pass, if any]
```

---

## How to re-run this

Use `/ai-vacancy-report` (`.claude/commands/ai-vacancy-report.md`) — orchestrates all three steps above in one invocation. See that file for the exact command sequence.
