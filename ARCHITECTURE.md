# Career Agent — Architecture

## Что это

AI-помощник для поиска работы. Читает вакансию, оценивает fit, генерирует CV и cover letter. Основная аудитория — Product Manager / Product Owner.

---

## Компоненты

```
┌─────────────────────────────────────────────────────────────────┐
│                        career-agent                             │
│                                                                 │
│  agent.py          — Telegram бот + RSSWatcher                  │
│  core/router.py    — PydanticAI Agent + tool dispatch           │
│  core/rss_watcher  — DB polling (status='queued')               │
│  tools/            — cv_fetch_jd, cv_analyze, cv_generate,      │
│                       cv_cover, cv_get_tracker                  │
│  web/api.py        — FastAPI: трекер + /api/new-vacancy         │
│  db/database.py    — aiosqlite CRUD                             │
└──────────────┬──────────────────────────────────────────────────┘
               │ httpx
       ┌───────┴────────┐         ┌──────────────────┐
       │ services/parser │         │  services/pdf    │
       │ jd-parser       │         │  pdf-service     │
       │ :8001           │         │  :8002           │
       │ URL → Markdown  │         │  Markdown → PDF  │
       └─────────────────┘         └──────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  services/job-monitor                                           │
│  RSS feeds → POST /api/new-vacancy → career-agent DB            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5 режимов запуска пайплайна

### Режим 1 — Автоматический (RSS)

```
job-monitor → POST /api/new-vacancy → web/api.py (DB: status=queued)
                                              ↓
                                    RSSWatcher (30s poll)
                                              ↓
                                     cv_fetch_jd → DB
                                              ↓
                              Telegram уведомление (Phase 1)
```

- **Кто запускает:** автоматически, без участия пользователя
- **API:** Anthropic API (через ClaudeProvider в фазах 2–4 — по запросу)
- **Конфиг:** `services/job-monitor/feeds.json`

---

### Режим 2 — Telegram: URL или текст JD

```
Пользователь → Telegram → TelegramBot → Router → tools → Claude API
```

- **Кто запускает:** пользователь отправляет URL или текст вакансии боту
- **API:** Anthropic API
- **Запуск:** `python agent.py`
- **Интерактив:** да — фазы по подтверждению

---

### Режим 3 — Claude Code + Anthropic API (тестирование / ручной запуск)

```
Пользователь → /pipeline <URL | file.md | ID>
                    ↓
             Claude Code запускает scripts/e2e_test.py
                    ↓
             Python инструменты → ClaudeProvider → Anthropic API
```

- **Кто запускает:** разработчик / тестировщик в Claude Code
- **API:** Anthropic API (через ClaudeProvider проекта)
- **Команды:**
  ```
  /pipeline https://djinni.co/jobs/123/        # URL
  /pipeline vacancies/djinni/2026-06/123/JD.md # готовый .md файл
  /pipeline 42                                 # vacancy_id из БД
  ```
- **Скрипт напрямую:**
  ```bash
  python scripts/e2e_test.py --url https://...
  python scripts/e2e_test.py --file path/to/JD.md
  python scripts/e2e_test.py --id 42 --phase generate,cover
  ```

---

### Режим 4 — Claude Code `/analyze` (локальный, без Anthropic API)

```
Пользователь → /analyze → skill/SKILL.md → Claude Code = LLM
                                ↓
                    prompts/[skill_type]/phaseN.md
                                ↓
                       vacancies/[Company — Role]/
```

- **Кто запускает:** пользователь в Claude Code
- **API:** ❌ не используется — Claude Code сам является LLM
- **Профиль:** `skill/users/[id]/PROFILE.md` (до EPIC-17)
- **Подробнее:** `docs/local-app.md`

---

### Режим 5 — Local Web UI (EPIC-19, запланировано)

```
Пользователь → браузер http://localhost:8080/app
                    ↓
             POST /analyze → FastAPI → ClaudeProvider → Anthropic API
                    ↓
             SSE прогресс → download CV.pdf + Cover.md
```

- **Кто запускает:** пользователь в браузере
- **API:** Anthropic API
- **Статус:** 📋 запланировано (EPIC-19)

---

## Сравнительная таблица режимов

| | Режим 1 (RSS) | Режим 2 (Telegram) | Режим 3 (Claude Code dev) | Режим 4 (/analyze) | Режим 5 (Web UI) |
|--|:---:|:---:|:---:|:---:|:---:|
| Anthropic API | ✅ | ✅ | ✅ | ❌ | ✅ |
| Пользователь вводит URL | ❌ | ✅ | ✅ | ✅ | ✅ |
| Текст JD (не URL) | ❌ | ✅ | ✅ (--file) | ✅ | ✅ |
| Интерактив по фазам | ❌ | ✅ | ✅ | ✅ | ✅ (SSE) |
| Нужен Telegram | ❌ | ✅ | ❌ | ❌ | ❌ |
| Нужен запущенный бот | ❌ | ✅ | ❌ | ❌ | ✅ |
| Пишет в БД | ✅ | ✅ | ✅ | ❌ | ✅ |

---

## Pipeline — фазы

| Фаза | Инструмент | Входные данные | Артефакт |
|------|-----------|---------------|---------|
| 1 — Fetch JD | `cv_fetch_jd` | URL → services/parser | `JD.md` |
| 2 — Analyze | `cv_analyze` | JD.md + PROFILE → Claude | `JD_analysis.md` |
| 3 — Generate CV | `cv_generate` | PROFILE + анализ → Claude | `CV.md` |
| 3.5 — Self-review | _(внутри generate)_ | CV.md → Claude | `CV.md` (revised) |
| — Render PDF | _(внутри generate)_ | CV.md → services/pdf | `CV.pdf` |
| 4 — Cover Letter | `cv_cover` | JD + CV → Claude | `Cover.md` |

---

## Структура хранения артефактов

```
vacancies/
└── {user_id}/
    └── {site}/          # djinni | dou | linkedin | other
        └── {YYYY-MM}/
            └── {slug}/
                ├── JD.md
                ├── JD_analysis.md
                ├── [Name]_CV.md
                ├── [Name]_CV.pdf
                └── [Name]_Cover.md
```

Режим 4 (`/analyze`): `vacancies/{Company — Role}/` (без user_id, без date-sharding)

---

## Известные упрощения (production bottlenecks)

Намеренные trade-off'ы, принятые для скорости разработки. Требуют замены перед реальной нагрузкой.

| Упрощение | Где | Production-путь |
|-----------|-----|----------------|
| `profile_json TEXT` в таблице `users` | `db/schema.sql` | Отдельная таблица `profiles` с историей версий |
| `MULTI_USER_ENABLED=false` (single-user mode) | `core/settings.py` | `=true` убирает фильтр `allowed_chat_id`; при настоящем масштабе — auth middleware |
| Нет concurrent write protection на profile | `db/database.py` | Optimistic locking или очередь записи |
| FSM-состояние onboarding в `users.onboarding_step` | `db/schema.sql` | Redis или выделенная FSM-таблица |

Подробнее — `docs/discovery/core-differentiators.md`.

---

## Связанные документы

- `docs/local-app.md` — детали Режима 4 (diagrams, команды, профиль)
- `docs/delivery/PIVOT-PLAN.md` — план фаз разработки
- `docs/delivery/BACKLOG.md` — статус эпиков · `docs/delivery/CHANGELOG.md` — история фич
- `docs/discovery/core-differentiators.md` — конкурентные преимущества, требующие отдельного дизайна

---

## Project phases

| Phase | Period | Direction | Key deliverable |
|-------|--------|-----------|-----------------|
| 1 — Generic AI agent | pre-2026-05-31 | Generic multi-agent orchestration platform | EPICs 1–12 (see `epics-archive/`); external service deps (`knowledge-mirror-parser`, `callback-cv`, `job-board-monitor`) |
| 2 — Focused vertical service | 2026-05-31 | Generic platform → PM/PO/PM job counselor; monorepo consolidation | ADR-01; EPICs 13–18; `services/` inside; multi-user schema |
| 3 — Deterministic FSM | 2026-06-15 | AI agent orchestrator → Python FSM + subordinate LLM | ADR-02; EPIC-21; 4 cognitive touchpoints; weasyprint PDF |

---

## Design Decisions Log

### ADR-01 — 2026-05-31: Pivot from generic agent orchestrator to focused vertical service

**Status:** Accepted  
**Context:**

The original architecture treated this project as a generic multi-agent orchestration platform — an AI framework that could be adapted to any workflow. The product was positioned as a tool showcase: PydanticAI, prompt caching, extended thinking, multi-agent dispatch.

After building and running the CV pipeline end-to-end for real vacancies, the product identity became unambiguous: the system was doing exactly one thing well — acting as a job counselor for PdM/PO/PM candidates. The "generic platform" framing was misleading to users and wasteful for development — every decision was being made in service of a specific, narrow problem.

**Decision:**

Reposition as a focused vertical service. The tight, opinionated pipeline is a feature, not a limitation. Everything outside this pipeline — generic agents, multi-domain routing, platform abstractions — was removed or never built.

Three structural consequences:

1. **Monorepo consolidation.** Three external repos (`knowledge-mirror-parser`, `callback-cv`, `job-board-monitor`) were being used as dependencies without ownership. Each was audited, stripped of dead code, and migrated into `services/` as first-class components. Nothing user-built lives outside this repo.

2. **Profile moves into the product.** The candidate profile lived in a hand-edited `PROFILE.md` file in an external repo. That's not a product — it's a config file. Profile generation via onboarding interview (PDF → structured profile → DB) became a core feature, not an afterthought.

3. **Multi-user by design from day one.** Single hardcoded `TELEGRAM_CHAT_ID` was the entire user model. Retrofitting multi-user later is expensive. `user_id` was introduced everywhere (DB schema, filesystem paths, LLM context) before any second user existed.

**Alternatives considered:**

| Alternative | Why rejected |
|-------------|-------------|
| Keep generic platform framing | Product identity was unclear; every feature decision became ambiguous |
| Incremental migration (keep external repos) | No ownership = no ability to audit, strip, or change the interface contract |
| Single-user forever | Multi-user is architectural, not just a feature; retrofitting is a rewrite |

**Trade-offs accepted:**

- Tight ICP (PdM/PO/PM) — intentionally narrows the addressable market to increase relevance per user
- Opinionated pipeline — phases are fixed; non-PM use cases require a new `skill_type`, not a new agent
- Monorepo — tighter coupling between services, but full ownership and no external dependency drift

**Outcome:**

All five pipeline phases remain intact and tested. External repo dependencies eliminated. Services architecture established (`services/parser/`, `services/pdf/`, `services/job-monitor/`). Multi-user schema in place. Profile onboarding epic defined.

See `docs/delivery/PIVOT-PLAN.md` for the full migration phase plan.

---

### ADR-02 — 2026-06-15: Deterministic FSM orchestrator replaces agent-driven pipeline

**Status:** Planned (EPIC-21)

**Context:**

After Phase 2 established the focused pipeline and monorepo structure, the remaining waste became visible: the LLM was doing deterministic work (arithmetic, decision tables, rendering), and in local mode a reasoning agent was hand-executing glue steps — one expensive agent turn per mechanical FS/DB/menu operation.

Two concrete signals:
1. VScore composite formula and Fit×VScore recommendation matrix were being computed by the LLM in prose — pure arithmetic and `if/elif`.
2. Step trace analysis (H-002) showed the ratio of agent turns on glue vs. cognitive work was inverted: most turns were FS/DB/menu, not analysis/generation.

**Decision:**

Draw and enforce the boundary. Python FSM owns the skeleton and all I/O. LLM called only for irreducible cognitive phases, returning structured JSON. Three structured calls (`P1+2`, `P3+3.5`, `P4`) + one conditional interactive exchange (`P2.5`), not a scatter of agent turns.

**Control principle:** FSM is primary (owns control flow + I/O). LLM is a subordinate pure function (text → JSON judgment, no FS/DB access, no control flow decisions). *Code runs the model — not the model the code.*

PDF engine also resolved: **weasyprint** (HTML/Jinja2 + CSS) replaces fpdf2 `render_md` (fragile line-by-line markdown parser, no colour emoji).

**Alternatives considered:**

| Alternative | Why rejected |
|-------------|-------------|
| Keep agent-driven glue | Every glue step costs a reasoning turn; arithmetic by LLM is error-prone |
| Playwright for PDF | ~300MB headless-Chrome dependency; heavier in Docker/CI |
| LLM decides branching | Violates control principle — cognitive output influences guards, never executes transitions |

**Outcome (target):**

4 cognitive touchpoints instead of scattered agent steps. Deterministic metrics (VScore composite, recommendation matrix, Top-15 freq, tools scan, repetition check) moved to Python. One skeleton shared by API/headless and local modes.

See [EPIC-21](docs/delivery/Epics/EPIC-21-deterministic-vs-cognitive-pipeline.md) for full task breakdown + UML diagrams.
