# EPIC-22 — Flutter Platform (Pivot 2)

**Status:** 🔵 Active — Phase A (4/7 done)
**Priority:** P0
**Last updated:** 2026-06-20
**Source:** [`docs/delivery/PIVOT-2-FLUTTER-PLATFORM.md`](../PIVOT-2-FLUTTER-PLATFORM.md)

---

## Context

Pivot 2 replaces Telegram with Flutter as the sole client. Full architecture, product vision, service logic schemas, pipeline economics, and model comparison are in `PIVOT-2-FLUTTER-PLATFORM.md` — this EPIC is the delivery tracker.

**Three pillars:**
1. **EPIC-21** — Python handles deterministic work (VacScore arithmetic, recommendation matrix, PDF render); LLM called only for 4 cognitive phases
2. **Ollama-first testing** — validate pipeline logic free on local/cloud model before Claude spend
3. **Flutter Windows Desktop as primary target** — Telegram removed; same Flutter codebase runs Web/Mobile later with no rewrite; Desktop uses polling + `flutter_local_notifications`; Web Push (A5) kept for future web/mobile

**Platform decision (2026-06-20):** Flutter Windows Desktop first. No HTTPS required, no hosting, FastAPI on localhost. `flutter build windows` from the same codebase that will later ship as Web/Mobile.

---

## Problem

Career Agent has no dedicated client. Telegram was the primary UI — it is removed entirely. The pipeline currently:
- Returns string blobs, not structured data (Flutter needs JSON per phase)
- Has no auto-trigger from RSS → Phase 1+2 without user intervention
- Has no notification mechanism for Desktop (Web Push = browser API; Desktop needs polling + system tray)
- Has no Flutter app (Phase C)

The deterministic/cognitive split (EPIC-21) is required before Flutter makes sense — the app renders structured JSON, not markdown.

---

## Goal

**Flutter Web = production UI.** User opens the app, sees new vacancies with fit scores, decides to generate CV, gets it done — all without manual pipeline steps.

---

## User Story

```
As a PdM in active job search
I want a clean Flutter web app that shows me new vacancies with fit analysis automatically
So that I spend time only on decision-making and CV review, not on triggering pipeline steps
```

---

## Acceptance Criteria

**Phase A done when:**
- RSS → `cv_fetch_jd` → `vacancy_id` → Phase 1+2 runs automatically, no user trigger
- Web Push notification delivered to browser on Phase 1+2 completion
- Semaphore prevents rate limit on batch inflow

**Phase B done when:**
- All cognitive phases (P1+2, P3+3.5, P4) return structured JSON (Pydantic contracts)
- VacScore composite + Fit×VacScore recommendation computed in Python, not LLM
- FastAPI exposes JSON endpoints consumed by Flutter

**Phase C done when:**
- Flutter Web app: vacancy list + detail screens rendering Phase 1+2 JSON
- Phase 2.5 objection handling UI: barrier → user reply → classification → adaptation brief
- CV generation trigger from Flutter → PDF download in Flutter

**Phase D done when:**
- Python FSM orchestrator drives the full pipeline (EPIC-21 Task 4)
- Flutter profile editing
- Mobile repackage verified (no code rewrite — Flutter Web → Flutter Mobile)

---

## Phase A — Auto-pipeline unblock

| # | Task | Status | Done |
|---|------|--------|------|
| A1 | `CandidateProfile` schema + population from PROFILE.md (`contracts/profile.py`, `core/profile_loader.py`, `AgentDeps.profile`) | ✅ Done | 2026-06-20 |
| A2 | `OllamaProvider.last_call_usage` — matches ClaudeProvider shape; fixes cv_analyze crash on Ollama | ✅ Done | 2026-06-20 |
| A3 | `cv_fetch_jd` → `fetch_jd(deps, url) -> int` split; `FetchError`; auto-pipeline can chain Phase 1+2 | ✅ Done | 2026-06-20 |
| A4 | `asyncio.Semaphore(RSS_CONCURRENCY)` in RSSWatcher; guards cv_fetch_jd after notification | ✅ Done | 2026-06-20 |
| A5a | Web Push: `POST /api/push/subscribe` + `send_push()` utility — for future web/mobile target | 🟡 Next | — |
| A5b | Desktop notification: Flutter polls `GET /api/vacancies?status=analyzed&since=X` → `flutter_local_notifications` fires system tray alert — Flutter-side only, no new backend endpoint | ✅ Done | 2026-07-01 |
| A6 | ~~Logic test on gemma4:31b-cloud~~ → **absorbed by B4** (auto-pipeline orchestrator test covers this) | ➡️ → B4 | B4 |
| A7 | Quality run Haiku P1 + Haiku P2 — both phases confirmed as production choice | ✅ Done | 2026-06-20 |

**A5a note:** Web Push requires HTTPS — not needed for Desktop MVP. Implement now (small, reusable) to unblock future web/mobile target.
**A5b note:** Pure Flutter — polls existing `/api/vacancies` endpoint. No new backend work. Ships with Phase C Desktop app.

---

## Phase B — JSON contracts + Python determinism

| # | Task | Status | Depends on |
|---|------|--------|-----------|
| B1 | EPIC-21 Task 2: Pydantic JSON contracts for P1+2, P3+3.5, P4 in `contracts/pipeline.py` | ✅ Done | A3 |
| B2 | EPIC-21 Task 3: VacScore composite + Fit×VacScore matrix → Python; LLM returns dim scores only | ✅ Done | B1 |
| B3 | FastAPI JSON endpoints for Flutter: `GET /api/vacancies`, `GET /api/vacancies/{id}/analysis`, `GET /api/vacancies/{id}/cv` | ✅ Done | B1 |
| B4 | Auto-pipeline orchestrator: RSS → `fetch_jd` → Phase 1+2 → `save analysis_json` → Web Push | ✅ Done | — |
| B5 | `AUTO_ANALYZE` env flag in `rss_watcher.py` (`False` = stop after fetch; `True` = full-auto) | 🔴 Planned | — |
| B6 | `GET /api/vacancies/{id}/jd` endpoint — returns JD.md content as markdown | 🟠 Planned | — |
| B7 | `POST /api/vacancies/{id}/analyze` endpoint — stub now; wires to Phase 1+2 on LLM unlock | 🟠 Planned | B5 |

---

## Phase C — Flutter MVP

| # | Task | Status | Done |
|---|------|--------|------|
| C1 | Flutter: vacancy list screen (Fit/Attraction badges, rec chip, source badge, selected state) | ✅ Done | 2026-07-01 |
| C2 | Flutter: vacancy detail screen (VerdictCard, QuickOverview, FitDims, Attraction Breakdown, #id hero) | ✅ Done | 2026-07-01 |
| C3 | Flutter: Phase 2.5 objection handling UI (barrier card → user reply → submit → adaptation brief) | 🔴 Blocked | LLM required |
| C4 | Flutter: CV preview dialog (View CV button → VacancyCvDialog tabs CV/Cover) | 🔵 Partial | 2026-07-01 |
| C5 | Flutter: Web Push registration | ❌ N/A Desktop | Browser-only |
| C6 | Flutter: inbox filter includes `fetched` + `analysis_queued` statuses | 🟠 Planned | — |
| C7 | Flutter: detail screen JD view when p2==null (JD markdown + Analyze/Skip buttons) | 🟠 Planned | C6 |
| C8 | Flutter: `VacancyCard` "New" badge for `fetched`; `vacancyJdProvider` + `analyzeVacancy()` | 🟠 Planned | C6 |

**C1 done (2026-07-01):** Fluid Desktop design system — purple M3 `ColorScheme`, glassmorphic `AppShell`, custom `NavigationRail`, `VacancyCard` (hover, selected state, source badge, Fit/Attraction outlined pill badges, #id in title row, reload icon in header).
**C2 done (2026-07-01):** `VacancyDetailScreen` — `_VerdictCard` (full-width go/no-go colored container), `_QuickOverviewCard` (label:text rows with icons — Category green, Who they want blue, Barriers/Risks red, Warnings amber), Fit Dimensions expanded by default, Attraction Breakdown section, `#id` in hero title row. `_ActionBar`: Open JD + View CV + Decline + Generate CV.
**C4 partial (2026-07-01):** `VacancyCvDialog` — tabbed overlay (CV + Cover), `flutter_markdown` render, empty state per tab. `getCv()` in repo + `vacancyCvProvider`. Cover file glob fixed (`*Cover.md`). PDF download + generate polling pending LLM.
**C6–C8 (Inbox-first flow):** See [`docs/delivery/INBOX-FIRST-FLOW.md`](../INBOX-FIRST-FLOW.md). Flutter inbox shows `fetched` vacancies; unanalyzed → JD view + Analyze/Skip. Backend: B5–B7.

---

## Phase D — Quality & Polish

| # | Task | Status | Depends on |
|---|------|--------|-----------|
| D1 | EPIC-21 Task 4: Python FSM orchestrator (deterministic skeleton, Phase 2.5 pause-state) | 🟡 | B2 |
| D2 | Flutter: profile editing screen | 🟢 | C2 |
| D3 | Flutter: mobile repackage verification | 🟢 | C4 |
| D4 | Remove Telegram bot code (`core/telegram.py`, aiogram handlers, all Telegram-specific paths) | 🟢 | C1 |

---

## Dependencies

| Dependency | Status | Notes |
|-----------|--------|-------|
| EPIC-21 Task 1 (weasyprint PDF) | ✅ Done (2026-06-15) | PDF render service live |
| EPIC-21 Task 2 (JSON contracts) | 🔴 BLOCKER for Phase B | Must land before Flutter |
| EPIC-21 Task 3 (VacScore → Python) | 🟠 | Needed before B4 (auto-pipeline) |
| `fetch_jd() -> int` (A3) | ✅ Done | Auto-pipeline can chain |
| Web Push HTTPS infra | 🟡 for A5a only | Desktop MVP doesn't need it; deferred |

---

## What Does NOT Change

- Python/FastAPI backend — stays
- SQLite (aiosqlite) — stays
- All pipeline tools (`cv_fetch_jd`, `cv_analyze`, `cv_generate`, `cv_cover`) — stays
- Multi-user model — stays
- RSS watcher + job-monitor service — stays
- `services/pdf/` render service — stays

**What is removed:** Telegram bot, aiogram handlers, Telegram-specific code in `core/telegram.py` — Phase D4, after Flutter C1 is live.

---

## Open Questions

- [ ] **HTTPS for Web Push** — required by Web Push API. Not needed for Desktop MVP (A5b = polling). Revisit when web/mobile target starts.
- [ ] **Auth in Flutter Desktop** — single-user local app: no auth needed initially. Multi-user scenario: decide before Phase C multi-user support.
- [ ] **Flutter experience level** — affects Phase C estimation.
- [ ] **Phase 2.5 UX design** — barrier cards + reply flow needs UX design before C3.
