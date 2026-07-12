# EPIC-26 — Vacancy Deduplication & Re-publish Detection

**Status:** ✅ Done 2026-07-09
**Delivered:** see [CHANGELOG.md](../CHANGELOG.md) → 2026-07-09

**Goal:** Eliminate noise from cross-source duplicates (same JD on Djinni + DOU) and surface re-published vacancies that were previously declined or buried.

**Problem 1 — Cross-source duplicates:**
Same vacancy appears on Djinni and DOU with identical or near-identical text. Currently creates two separate DB entries with no link between them. User wastes time analyzing the same role twice.

**Problem 2 — Re-published/bumped vacancies:**
A vacancy already in DB (analyzed, declined, or buried) gets re-published or bumped in RSS feed. Current behaviour: URL already exists → silently ignored. User never knows the vacancy is active again. A declined vacancy that was re-posted remains declined and invisible.

---

## Design

**Duplicate detection — combo approach:**
- `content_hash` = sha256 of normalized JD text (lowercase, collapse whitespace, strip punctuation) — stored at fetch time
- `normalize(title)` + `company` fuzzy match — checked at insert time against existing DB entries for the same `user_id`
- Match rule: `content_hash` collision **OR** (normalized_title == normalized_title AND company == company)
- First entry in DB = original. Second entry = duplicate, `duplicate_of = original_id`
- Duplicates still created and appear in inbox — marked with badge "Дубль #X"
- Edge case: whitespace/formatting diff between sources → title+company catches it even if hash differs

**Re-publish detection:**
- RSS watcher / fetch receives URL already in DB
- Compare RSS `published_at` with stored `published_at`
- If `published_at` newer AND vacancy `status` = `declined` / `skipped`:
  - Update `published_at`, set `republished_at = now()`, transition status → `fetched`
  - Flutter badge: "↑ Повторно опубликована · Ранее отклонена"
- If vacancy `status` = `analyzed` / `inbox`: update `published_at` only, no status change, no badge
- If vacancy `status` = `analyzing` / active: ignore entirely

**Inbox sorting:**
- Old: `ORDER BY id DESC` (insertion order)
- New: `ORDER BY published_at DESC, id ASC`
- `published_at` already stored by RSS watcher; vacancies added manually = `published_at = created_at`

---

## DB changes (migrations)

| Column | Table | Type | Purpose |
|---|---|---|---|
| `duplicate_of` | `vacancies` | `INTEGER REFERENCES vacancies(id)` | FK to original if this is a duplicate |
| `content_hash` | `vacancies` | `TEXT` | sha256 of normalized JD text |
| `republished_at` | `vacancies` | `DATETIME` | Set when re-published after decline |

---

## Task list

**T1 — DB migrations** ✅
- `db/schema.sql`: add 3 columns
- `db/database.py`: migration `ALTER TABLE` for each; helper `find_duplicate(user_id, content_hash, norm_title, company) → int | None`

**T2 — Duplicate detection at fetch** ✅
- `tools/cv_fetch_jd.py`: compute `content_hash` after JD text parsed; call `find_duplicate`; set `duplicate_of` if match found; log duplicate link
- `core/rss_watcher.py`: same check at RSS insert time

**T3 — Re-publish detection in RSS watcher** ✅
- `core/rss_watcher.py`: on URL already-exists case, compare `published_at`; update fields + transition status per design above

**T4 — Inbox sort + API response** ✅
- `web/api.py`: change vacancy list `ORDER BY` to `published_at DESC, id ASC`; include `duplicate_of` and `republished_at` in list + detail responses

**T5 — Flutter model + UI badges** ✅
- `flutter/lib/models/vacancy.dart`: `duplicateOf`, `republishedAt` fields
- `flutter/lib/widgets/vacancy_card.dart`: "Dup #X" badge (secondary chip, subtle colour); "↑ Republished" badge (amber)
- Clickable badges → cross-navigation; hover tooltips
- No separate inbox section — all in same inbox, sorted by date

---

## Out of scope

- Merging duplicate vacancies (would lose analysis data from both)
- LLM-based semantic similarity (overkill for this problem)
- Dedup across users (separate user_id = separate namespace)
