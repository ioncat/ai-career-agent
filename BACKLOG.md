# career-agent — Backlog

> Last updated: 2026-07-01
> Epic format: post-pivot epics (13+) live in `docs/delivery/epics/`. This file = priority tracker + status overview.
> Pre-pivot epics (1–12): `docs/delivery/epics-archive/EPIC-01-12-pre-pivot.md`

---

## 🔵 P0 — [EPIC-22](docs/delivery/Epics/EPIC-22-flutter-platform.md) — Flutter Platform (Pivot 2)

**Goal:** Flutter Web = sole UI. Telegram removed. Pipeline emits JSON. RSS → auto Phase 1+2 → Web Push → Flutter.

**Status:** Phase C in progress (2026-07-01). C1+C2 done. C4 partial (CV preview). C3 blocked on LLM. C6–C8 + B5–B7 planned (Inbox-first flow). Full architecture: `docs/delivery/PIVOT-2-FLUTTER-PLATFORM.md`. Flow plan: `docs/delivery/INBOX-FIRST-FLOW.md`.

**Critical path:** Phase A (auto-pipeline) → Phase B (JSON contracts + EPIC-21 Tasks 2–3) → Phase C (Flutter MVP) → Phase D (polish + Telegram removal).

---

## 🔴 P0 — [EPIC-21](docs/delivery/Epics/EPIC-21-deterministic-vs-cognitive-pipeline.md) — Deterministic vs Cognitive pipeline split

**Goal:** Draw the boundary — deterministic work in Python (FSM orchestrator), LLM only for irreducible cognitive phases. Source: `docs/discovery/hypotheses/H-002`.

**Re-audited rev 2 (2026-06-15):** classification updated for VScore (composite formula + recommendation matrix → Python) and Phase 2.5 (interactive cognitive pause-state). PDF engine decided: **weasyprint**. Two older backlog items folded in (see below).

**Task 1 (weasyprint PDF) — ✅ Done (2026-06-15).** `services/pdf/render.py` rewritten: 520-line fpdf2 parser → 50-line weasyprint pipeline. Jinja2 A4 template, font-face CSS, interface preserved. Docker system libs added.

**Next up:** Task 2 — Pydantic JSON contracts for cognitive phases (P1+2, P3+3.5, P4) in `contracts/`. Task 0 — re-trace happy-path step count (H-002 baseline stale). See EPIC-21 for full task list.

---

## 🟡 Post-EPIC-21 — Docs & diagrams freshness review

After EPIC-21 lands: audit all docs and diagrams for staleness vs. implemented FSM.

- `docs/diagrams/EPIC-21-pipeline-fsm.html` — verify FSM states + sequence match final implementation
- `ARCHITECTURE.md` — update pipeline phases table, mode comparison table (Режим 4 description changes with Task 6)
- `CLAUDE.md` — update "Current phase" status line
- `docs/local-app.md`, `docs/system-flow.md` — verify they reflect FSM orchestrator, not agent-driven steps
- `README.md` — pipeline descriptions, any architecture diagrams
- `docs/discovery/Pipeline-Evolution.md` — add entry for Phase 3 (FSM, v7+)
- `docs/delivery/PIVOT-PLAN.md` — Phase 7 scope description may shift after FSM lands

> Trigger: EPIC-21 Task 4 (FSM orchestrator) merged. Run this review before closing the EPIC.

---

## ✅ VScore + Recommendation Matrix (2026-06-14)

- **VScore** — 8-dimension vacancy attractiveness score (1–10): company_tier, seniority, market_scope, company_type, company_stage_fit, domain_score (interest + longevity), remote_policy, compensation
- `prompts/pm/phase1_analysis.md` + `prompts/generic/phase1_analysis.md` — section 1.7 added (formula, output, domain_score detail)
- `skill/SKILL.md` — Quick Scan format: `**VScore:** X.X/10`; p1 JSON schema extended with `vacancy_score` + `vacancy_dims`
- `skill/users/1/PROFILE.md` — `## Vacancy Preferences` (domain_interests + company_stage_prefs); extensible per user, no code changes needed
- `web/reader.py` — `VacancyView.vacancy_score`; parsed from `analysis_json.p1.vacancy_score`
- `web/templates/tracker.html` — VScore column (green ≥7.5 / amber 5.5–7.4 / gray <5.5); colspan 12→13; search `.trim()` fix
- **Fit × VScore recommendation matrix** — `prompts/pm/phase2_fit.md` + `prompts/generic/phase2_fit.md` + `skill/SKILL.md`:
  - Hard blockers OR fit < 5 → `decline` always (VScore cannot override)
  - Fit 5–6 + VScore ≥7.5 → `take a chance — premium opportunity`
  - Fit 5–6 + VScore <5.5 → `decline — not worth the effort`
  - Fit ≥7 + VScore <5.5 → `apply — limited upside`
  - Labels are display-only (Quick Scan); DB stores base value

---

## ✅ P1 — Pipeline hardening (2026-06-04, 2nd session)

- `scripts/inbox_scan.py` — canonical recursive inbox scanner (title + Source URL parse, dedup vs `inbox/{user_id}/*/JD.md`, `raw_folder`, `--json`). Root cause: non-recursive `ls` missed folder-based drops → false "inbox empty". Both `SKILL.md` + `analyze.md` now mandate it.
- `/analyze` Step 0 → combined two-block menu (profile/mode + inbox), vertical-split columns, no round-trip.
- `services/pdf/render.py` — `render_md` now **cover-aware**: CV-header parsing only when a contacts-links line is present in first lines; else render as wrapped body. Fixes cover overflow.
- `prompts/pm/phase3_cv_draft.md` — CV contacts line fixed verbatim: `Email · Telegram · LinkedIn · ioncat.github.io` (LinkedIn always, no GitHub).
- `SKILL.md` PDF section + `analyze.md -pdf` — rewritten to use `services/pdf` only; removed deprecated `../callback-cv/cv_to_pdf.py` references.

---

## 🟡 P1 — Phase 2.5 Objection Handling (added 2026-06-05)

New pipeline step formalized in `skill/SKILL.md` → "Phase 2.5 — Objection Handling": when Key Barriers ≠ нет, resolve weaknesses interactively BEFORE CV draft; resolved evidence appended to PROFILE.md + JD_analysis.md.
**Follow-up:** dedicated `prompts/[skill_type]/phase2_5_objections.md` prompt file (currently spec lives in SKILL.md). Optional DB `analysis_json.p2_5`.

---

## 🟠 P1 — [EPIC-24](docs/delivery/Epics/EPIC-24-progressive-profile.md): Progressive Profile — Evidence Bank + Onboarding (updated 2026-07-02)

**Центральный элемент pipeline.** PROFILE.md сейчас = уже отфильтрованный CV. Phase 3 только перетасовывает одни и те же карты и не может найти сигналы которых нет в контексте.

**Решение — два слоя:**

```
skill/users/[id]/evidence.json   ← ЕДИНЫЙ JSON, не набор файлов MD
                                    Максимальная детализация по каждой роли:
                                    все что делал, все сигналы, все метрики
                                    Phase 3 читает нужные секции → богатый контекст

PROFILE.md                       ← только: Settings, Name variants, Contacts,
                                    Archetype, Vacancy Preferences, Honest Gaps
                                    Больше не хранит детали опыта
```

**Формат evidence.json (структура на проработку):**
```json
{
  "roles": [
    {
      "id": "hostserver_po",
      "company": "HostiServer.com",
      "title": "Product Owner — Platform & Operational Systems",
      "dates": "Jan 2018 – Oct 2021",
      "signals": {
        "discovery": ["CustDev через операционный диалог", "сегмент арбитражников", "JTBD без ярлыка"],
        "funnel": ["self-service portal", "off-hours cohort → automated flow", "order-to-payment"],
        "content": ["копирайтинг всего сайта", "лендинги", "тексты с одним другим человеком"],
        "team": ["онбординг + менторинг billing support", "informal head of support"],
        "client": ["pre-sales enterprise", "pilot negotiation", "VIP account management", "migration onboarding"],
        "marketing": ["Google Ads PPC", "conversion rate analysis", "competitor positioning"],
        ...
      },
      "metrics": { "nps": "+19→+48", "billing_errors": "-95%", "automation": "~100%", ... }
    },
    ...
  ]
}
```

**Онбординг-интервью (процесс):**
Провести сессию по каждой роли — не "расскажи о себе" а структурированный разбор:
- Что конкретно делал? Какие решения принимал?
- Что построил с нуля?
- Какие метрики двигал?
- Что было неожиданным (CustDev, сегменты, инсайты)?
- Что гордишься и что бы не стал повторять?

Результат → секция в `evidence.json`.

**Начать с HostiServer** — самый богатый и важный опыт, значительная часть незафиксирована (контент/копирайтинг, лендинги, полный масштаб поддержки).

**Затем:** Marketplace, InsulaLabs, SBC Distribution, General Servers.

**Влияние на pipeline:**
- Phase 3 получает `evidence.json` → может найти сигналы под конкретную вакансию
- Phase 2.5 консультирует evidence напрямую → меньше "не знаю есть ли кейс"

**Design doc:** `docs/discovery/progressive-profile.md` (gitignored — internal only) — архитектурное обоснование, vision, план реализации.
- PROFILE.md становится легче и актуальнее

**Статус:** не начат. Приоритет поднят с P2 → P1. Первый шаг: онбординг-сессия HostiServer.

---

## P0 — Market Research (do before next dev sprint)

### 🔴 Competitive landscape analysis

**Goal:** Understand the market before building further.

- Find similar services (AI-assisted job search, CV tailoring, fit analysis — PM-focused)
- Critique our strategy and positioning with real market data
- Verdict: is the gap real, what should we adjust?

**How:** Research prompt using `docs/discovery/product-thesis.md` + `docs/discovery/ideas.md` + README. Run against web search.
**Output:** `docs/discovery/competitive-analysis.md`

⚠️ **Reminder** — requested 2026-05-31, still not done.

---

## P0 — Foundation (post-pivot)

| Epic | Title | Status |
|------|-------|--------|
| [EPIC-13](docs/delivery/epics/EPIC-13-multi-user-data-model.md) | Multi-user data model | ✅ Done (2026-06-01) |
| [EPIC-14](docs/delivery/epics/EPIC-14-services-pdf.md) | services/pdf/ — Kill subprocess PDF | ✅ Done (2026-06-01) |
| [EPIC-15](docs/delivery/epics/EPIC-15-services-parser.md) | services/parser/ — Own the parser | ✅ Done (2026-06-01) |
| [EPIC-16](docs/delivery/epics/EPIC-16-services-job-monitor.md) | services/job-monitor/ — Move + redesign | ✅ Done (2026-06-01) |
| [EPIC-17](docs/delivery/epics/EPIC-17-onboarding.md) | Onboarding: PDF → Interview → Profile | ✅ Done Phase 1 (stub interview, 2026-06-01) |
| EPIC-18 | Rename agent-hub → career-agent | ✅ Done (2026-06-01) |
| [EPIC-19](docs/delivery/epics/EPIC-19-local-execution.md) | Local execution mode (web UI) | 📋 Planned |
| [EPIC-20](docs/delivery/Epics/EPIC-20-vacancy-path-standard.md) | Unified vacancy path standard | 📋 Planned |
| [EPIC-21](docs/delivery/Epics/EPIC-21-deterministic-vs-cognitive-pipeline.md) | Deterministic vs Cognitive pipeline split | 📋 Planned (P0 — Task 1 tomorrow) |

---

## ✅ P1 — Batch inbox: fix move-to-clean-folder flow (2026-06-02)

- `scripts/vacancy_track.py` — added `delete-inbox` subcommand (path traversal guard, idempotent)
- `skill/SKILL.md` — Batch Mode + Sequential Mode: `move-to-inbox` → `delete-inbox`
- Cleaned up stray duplicate `Senior Technical Product Manager AI — DOIT Software` folder

---

## ✅ P1 — Inbox deduplication (2026-06-02)

- `skill/SKILL.md` — Sequential Mode: step a.5 dedup (URL grep → skip/reprocess prompt)
- `skill/SKILL.md` — Batch Mode: silent dedup, `♻️ уже обработана` in table
- `.claude/commands/analyze.md` — step 3 dedup note added before inbox menu

---

## P1 — Testing & Operations

### 🟡 e2e_test.py — integration verification

**What:** manual integration test. Hits real Claude API + real services. Costs tokens.
**When to run:** after changes to cv_generate / cv_cover / cv_analyze / ClaudeProvider / CVAdapter, after major EPIC merge, when something seems broken.
**Not for:** scheduled monitoring (costs money). Use health_check.py for that.

**Prerequisites:** jd-parser :8001 + pdf-service :8002 running + ANTHROPIC_API_KEY in .env

```bash
# Start services if not running:
cd services/pdf && python -m uvicorn app:app --port 8002 &

# Run e2e (interactive terminal — answers y/n manually):
python scripts/e2e_test.py --id 48 --phase generate,cover

# Or non-interactive (auto-confirms all API calls):
python scripts/e2e_test.py --id 48 --phase generate,cover --auto-confirm
```

- [x] Contract Tests: ParserAdapter + CVAdapter (mock)
- [x] **e2e verify: generate+cover** — vacancy #48, CV.md ✅ PDF ✅ Cover.md ✅ ($0.10, 2026-06-02)
  - Fixed: `services/pdf/render.py` font path was relative `services/pdf/fonts/` → now absolute `_PROJECT_ROOT/fonts/`
  - Fixed: added `load_dotenv` to render.py so pdf-service picks up .env on startup
- [ ] e2e verify: full pipeline from URL (fetch → analyze → generate → cover)

### ✅ health_check.py — lightweight service monitor (2026-06-02)

- `scripts/health_check.py` — implemented: parser + pdf-service HTTP checks, SQLite SELECT 1, optional Telegram bot ping + alert on failure
- Exit 0 = all OK, exit 1 = any failure
- `--telegram` flag: also check bot token validity + send alert if down
- `--parser-url` / `--pdf-url` overrides for non-default ports

```bash
python scripts/health_check.py            # basic
python scripts/health_check.py --telegram # + bot check + alert
```

- [ ] Wire to Windows Task Scheduler (recurring)

### 🟡 Contract Tests
- [x] `tests/test_parser_adapter.py` — ParserAdapter: mock httpx, test parse/error/health paths
- [x] `tests/test_cv_adapter.py` — CVAdapter: mock httpx, happy path/error/network/construction (11 tests)

### 🟡 Multi-skill architecture
**Status: ✅ Phase 1 done (2026-06-01)**
- [x] `prompts/pm/` + `prompts/generic/` — all 5 phases per skill type
- [x] `skill_type` routing in all tools (cv_analyze, cv_generate, cv_cover)
- [x] `AgentDeps.skill_type` — default `'pm'`, seeded from DB user row
- [x] Tested: PM pipeline (SOLAR Digital ✅) + Generic pipeline (AlphaNova ✅)

**Phase 2:**
- [x] `skill_type` question in Telegram `/start` FSM — already in EPIC-17 Phase 1 (`core/telegram.py` line 268)

---

## P1 — Tracker: editable salary field

Replace static salary badge with inline-editable text input per vacancy row.

**Why:** salary often absent in JD or needs manual correction after the fact.

**How it works:**
- Tracker row: click `—` or existing value → `<input>` appears inline → blur/Enter → PATCH
- `PATCH /api/vacancies/{id}/salary` — writes `salary TEXT` (already in DB schema)
- Auto-fill: Phase 2 already extracts salary into `analysis_json.p2.salary` → write to `vacancies.salary` at analysis time (currently not wired)
- Display: `$4500` / `3000–4500 USD` / `—` if empty

**Tasks:**
- [ ] `web/api.py` — `SalaryUpdate` + `PATCH /api/vacancies/{id}/salary`
- [ ] `db/database.py` — `set_vacancy_salary(id, value)` helper
- [ ] `tracker.html` — replace `.salary-badge` static span with inline editable field; click-to-edit UX, blur saves
- [ ] `tools/cv_analyze.py` — wire `p2.salary` → `vacancies.salary` on phase 2 completion
- [ ] Tests: 3 API tests (set/clear/404) + 1 reader test

---

## P1 — Pipeline Cost Preview

Feature: cost estimate sent to user before full pipeline run.
Trigger: after `cv_fetch_jd` — JD.md is known, size is known.

```
💰 Оценка бюджета — [Vacancy title]
Phase 1 (анализ):    ~$0.04
Phase 2 (фит):       ~$0.06
Phase 3 (CV draft):  ~$0.05
Phase 3.5 (review):  ~$0.07
Phase 4 (cover):     ~$0.05
──────────────────────────
Итого:               ~$0.27

Запустить полный pipeline? [Да] [Только анализ] [Отмена]
```

- [ ] `tools/cv_estimate.py` — token estimate per phase + cost calc
- [ ] Fallback to baseline averages from `docs/discovery/Tokenomics.md` if no DB history
- [ ] Telegram inline keyboard: [Да] [Только анализ] [Отмена]

---

## ~~P1 — Детерминированный pipeline~~ → folded into [EPIC-21](docs/delivery/Epics/EPIC-21-deterministic-vs-cognitive-pipeline.md)

Merged 2026-06-15. The "agent generates content, code applies fixed template" principle and its checklist (strict JD_analysis.md / CV templates, inbox-flow extraction, SKILL.md step review) are now EPIC-21 Tasks 1–4 + 6.

---

## ~~P1 — PDF template system~~ → = [EPIC-21](docs/delivery/Epics/EPIC-21-deterministic-vs-cognitive-pipeline.md) Task 1

Merged 2026-06-15. Engine decision resolved: **weasyprint** (HTML/Jinja2 + CSS → PDF). playwright rejected (~300MB headless-Chrome dependency, heavier in Docker/CI). Drops fpdf2 (no colour emoji, manual spacing). Full task spec in EPIC-21.

---

## 🟡 Docker deploy on VM — next session

`docker-compose.yml` готов (5 сервисов). WeasyPrint требует GTK — только в Docker (Linux контейнер).

**Plan:**
1. На VM: `git pull && docker compose up --build`
2. Порты биндятся на `0.0.0.0` — доступно по IP виртуалки
3. Из Windows: `http://VM_IP:8080` (трекер), бот через Telegram

**launcher.py** — локальный запуск без Docker (все 5 сервисов в одном окне, sequential start, Ctrl+C убивает всё). PDF сервис на Windows без GTK не работает — только через Docker.

---

## ✅ Phase A blockers — auto-pipeline foundation (2026-06-20)

**Goal:** unblock the RSS → Phase 1+2 auto-pipeline by resolving 4 infrastructure gaps.

### #1 — CandidateProfile schema + population from PROFILE.md
- `contracts/profile.py` — `CandidateProfile(BaseModel)`: `skill_type`, `language`, `domain_interests`, `company_stage_prefs`; `phase1_context()` returns compact JSON for Phase 1 injection
- `core/profile_loader.py` — `parse_profile_md(text)`: parses `## Settings` key-value + `## Vacancy Preferences` YAML block; never raises
- `core/deps.py` — `AgentDeps.profile: CandidateProfile | None` field added
- `agent.py` — loads PROFILE.md from file, calls `parse_profile_md`, stores to DB + `deps.profile`
- `tests/test_profile_loader.py` — 20 tests (settings, YAML prefs, phase1_context, integration)

### #2 — OllamaProvider.last_call_usage
- `core/llm_client.py` — `last_call_usage` property on `OllamaProvider`; tracks `prompt_eval_count` / `eval_count` from Ollama response; matches ClaudeProvider shape (cost_usd=0.0, cache tokens=0); `log_session_summary()` added
- `tests/test_llm_client.py` — 4 new tests (None before first call, populated after, zero on missing counts, updates on second call)
- **Why:** `cv_analyze.py` logged token usage via `llm.last_call_usage` → AttributeError crash when `LLM_PROVIDER=ollama`

### #3 — cv_fetch_jd returns vacancy_id
- `tools/cv_fetch_jd.py` — split into `fetch_jd(deps, url) -> int` (core, auto-pipeline callable) + `cv_fetch_jd(ctx, url) -> str` (PydanticAI tool wrapper); `FetchError` exception replaces string error returns
- `tests/test_cv_fetch_jd.py` — rewritten: 26 tests covering both entry points, FetchError, duplicate/queued handling, vacancy_id propagation
- **Why:** auto-pipeline needs vacancy_id as int to chain Phase 1+2 without user interaction; old tool returned only a display string

### #4 — RSS batch semaphore
- `core/rss_watcher.py` — `asyncio.Semaphore(concurrency)` in `__init__`; guards `cv_fetch_jd` in `_process` (after Telegram notification, before parser+LLM)
- `core/settings.py` — `rss_concurrency: int = 2` + `RSS_CONCURRENCY` env var
- `agent.py` — passes `concurrency=settings.rss_concurrency` to `RSSWatcher`
- `tests/test_rss_watcher.py` — 5 new tests (default/custom concurrency, notification not gated, concurrency=1 serializes, concurrency=2 allows 2 parallel)
- **Why:** N queued vacancies → N parallel LLM calls → Anthropic rate limit (RPM/TPM) + Ollama GPU contention; semaphore scope will extend to cover Phase 1+2 auto-run
- **Tests total:** 320 → 362

---

## ✅ Ollama error handling + model testing (2026-06-18)

- **No-timeout mode** — `OLLAMA_TIMEOUT=0` → `read_timeout=None` in httpx (for slow thinking models like qwen3:8b that run 10+ min)
  - `core/llm_client.py` — `OllamaProvider.__init__`: `read_timeout = None if timeout == 0 else float(timeout)` → `httpx.Timeout(timeout=read_timeout, connect=10.0)`
  - Timeout error message shows `∞` when read timeout is None
- **done_reason logging** — every OllamaProvider call logs `model / elapsed / in / out / done_reason`
- **Truncation detection** — `done_reason='length'` → raises `LLMError` with actionable message (raise MAX_TOKENS or shorten input)
- **scripts/test_ollama_pipeline.py** — `--phase 1|2` flag: run Phase 1 only, Phase 2 only, or both; Phase 2 reads existing `phase1.md` from `ollama/` folder
- **Model comparison** (vacancy #120 — Product Owner iSpeedtoLead):

  | Model | Type | Phase 1+2 | Output | Rating |
  |-------|------|-----------|--------|--------|
  | qwen3:8b | local | 19 min | full | ★★★ |
  | glm-5.2:cloud | cloud | — | 403 paid | ❌ |
  | minimax-m3:cloud | cloud | ~157s | truncated | ❌ |
  | gemma4:31b-cloud | cloud | 105s | full | ★★★ |
  | cas/aya-expanse-8b | local | 29s | full | ★ |

  **Best for logic testing:** `gemma4:31b-cloud` (105s, full structure, free)
- **Tests**: 316 → 320 total (4 new OllamaProvider error path tests)

---

## ✅ RSS watcher hardening + inbox folder naming + Ollama provider (2026-06-17)

- **RSS watcher**
  - `core/rss_watcher.py` — notify-first (Telegram message before processing), salary extracted from title, status machine fix (fetching→done)
  - `core/rss_watcher.py` — concurrent processing via `asyncio.gather` (all queued vacancies fetched in parallel)
  - `web/api.py` — `_site_from_url()` + site set at webhook insert; fixes "?" site badge in tracker
  - `db/schema.sql` + `db/database.py` — `published_at` column (RSS publication date stored; backfilled from `created_at` for existing rows)
- **Inbox folder naming** — `{vacancy_id} — {role} — {company}` format
  - `contracts/parsed_document.py` — `company: str | None` field added to `ParsedDocument`
  - `services/parser/app.py` — `_extract_company()`: DOU from URL slug, Djinni from `<title>` tag
  - `tools/cv_fetch_jd.py` — DB insert before folder creation (to get vacancy_id), `_safe_folder_name()` strips forbidden Windows chars
- **Ollama LLM provider**
  - `core/llm_client.py` — `OllamaProvider` full httpx implementation: POST `/api/chat`, 300s timeout, `LLMUnavailableError` on connect fail
  - `core/settings.py` — `LLM_PROVIDER` / `OLLAMA_BASE_URL` / `OLLAMA_MODEL` env vars (`.env`)
  - `agent.py` — runtime branch: `LLM_PROVIDER=ollama` → `OllamaProvider`; default → `ClaudeProvider`
- **Tests**: 291 → 316 total

---

## ✅ start.vbs → launcher.py (2026-06-16)

Заменён на `launcher.py` — Python-оркестратор в одном CMD окне.

---

## ✅ RSS automation + local startup (2026-06-15)

- `scripts/import_seen_jobs.py` — imports seen_jobs.json → DB (`--today`, `--dry-run`); status="new"
- `services/job-monitor/feeds.json` — 7 feeds migrated from original job-board-monitor
- `services/job-monitor/monitor.py` — fixed .env path (was looking in services/job-monitor/, now project root)
- `docker-compose.yml` — removed `:ro` from web-tracker DB volume
- `run_*.bat` — individual bat files for each service (debugging)
- `start.vbs` — Windows Terminal launcher (split-pane, WIP)
- DB: user_id=1 (Alex, chat_id=319987251), user_id=2 (Maria, chat_id=637454887) — telegram_chat_ids set

---

## ✅ services/job-monitor — divergence from original is intentional (2026-06-15)

Our `services/job-monitor/monitor.py` was redesigned during EPIC-16 and is **more advanced** than the original `job-board-monitor` repo.

**Key difference:**
- Original (`E:\My files\0 My_Dev\my_prj\job-board-monitor\`) — pushes vacancies directly to **Telegram** (TELEGRAM_TOKEN + chat_id recipients)
- Ours (`services/job-monitor/`) — pushes vacancies to **career-agent webhook** (`POST {CAREER_AGENT_URL}/api/new-vacancy`) using career-agent integer `user_ids`

Do not sync from original — the delivery model is fundamentally different.

**One-time import of existing seen_jobs.json** (vacancies already delivered by original bot):
```bash
python scripts/import_seen_jobs.py --today --dry-run   # preview
python scripts/import_seen_jobs.py --today             # import today's entries
python scripts/import_seen_jobs.py                     # import all 830 entries
```
Status inserted: `new` — visible in tracker, not auto-processed by rss_watcher.

**To activate ongoing RSS automation:**
1. Create `services/job-monitor/feeds.json` from `feeds.example.json`
2. Set `CAREER_AGENT_USER_1=1` in `.env`
3. `docker compose up` — job-monitor will POST new vacancies to web-tracker webhook

---

## P2 — Onboarding (detail in EPIC-17)

- [ ] See [EPIC-17](docs/delivery/epics/EPIC-17-onboarding.md) for full User Story + tasks

---

## P3 — Infrastructure

- [ ] Telegram webhook mode (config flag, currently long polling)
- [ ] asyncio.Queue → Redis (when concurrent users justify it)

---

## P3 — MCP Server (AI Interoperability)

**Why this matters — the real motivation:**

Job search is the kind of task a personal AI assistant should own end-to-end on your behalf.
Not a tool you query manually — a capability your AI agent invokes for you.

Imagine: your personal Claude Project, custom GPT, or any MCP-compatible agent
can call Career Agent as a native tool — analyze a vacancy you forward it,
check your fit before you've even opened the link, trigger CV generation, track
where you've applied. The agent becomes your personal career strategist, not just
a chatbot. You close the job search loop without switching contexts.

That's the unlock: Career Agent as infrastructure for personal AI agents, not just
a standalone app. Any intelligent assistant with MCP support can become a
full-service job search partner for its owner — using this service as the backbone.

**What to expose as MCP tools:**

| Tool | Description |
|------|-------------|
| `analyze_vacancy` | URL or JD text → fit score, recommendation, barriers |
| `generate_cv` | vacancy_id + user_id → CV.md + PDF |
| `generate_cover` | vacancy_id + user_id → cover letter |
| `get_tracker` | user_id → list of vacancies with status, fit, applied |
| `set_applied` | vacancy_id → mark CV as submitted |
| `get_vacancy` | vacancy_id → full analysis + CV + cover |

**Stack:** FastMCP or manual MCP JSON-RPC server wrapping existing `web/api.py` + tools.
Auth: API key per user (tied to `users` table).

**Tasks:**
- [ ] Design MCP tool schema (names, params, return types)
- [ ] `services/mcp/` — FastMCP server wrapping existing logic
- [ ] Auth: `api_key` column on `users` table + MCP auth middleware
- [ ] `docs/mcp-integration.md` — how to wire Career Agent into Claude Projects / custom agents
- [ ] Test with Claude Projects + Claude Code agent as clients

---

## P4 — Extensions

- [ ] `tools/yt_transcribe.py`
- [ ] `tools/quote_store.py`
- [ ] `tools/email_draft.py`
- [ ] Job auto-submit (research feasibility first)

---

## P4.5 — Unit Economics Dashboard

- [ ] `web/api.py` — `GET /api/economics` JSON endpoint
- [ ] `web/templates/economics.html` — Chart.js dashboard:
  - Cost per vacancy (avg + distribution)
  - Phase breakdown (% of total)
  - Cache efficiency (cache_hit_rate, savings in USD)
  - Daily spend (cumulative chart)
  - Unit economics simulator (slider: price/vacancy → margin %)

---

## P5 — Polish & Docs

- [ ] README: Mermaid architecture + pipeline state machine diagrams
- [ ] QUICKSTART.md — one-command startup
- [ ] USER_GUIDE.md — Telegram commands + web tracker
- [ ] Prerequisites doc — external repos layout (post-pivot: irrelevant after EPIC-14/15/16 done)

---

## ✅ Done

### Pre-pivot (EPIC 01–12)
See `docs/delivery/epics-archive/EPIC-01-12-pre-pivot.md`

### Post-pivot
- **EPIC-18** — Rename `agent-hub` → `career-agent` (2026-06-01)
- **EPIC-13** — Multi-user data model: `users` table, `user_id` FK, default user seeding, user-scoped vacancy paths, tracker filter (2026-06-01, 241 tests)
- **EPIC-14** — services/pdf/: render.py + FastAPI /render endpoint, CVAdapter subprocess → httpx (2026-06-01, 235 tests)
- **EPIC-15** — services/parser/: stripped knowledge-mirror-parser, djinni+dou only, docker-compose updated (2026-06-01)
- Multi-skill routing Phase 1 — `prompts/pm/` + `prompts/generic/`, skill_type in AgentDeps (2026-06-01)
- **EPIC-17 Phase 1** — Telegram onboarding: /start FSM, PDF upload (pypdf), profile_json in DB, /update_profile, /set_skill, ClaudeProvider loads from DB, MULTI_USER_ENABLED flag (2026-06-01, 250 tests)

### Batch mode for inbox (2026-06-02)
- **Trigger**: 3+ vacancies in inbox → auto batch mode (no flags needed)
- **Flow**: "Processing N vacancies..." → Phase 1+2 silent for all → consolidated table → Approve / Try chance / Skip
- **Table**: #, Company — Role, Src, Fit, Rec (✅/⚠️/❌), Level/$, Key gap; sort ✅→⚠️→❌ + fit DESC
- **Sequential mode**: 1–2 vacancies → behavior unchanged
- **move-processed**: after Phase 1+2 (regardless of Phase 3+4 decision)

### URL deduplication + Local mode → Tracker (2026-06-02)
- **`normalize_url()`** — strips UTM/tracking params, trailing slash, lowercases host; all boards safe (IDs in path)
- **`extract_site()`** — auto-infers djinni/dou/linkedin/hh/other from URL hostname
- **`insert_vacancy()`** — always stores normalized URL; auto-infers site when not explicit
- **`get_vacancy_by_url()`** — matches on `normalized OR original` (legacy fallback for existing UTM rows)
- **`scripts/vacancy_track.py`** — lightweight CLI: `upsert` (idempotent, prints vacancy_id) · `update` (status + path) · `move-processed` (inbox → processed/)
- **`/analyze` + `SKILL.md`** — DB write + processed/ move steps wired into inbox processing flow
- **Tests** — +14 dedup/normalize/extract tests; 279/279 ✅

### Tracker: source grouping + site filter (2026-06-02)
- **`site` field exposed in tracker** — grouping rows by date → source (DOU / Djinni / LinkedIn); recommended first within each source group
- **Site chip per row** — colored badge (DOU green, Djinni blue, LinkedIn navy) visible at all times, survives JS sort
- **Source filter dropdown** — "All sources / Djinni / DOU / LinkedIn / Other"; state persisted in localStorage
- **Smart source-sep hide** — source separator hidden when filter removes all its rows
- **Sort** — `web/api.py`: date DESC → site ASC → rec_order (recommended=0, other=1, not-recommended=2)
- **`site_display` property** — `VacancyView`: djinni→Djinni, dou→DOU, linkedin→LinkedIn, unknown→capitalize
- **Tests** — 6 new `TestSiteDisplay` tests; full suite 259/259 ✅

### Skill pipeline improvements (2026-06-02)
- **Mode selection (Step 0)** — `/analyze` now asks Local vs API mode as the very first step, before inbox check and profile load; mode applies to entire session; `-l` and `-inbox` flags skip mode question
- **Inbox manual drop zone** — `vacancies/inbox_manual/` folder: drop `.md`/`.txt` files; checked on every `/analyze`; first-line URL → fetch pipeline, otherwise JD text; on success → moved to `processed/`; multi-file batch support; profile selection if multiple users
- **Cover letter two variants** — Phase 4 now always generates Variant A (narrative) + Variant B (bullets) side-by-side; templates in `prompts/pm/phase4_cover.md`
- **Ukrainian CV: no РЕЗЮМЕ header** — Rule 15 in `prompts/pm/phase3_cv_draft.md`: Ukrainian CV summary flows directly after headline, no section header
- **PDF paragraph spacing fix** — `cv_to_pdf.py`: `ln(1)` → `ln(4)` in `paragraph()` method; eliminates merged paragraphs in all CVs
- **Legacy KMP cleanup** — `kmp` → `parser` in tests, scripts, tool docstrings, EPIC-15 doc; no functional change
