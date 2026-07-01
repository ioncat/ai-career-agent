# Inbox-First Flow — Implementation Plan

**Version:** 1.0 (2026-07-01)
**Status:** Planned — not started
**Related:** EPIC-22 Phase C (tasks C6–C8), Phase B (tasks B5–B7)

---

## Problem

Current pipeline is fully automatic: RSS → Phase 1+2 runs for every incoming vacancy without user involvement. The inbox shows only `analyzed` vacancies.

This breaks two things:
1. **Pay-per-analyze model** — user can't decide whether to spend a token on this vacancy before it's already analyzed.
2. **User control** — vacancies the user would skip are processed anyway.

---

## Target State

RSS → fetch JD only (status=`fetched`). User sees all incoming vacancies in the inbox. For each unanalyzed vacancy: reads the JD, decides Analyze or Skip. Analysis runs async; when done → notification fires → detail screen unlocks.

Full-auto remains available via `AUTO_ANALYZE=true` (env flag, no code changes).

---

## Two Modes

| | Inbox-first (default) | Full-auto |
|---|---|---|
| Trigger | `AUTO_ANALYZE=false` (default) | `AUTO_ANALYZE=true` |
| RSS → | fetch JD only | fetch JD + Phase 1+2 |
| Inbox shows | `fetched` + `analyzed` | `analyzed` only |
| User decides | Analyze / Skip per vacancy | receives result only |
| Fits | pay-per-analyze monetization | package monetization |
| Detail screen (p2=null) | JD + Analyze/Skip buttons | "анализ выполняется..." |

---

## Monetization Connection

- **Pay-per-analyze** → inbox-first: user sees JD, decides to spend a token.
- **Package (30 analyses)** → full-auto: all incoming vacancies auto-analyzed from pool.

The `AUTO_ANALYZE` flag is the only switch between models. No other code changes.

---

## Flow Diagram

```
RSS push
  ↓
fetch_jd() — save JD.md, status=fetched
  ↓
AUTO_ANALYZE?
  ├─ true  → Phase 1+2 auto → status=analyzed → notification
  └─ false → stop here

Flutter Inbox (shows fetched + analyzed)
  User opens fetched vacancy → reads JD
    ├─ Skip  → PATCH /decline → status=declined
    └─ Analyze → POST /analyze → status=analysis_queued
                    ↓ (async)
               Phase 1+2 runs
                    ↓
               status=analyzed → notification fires
                    ↓
               VacancyDetailScreen unlocks (p2 present)
```

---

## Task List

### Backend

| Priority | Task | Detail |
|----------|------|--------|
| 🔴 | `AUTO_ANALYZE` env flag in `rss_watcher.py` | `Settings.auto_analyze: bool = False`; `False` → stop after `fetch_jd`; `True` → existing full-auto path |
| 🟠 | `GET /api/vacancies/{id}/jd` | reads `vacancies/{user_id}/{folder}/JD.md` → `{"jd_md": "..."}` |
| 🟠 | `POST /api/vacancies/{id}/analyze` | stub: status → `analysis_queued`; wires to Phase 1+2 when LLM available |

**Already done (no changes needed):**
- 🟢 `GET /api/vacancies/{id}` — vacancy metadata
- 🟢 `PATCH /api/vacancies/{id}/decline` — Skip action
- 🟢 Desktop polling + notification on `status=analyzed`

### Flutter

| Priority | Task | Detail |
|----------|------|--------|
| 🔴 | Inbox filter: add `fetched`, `analysis_queued` | `_folderMatch('inbox')` — 4 statuses instead of 2 |
| 🔴 | `VacancyDetailScreen` — JD view when `p2==null` | Markdown render of JD + Analyze/Skip buttons (not "анализ выполняется...") |
| 🟠 | `VacancyCard` — "New" badge for `fetched` status | Status-aware styling; analyzed cards unchanged |
| 🟠 | `vacancyJdProvider` + `getJd()` in repo | `GET /api/vacancies/{id}/jd` → `String` (markdown) |
| 🟠 | `analyzeVacancy()` in repo + Analyze button | `POST /api/vacancies/{id}/analyze` → reload card |

**Already done (no changes needed):**
- 🟢 Polling + local notification (`VacancyListNotifier` + `NotificationService`)
- 🟢 Skip → Decline button in `_ActionBar`

---

## LLM Unlock Path

When Claude CLI becomes available:

1. `POST /api/vacancies/{id}/analyze` stub → replace with real Phase 1+2 call
2. Status transitions: `analysis_queued` → `analyzing` → `analyzed`
3. Polling already handles `analyzed` — notification fires automatically

One commit. No Flutter changes. No architecture changes.

---

## Status Lifecycle

```
fetched → analysis_queued → analyzing → analyzed
       ↘                                         
         declined
```

`fetched` — JD saved, no analysis  
`analysis_queued` — user triggered, waiting  
`analyzing` — Phase 1+2 running (future: real LLM)  
`analyzed` — full data available, notification sent  
`declined` — user skipped  
