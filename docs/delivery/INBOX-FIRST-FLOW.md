# Inbox-First Flow — Implementation Plan

**Version:** 1.1 (2026-07-03)
**Status:** 🟡 In Progress — backend #1–5 next
**Related:** EPIC-22 Phase C (tasks C6–C8), Phase B (tasks B5–B7), EPIC-23, EPIC-24, EPIC-21

---

## Problem

Current pipeline is fully automatic: RSS → Phase 1+2 runs for every incoming vacancy without user involvement. The inbox shows only `analyzed` vacancies.

This breaks two things:
1. **Pay-per-analyze model** — user can't decide whether to spend a token on this vacancy before it's already analyzed.
2. **User control** — vacancies the user would skip are processed anyway.

---

## Target State

RSS → fetch JD only (status=`fetched`). User sees all incoming vacancies in the inbox. For each unanalyzed vacancy: reads the JD, decides Analyze or Skip. Analysis runs async; when done → notification fires → detail screen unlocks.

Full-auto remains available via `ANALYSIS_MODE=full_auto` (env var, no code changes).

---

## Two Modes

| | Inbox-first (default) | Full-auto |
|---|---|---|
| Trigger | `ANALYSIS_MODE=inbox_first` (default) | `ANALYSIS_MODE=full_auto` |
| RSS → | fetch JD only | fetch JD + Phase 1+2 |
| Inbox shows | `fetched` + `analyzed` | `analyzed` only |
| User decides | Analyze / Skip per vacancy | receives result only |
| Fits | pay-per-analyze monetization | package monetization |
| Detail screen (p2=null) | JD + Analyze/Skip buttons | "анализ выполняется..." |

---

## Monetization Connection

- **Pay-per-analyze** → inbox-first: user sees JD, decides to spend a token.
- **Package (30 analyses)** → full-auto: all incoming vacancies auto-analyzed from pool.

The `ANALYSIS_MODE` env var is the only switch between modes. No other code changes.

---

## Flow Diagram

```
RSS push
  ↓
fetch_jd() — save JD.md, status=fetched
  ↓
ANALYSIS_MODE?
  ├─ full_auto   → Phase 1+2 auto → status=analyzed → notification
  └─ inbox_first → stop here

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
| 🔴 | `ANALYSIS_MODE` in `rss_watcher.py` + `Settings` | ✅ Done — `inbox_first` stops after fetch; `full_auto` runs Phase 1+2 automatically |
| ✅ | `GET /api/vacancies/{id}/jd` | reads JD.md from `markdown_path` → `{"jd_md": "..."}` · Done 2026-07-03 |
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
`analyzing` — Phase 1+2 running  
`analyzed` — full data available, notification sent  
`declined` — user skipped  

---

## Сводный план — строгая очерёдность

> Включает все незакрытые эпики. Группы: Backend → Flutter → DB Profile → Архитектура.

| # | Задача | Эпик | Зависит от | Зачем |
|---|--------|------|-----------|-------|
| 1 | `GET /api/config` → `{llm_provider, model}` | EPIC-23 T4 | — | Flutter узнаёт какой провайдер активен |
| 2 | `ANALYSIS_MODE` в `rss_watcher.py` + `Settings` + `GET /api/config` | EPIC-22 B5 | — | ✅ Done — `inbox_first` \| `full_auto`; виден в Flutter через /api/config |
| 3 | Проверить/добавить `PATCH /api/vacancies/{id}/decline` | EPIC-22 B5 | — | Flutter кнопка Skip |
| 4 | `GET /api/vacancies/{id}/jd` → `{jd_md}` | EPIC-22 B6 | #2 | ✅ Done — Flutter читает JD без анализа |
| 5 | `POST /api/vacancies/{id}/analyze` — реальный (claude_cli) | EPIC-22 B7 | #2, EPIC-23 | Пользователь нажимает Analyze → Phase 1+2 через claude_cli |
| 6 | Flutter: inbox показывает `fetched` + `analysis_queued` | EPIC-22 C6 | #2, #4 | Вакансии без анализа видны в инбоксе |
| 7 | Flutter: `VacancyDetailScreen` — JD-режим (p2==null) + кнопки Analyze/Skip | EPIC-22 C7 | #3, #4, #5 | Полный UI для необработанной вакансии |
| 8 | Flutter: `VacancyCard` — бейдж "New" для `fetched` | EPIC-22 C8 | #6 | Визуальное различие новых вакансий |
| 9 | Flutter: `vacancyJdProvider` + `analyzeVacancy()` в репо | EPIC-22 C8 | #4, #5 | Провайдер данных + action для кнопок из #7 |
| 10 | Flutter Settings: показать активный LLM провайдер | EPIC-23 T5 | #1 | Видно что работает claude_cli, не API |
| 11 | Phase 2.5 write-back → MERGE в `progressive_profile` | EPIC-24 T5 | EPIC-23 | Сигналы из objection handling накапливаются в DB профиле |
| 12 | Phase 3 evidence reader → читает roles[] из `progressive_profile` | EPIC-24 T6 | #11 | Богатый контекст при генерации CV из DB профиля |
| 13 | `GET /api/users/{id}/progressive_profile` | EPIC-24 T8 | #12 | Flutter читает DB профиль |
| 14 | Trim PROFILE.md — убрать Experience + Additional Evidence | EPIC-24 T7 | #12 | PROFILE.md тонкий; опыт живёт в DB |
| 15 | Pydantic JSON contracts для cognitive phases | EPIC-21 T2 | — | Типизация контрактов pipeline (параллельно #11–14) |

**Группы:**
- **#1–5** — Backend foundation (~1–2 дня)
- **#6–10** — Flutter MVP с inbox-first UX (~2–3 дня)
- **#11–14** — DB profile в production pipeline
- **#15** — архитектурный рефактор, не блокирует UX
