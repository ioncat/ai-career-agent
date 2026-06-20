# Pivot 2 — Flutter Platform + Structured Pipeline

**Date:** 2026-06-20
**Status:** Active — Architecture decided, sequencing confirmed
**Scope:** Full UI migration to Flutter Web; Telegram removed entirely; pipeline structuring (JSON contracts + deterministic split)

---

## Context

Original pivot (2026-05-31) established Career Agent as a focused vertical service for PdM/PO/PM job search, with Telegram as primary UI. After running the pipeline end-to-end and testing models, three facts became clear:

1. **Telegram is removed entirely.** Friction-heavy for interactive use, splits attention between two clients, no competitive advantage. Flutter = the only client.
2. **Flutter Web first, mobile later.** All logic and UX on Flutter Web. Mobile = repackage when needed — no code rewrite, no App Store overhead now. Web Push API handles browser notifications.
3. **Pipeline must emit JSON, not markdown blobs.** LLM output fed to UI requires structured data. Prerequisite for EPIC-21 (deterministic/cognitive split).

---

## Product Vision — Career Counselor UX

The Flutter app is not a tracker or dashboard. It's a **career counselor** — guided, step-by-step workflow per vacancy that mirrors how a human consultant works with a candidate.

**Core principle:** We do the hard work. The user only makes decisions, adds context, edits what they don't like.

- We analyze the vacancy and candidate fit automatically — user doesn't trigger phases manually
- We surface pluses, minuses, and risky signals explicitly — user doesn't interpret raw text
- We present objections (barriers) and help the candidate address them — **competitive advantage** over generic CV generators
- We minimize cognitive load: user reads, decides, optionally edits — that's it
- Every interaction teaches us something to improve future generation quality

**Phase 2.5 (Objection Handling) is non-negotiable.** It lives in Flutter as a proper interactive UI component. When barriers are detected, the app presents them conversationally — the candidate responds/clarifies — then we generate a stronger, more defensible CV. This is why we're building a dedicated client.

**The Flutter app is what makes Career Agent a product, not a script.**

---

## Three Pillars

| # | Pillar | Status |
|---|--------|--------|
| 1 | **EPIC-21** — Python handles deterministic work (VacScore arithmetic, recommendation matrix, PDF render); LLM called only for 4 cognitive touchpoints | 📋 Planned |
| 2 | **Ollama-first testing** — validate pipeline logic cheap on free local/cloud model; final quality run on Claude | ✅ Decided (06-18) |
| 3 | **Flutter Web as sole UI** — Telegram removed; Web Push for notifications; web first, mobile port later | ✅ Decided 2026-06-20 |

---

## Full Service Logic

### Источники вакансий

```
RSS feeds (DOU + Djinni + job-monitor)     Manual URL (Flutter input)
              │                                       │
              └─────────────────┬─────────────────────┘
                                ↓
                         cv_fetch_jd
               URL → jd-parser service → JD.md
               Записывает в DB: url, title, site, published_at, user_id
               Возвращает: vacancy_id
               [нет LLM, нет профиля]
```

---

### Авто-пайплайн (запускается на каждой новой вакансии)

```
vacancy_id + JD.md
        ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 1 — JD Analysis + VacScore
Модель: Claude Haiku ($0.022/call)
Вход: JD.md + profile_json["domain_interests"] (~10 токенов)
      [полный PROFILE не нужен]
Выход:
  • VacScore (8 dims): company_tier, seniority, market_scope,
    company_type, company_stage_fit, domain_score,
    remote_policy, compensation → итог X.X/10
  • Archetype ("Execution-heavy Delivery PO")
  • North Star компании
  • Pain points (что сломано, почему нанимают)
  • Role balance (Execution / Discovery / Strategy / Ops %)
  • Expectations: explicit / implicit / hidden pressure / toxic zones
  • Language analysis (culture signals, dominant phrases)
  • "Who will NOT fit" — анти-паттерны
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        ↓
PHASE 2 — Candidate Fit Assessment
Модель: Claude Haiku ($0.029/call)
Вход: JD.md + Phase 1 output + полный PROFILE (system prompt, cached)
Выход:
  • fit_score (1–10)
  • Fit × VacScore recommendation:
      go / apply — strong match / take a chance / decline
  • Barriers (список: что не совпадает с JD требованиями)
  • Adaptation plan (как закрыть каждый gap)
  • Quick Scan (3 строки: fit + rec + key signal/barrier)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        ↓
Сохраняется: JD_analysis.md + analysis_json в DB
```

---

### Нотификация → решение пользователя

```
Phase 1+2 done
      ↓
Web Push → Flutter PWA (браузер / установленное приложение)
┌─────────────────────────────────────────┐
│ Product Owner — iSpeedtoLead            │
│ VacScore 7.6 · Fit 7/10 · apply ✅     │
└─────────────────────────────────────────┘
      ↓ клик
Flutter app открывается на этой вакансии

Пользователь видит в Flutter:
  • VacScore (разбивка по 8 dims)
  • Archetype + pain points
  • fit_score + barriers + adaptation plan
  • Recommendation: apply / decline / take a chance

        ↓ пользователь решает
"Генерировать CV"          "Архивировать"
        ↓                        ↓
  CV-пайплайн стартует       вакансия закрыта, конец
```

**Go/no-go = решение о генерации CV.** Пользователь не может принять его без fit_score + barriers — именно это даёт Phase 2. Обе фазы запускаются автоматически до того, как пользователь что-либо видит.

---

### CV-пайплайн (по запросу пользователя)

```
vacancy_id + user action "Генерировать CV"
        ↓
PHASE 2.5 — Objection Handling  [только если есть barriers]
Интерфейс: Flutter (интерактивный диалог)
Логика:
  Система показывает barrier → пользователь отвечает / уточняет
  → классифицируется: снят / частично снят / остаётся
  → формируется adaptation brief для Phase 3
[Конкурентное преимущество — без этого CV generic]
        ↓
PHASE 3 — CV Generation
Модель: Claude Sonnet
Вход: JD.md + Phase 1+2 output + PROFILE + adaptation brief (из 2.5)
Выход: CV.md (адаптированное под эту вакансию)
        ↓
PHASE 3.5 — CV Self-Review  [обязательно, пользователь не видит]
Модель: Claude Sonnet
Вход: CV.md + исходные требования JD
Выход: CV.md v2 (исправленная версия)
        ↓
PHASE 4 — Cover Letter
Модель: Claude Sonnet
Вход: CV.md v2 + JD + PROFILE + candidate tone preferences
Выход: Cover.md
        ↓
PDF render (services/pdf/ via CVAdapter — httpx POST /render)
        ↓
Web Push: "CV готов →"
        ↓
Flutter: CV preview + PDF download + "Подать заявку"
```

---

### Мультипользователь

```
feeds.json:
  { "user_id": 1, "feeds": ["dou.ua/...", "djinni.co/..."] }
  { "user_id": 2, "feeds": [...] }

RSS watcher:
  для каждого user_id → для каждого feed → новые вакансии
  → cv_fetch_jd(url, user_id)
  → авто-пайплайн(vacancy_id, user_id)
  → Web Push → users[user_id].push_subscription

Все DB записи: user_id FK везде
PROFILE: загружается по user_id из DB или skill/users/[id]/PROFILE.md
```

---

### Статусы вакансии в DB

```
new → analyzing (P1+P2 running) → analyzed (P1+P2 done, awaiting user)
    → generating (P3+4 running) → ready (CV + cover done)
    → applied → archived
```

---

## Phase Roadmap

### Phase A — Unblock auto-pipeline (1–2 days)

1. ✅ **`profile_json` schema + population** — `CandidateProfile` (contracts/profile.py), `parse_profile_md()` (core/profile_loader.py), stored in DB on startup, passed via AgentDeps. Done 2026-06-20.
2. ✅ **`last_call_usage` on `OllamaProvider`** — property added, shape matches ClaudeProvider. Done 2026-06-20.
3. ✅ **`cv_fetch_jd` returns `vacancy_id`** — split into `fetch_jd(deps, url) -> int` + `cv_fetch_jd()` tool wrapper; `FetchError` exception. Done 2026-06-20.
4. ✅ **Semaphore on concurrent LLM calls** — `asyncio.Semaphore(RSS_CONCURRENCY)` in RSSWatcher; guards cv_fetch_jd after notification. Done 2026-06-20.
5. 🟡 Web Push subscription endpoint + send utility
6. 🟢 Logic test on Ollama (`gemma4:31b-cloud`) — validate data flow, free
7. ✅ **Quality run on Claude Haiku P1 + Haiku P2** — tested 2026-06-20 on vacancy #120; both phases on Haiku confirmed as production choice.

### Phase B — JSON contracts (foundation for Flutter) (3–5 days)

8. 🔴 EPIC-21 Task 2: Pydantic JSON contracts for Phase 1+2, Phase 3+3.5, Phase 4
   - Phase 1+2 → `{analysis: {...}, vacscore_dims: {8 fields}, fit_score, barriers: [...], adaptation: [...]}`
   - Phase 3+3.5 → `{cv_md: str, review: {...}}`
   - Phase 4 → `{cover_md: str}`
9. 🔴 EPIC-21 Task 3: VacScore composite formula + Fit×VacScore recommendation matrix → Python
   - LLM returns only dim scores; Python computes VacScore and recommendation
   - Eliminates LLM prose arithmetic (verified bug in all three models tested)
10. 🟠 FastAPI: JSON endpoints for Flutter (`GET /api/vacancies`, `GET /api/vacancies/{id}/analysis`, etc.)

### Phase C — Flutter MVP (1–2 weeks)

11. 🟠 Flutter: vacancy list screen (replaces HTMX tracker)
12. 🟠 Flutter: vacancy detail screen (Phase 1+2 JSON rendered as cards)
13. 🟠 Flutter: Phase 2.5 objection handling UI (interactive dialog)
14. 🟡 Flutter: trigger CV generation from app
15. 🟡 Flutter: CV preview + PDF download

### Phase D — Quality & Polish

16. 🟡 EPIC-21 Tasks 4–6: Python FSM orchestrator (full deterministic skeleton)
17. 🟢 Flutter: profile editing
18. 🟢 Flutter: mobile repackage (no code rewrite — Flutter Web → Flutter Mobile)

---

## Critical Path

```
Phase A (auto-pipeline) → Phase B (JSON) → Phase C (Flutter MVP) → Phase D (polish)
```

Phase A and start of Phase B are independent — can overlap.

---

## What Does NOT Change

- Python/FastAPI backend — stays
- SQLite — stays
- All pipeline tools (`cv_fetch_jd`, `cv_analyze`, `cv_generate`, `cv_cover`) — stays
- Multi-user model — stays
- RSS watcher + job-monitor service — stays
- `services/pdf/` render service — stays

**What is removed:** Telegram bot, aiogram handlers, all Telegram-specific code.

---

## Pipeline Economics

**RSS inflow:** 10–30 vacancies/day per user (DOU + Djinni + LinkedIn combined).

### Cost per vacancy — model options

| Approach | Cost/vacancy | Monthly (20/day, 1 user) |
|----------|-------------|--------------------------|
| Sonnet on both phases | ~$0.11 | ~$66 |
| Haiku P1 + Sonnet P2 | ~$0.07–0.09 | ~$42–54 |
| **Haiku P1 + Haiku P2 (both auto)** | **~$0.051** | **~$31** |

**Decision: Haiku on both phases.**

Tested 2026-06-20 on vacancy #120. Haiku Phase 2 cost $0.029, 46s, 14 947 chars output.

### Haiku Phase 2 quality — test observations (vacancy #120)

- **Barriers**: all 4 correctly identified with specific evidence from PROFILE:
  - ❌ Microservices/API reasoning — no evidence in profile
  - ⚠ Cost-of-delay framing — metrics-driven but not native language
  - ⚠ Cycle-time/WIP instrumentation — NPS/error metrics present, sprint-level not
  - ⚠ Team size 8+ — not confirmed in profile
- **Fit breakdown table**: 11 JD requirements × candidate evidence, ✅/⚠/❌ per row
- **Adaptation plan**: 5 concrete actions with ready CV language (not generic) — e.g. "reframe HostiServer billing work as cost-of-delay reasoning", "bridge microservices gap with honest ramp intent"
- **Recruiter objections**: 5 specific Q&A pairs with prepared answers
- **Phase 2.5 trigger check**: correctly identified team-size objection as requiring clarification before CV generation
- **Known issue**: fit_score inconsistency — Quick Scan says 6.5, Internal Analysis says 7.0. Same arithmetic self-override bug as Phase 1. Fixed by EPIC-21 Task 3 (Python computes scores from dim outputs).

**Conclusion:** Haiku Phase 2 quality is close enough to Sonnet for production auto-pipeline. Quality gap may exist on edge cases (very complex JDs, subtle culture signals) — monitor after rollout. Sonnet remains available as upgrade path per-vacancy if needed.

$31/month for a user in active job search (20 vacancies/day) is acceptable. Sonnet upgrade path: +$11/month.

### Alternative: GLM-5.2 via Ollama — flat $20/month

GLM-5.2 is available via Ollama cloud for a flat $20/month subscription (vs pay-per-token on Claude API). At 20 vacancies/day that's ~600 analyses/month — at Haiku rates this would cost ~$31, so GLM-5.2 breaks even around 20/day and wins above that.

**Status:** Not tested for quality yet. Previous attempt returned 403 (access issue, not model quality issue). Needs:
1. Verify subscription/access method
2. Run Phase 1+2 quality test on same vacancy #120
3. Compare output vs Haiku baseline

If GLM-5.2 quality ≈ Haiku: flat $20/month regardless of volume = better economics for active users (30+ vacancies/day).

### Testing policy — until Flutter is live

All pipeline testing is local. External calls (Web Push, any outbound notification) are **banned in testing mode**. Rules:
- `AGENT_MODE=testing` must be set — already enforced in e2e_test.py
- LLM API calls: allowed (needed for quality testing)
- Web Push: disabled — no push subscriptions in test environment
- All output goes to stdout / local files only
- No external integrations until Flutter MVP (Phase C) is deployed

---

## Model Comparison — Phase 1 Quality (2026-06-20)

Tested on vacancy #120 (Product Owner — iSpeedtoLead, $1800–4500, remote). Same raw JD for all three via `scripts/test_ollama_pipeline.py` (reads `ollama/JD.md`).

### Run stats — Phase 1

| Model | Provider | Cost/run | Speed | Output |
|-------|----------|----------|-------|--------|
| Claude Sonnet 4.6 | API | ~$0.07 | ~30s | full |
| Claude Haiku 4.5 | API | $0.022 | 50s | 15 582 chars |
| Gemma4:31b-cloud | Ollama (free) | $0.00 | ~105s | full |

### Run stats — Phase 2 (Haiku only tested)

| Model | Provider | Cost/run | Speed | Output |
|-------|----------|----------|-------|--------|
| Claude Haiku 4.5 | API | $0.029 | 46s | 14 947 chars |

**Phase 1 + Phase 2 combined on Haiku: $0.051/vacancy**

### VacScore dimensions

| Dim | Weight | Sonnet | Haiku | Gemma | Verdict |
|-----|--------|--------|-------|-------|---------|
| company_tier | 12 | 2/4 | 3/4 | 3/4 ↑ | Sonnet консервативнее — спорно |
| seniority | 12 | 2/4 | 3/4 | 3/4 ↑ | Sonnet консервативнее — спорно |
| market_scope | 8 | 2/3 | 2/3 | 3/3 ↑ | Sonnet+Haiku правы — USA only |
| company_type | 18 | 3/3 | 3/3 | 3/3 | все согласны |
| company_stage_fit | 10 | 3/3 | 2/3 | 3/3 | Haiku осторожнее |
| domain_score | 25 | 3/5 | 3/5 | 4/5 ↑ | Sonnet+Haiku точнее — B2B lead gen ≠ user interests |
| remote_policy | 10 | 3/3 | 3/3 | 3/3 | все согласны |
| compensation | 5 | 3/3 | 2/3 | 3/3 | Haiku точнее — нет цифр в JD |
| **VacScore** | — | **7.5** | **7.6*** | **7.8** | *Haiku manually adjusted to 7.2 — arithmetic bug |

↑ = inflated vs Sonnet baseline

### Qualitative differences

| Check | Sonnet | Haiku | Gemma |
|-------|--------|-------|-------|
| Company name | iSpeedtoLead ✓ | "[unnamed in JD]" | "Not specified" ✗ |
| NOT Founder Proxy anti-signal | caught ✓ | caught ✓ | missed ✗ |
| Archetype label | Execution-heavy Delivery PO | Execution-heavy Delivery | Execution-heavy Technical PO |
| Phase 1/2 boundary | clean | §1.8 Fit Summary bleed | clean |
| Fast-exit culture (month 2) | caught ✓ | caught ✓ | partial |
| Month 3 pressure signal | caught ✓ | caught ✓ | mentioned |
| Visible prioritization score | caught ✓ | caught ✓ | missed ✗ |

### Conclusions

- **Sonnet = quality baseline.** Catches anti-signals, most precise on dims. Too expensive for auto Phase 1 ($0.07).
- **Haiku = Phase 1 production choice.** Quality ≈ Sonnet on structure and dims, 3.2× cheaper ($0.022). Two prompt fixes needed: (1) prevent Phase 2 bleed into §1.8; (2) remove prose VacScore arithmetic — moves to Python (EPIC-21 Task 3).
- **Gemma = logic testing only.** Free, structure holds. VacScore inflated ~+0.3. Misses Phase 2-level signals. Not for production.

**VacScore arithmetic bug (all three models):** LLM computes composite and can self-adjust the total. EPIC-21 Task 3 fixes: LLM returns dim scores only → Python computes VacScore → no override possible.

---

## Open Questions

- [ ] Flutter experience level — affects Phase C estimation
- [ ] Auth model in Flutter app (no auth on current web tracker)
- [ ] Web Push: HTTPS required — hosting decision needed before Phase A item 5
