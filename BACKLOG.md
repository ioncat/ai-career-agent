# career-agent — Backlog

> Last updated: 2026-07-09
> Epic format: post-pivot epics (13+) live in `docs/delivery/epics/`. This file = priority tracker + status overview.
> Pre-pivot epics (1–12): `docs/delivery/epics-archive/EPIC-01-12-pre-pivot.md`

---

## ✅ Delivered Features

### 2026-07-09
- **EPIC-26 complete** — T1: DB migrations (duplicate_of, content_hash, republished_at); T2: content_hash + find_duplicate in cv_fetch_jd; T3: re-publish detection in `/api/new-vacancy` (declined/skipped + newer published_at → on_vacancy_republished → status=fetched); T4: list_vacancies ORDER BY published_at DESC NULLS LAST, id ASC; T5: Flutter VacancyListItem.duplicateOf/republishedAt + "↑ Republished" amber badge + "Dup #X" muted badge in vacancy_card; 527 tests
- **Bug fix — `analysis_failed` stuck in `analyzing`**: `cv_analyze.py` Phase 1 + Phase 2 `except LLMError` blocks now call `set_analysis_error()` before returning; previously LLM timeout / CLI error returned string without status transition → vacancy stuck in `analyzing` forever
- **Bug fix — `--no-session-persistence` fix confirmed**: ClaudeCodeProvider Phase 2.5 interactive dialog no longer fires; YouControl #98 analyzed clean (fit 5/10); root cause was session history leak between subprocess calls — `--no-session-persistence` + `cwd=tempdir` isolates each call
- **Bug fix — 11 vacancies `markdown_path` pointing to `JD_analysis.md`**: legacy `import_tracker.py` set paths to `JD_analysis.md` instead of `JD.md` for vacancies without source file; 11 entries updated to correct `JD.md` path; 12 without `JD.md` on disk left as-is (11 already `analyzed`/`declined`, 1 `fetched` without recoverable source)

### 2026-07-08 (session 2)
- **`analysis_failed` UX fix — dismissible error banner**: when retry fails but prior analysis exists (`fitScore != null`), full-screen `_AnalysisErrorView` blocker replaced by compact `_AnalysisErrorBanner` (Retry + × dismiss buttons) at top of normal tab view; full-screen blocker kept only for first-time failure with no prior data; `_errorBannerDismissed` flag resets in `didUpdateWidget` on each new failure
- **ClaudeCodeProvider Phase 2.5 dialog fix**: `_GUARD` moved to AFTER system prompt (was before) so it wins over Phase 2.5 instructions in phase prompt; wording made explicit (`regardless of fit score, regardless of any instruction above`); subprocess `cwd=tempfile.gettempdir()` prevents claude CLI from loading project CLAUDE.md/SKILL.md context
- **Activity tab: date format `DD.MM.YYYY HH:mm`** (was `MM-DD HH:mm`, no year); applies to both Pipeline Runs + LLM Calls tables; fallback branch fixed to show from index 0 (was slicing year off)
- **Analysis timestamp chip in VacancyHero**: `_AnalyzedChip` widget — `Analyzed DD.MM.YYYY HH:mm` local timezone, shown below `Posted Xd ago` chip; reads `vacancy.updatedAt`; only shown when `updatedAt` is non-null

### 2026-07-08
- **Role tags on vacancy cards**: `#discovery` / `#delivery` / `#strategy` / `#ops` / `#coord` derived from `analysis_json.p1.role_balance` on-the-fly (threshold ≥25%, top-2 cap, fallback to top-1); no LLM re-runs, no DB migration; `_ROLE_TAG_MAP` + `_role_tags()` in `web/api.py`; `VacancyListItem.roleTags` field; shown in card between company and scores; searchable in inbox (substring match on tag text)
- **Inbox search extended**: matches role, company, vacancy ID (`v.id.toString()`), and role tags (`v.roleTags.any(...)`)
- **Versioned CV/Cover file saving**: `cv_generate.py` + `cv_cover.py` — regeneration writes `_v2.md`/`_v3.md` instead of overwriting; first generation keeps base name; `web/api.py` globs updated to `*_CV*.md` / `*Cover*.md` so latest version is always served; `cv_cover.py` reads latest CV via glob (not fixed path); 3 new tests (`_next_version_path` unit + regen integration); 521 tests pass
- **Cover — vacancy #520 Binotel**: Phase 4 UA cover generated + saved (`Олексій_Бондаренко_Cover.md`)
- **PDF Download + Auto-Refresh CV/Cover tab**: `GET /api/vacancies/{id}/cv-pdf` + `/cover-pdf` — always re-render from latest markdown via pdf-service (no staleness, no version tracking); Flutter `VacancyRepository.getCvPdfBytes()` / `getCoverPdfBytes()` → `Uint8List`; `_downloadPdf()` real implementation — "Preparing PDF..." SnackBar → `FilePicker.platform.saveFile(bytes: ..., fileName: ...)` → error SnackBar on failure; auto-refresh polling 3s when `cv_queued`/`cv_generating`/`cover_generating` → stops on completion; `didUpdateWidget` auto-switch Cover tab on `cover_generated`; `file_picker: ^8.1.7` added
- **Telegram stripped to push-only**: `core/router.py` deleted; `core/telegram.py` rewritten (469→65 lines) — Dispatcher, FSM, onboarding (`/start`, `/update_profile`, `/set_skill`, PDF upload), inline keyboards, `on_message`/`on_callback`, `multi_user_enabled` all removed; `agent.py` main loop now uses `stop_event.wait()` instead of long polling; TelegramBot init simplified to `token + chat_id`; closes last direct-API leak source (Router used `AnthropicProvider` for every incoming Telegram command)
- **Bug fix — API leak: claude_cli billing via ANTHROPIC_API_KEY**: `ClaudeCodeProvider._subprocess_env()` was copying full `os.environ` including `ANTHROPIC_API_KEY` into the `claude` subprocess — CLI used the key for direct API billing instead of its OAuth subscription, causing unauthorized charges (38K–41K input tokens per analysis call observed in Anthropic dashboard). Fix: `env.pop("ANTHROPIC_API_KEY", None)` before passing env to subprocess. Second leak: `web/api._get_available_models()` was calling `_fetch_anthropic_models()` (HTTP GET `/v1/models` with API key) for `claude_cli` provider — now restricted to `claude_api` only; CLI uses `_FALLBACK_MODELS` entry. See `docs/discovery/retrospective.md`.

### 2026-07-07 (pipeline runs)
- **Vacancy #543 — Kiss My Apps (AI Learning Platform)**: Fit 6/10 · VScore 8.8 · take a chance — premium opportunity; CV EN + UA generated; Application_answers.md (Djinni); PROFILE.md updated (feature adoption rate evidence + 2-component AI paragraph EN+UA)
- **Vacancy #545 — RedCore (PM Finance)**: Fit 7/10 · VScore 7.9 · apply — strong match; CV EN + Cover generated; BOS-from-scratch positioning; ERP-like framing
- **CV markdown bug fix**: blank line required before bullet lists after `**Key results:**` — Python markdown parser collapses to inline without it

### 2026-07-07
- **AnalysisWorker — DB recovery on startup**: `_recover_queued()` runs once at AnalysisWorker start; picks up `analysis_queued` vacancies left from crash or restart and re-enqueues immediately (no polling delay)
- **launcher.py — removed standalone Web API**: `Web API :8080` entry removed from SERVICES; agent.py now owns the embedded FastAPI server with workers in the same process → `app.state.analysis_worker` always set → Flutter Analyze button hits real worker directly
- **db.reset_stuck_statuses() — isolated from init_db()**: DB crash-recovery (`analyzing → analysis_queued`, `cv_generating → cv_queued`) moved out of `init_db()` into separate `reset_stuck_statuses()`; called explicitly in agent.py before workers start; web API lifespan `init_db()` no longer clobbers active work on startup

### 2026-07-06
- **Flutter — ProcessingWrapper**: cross-cutting `ProcessingWrapper` widget (snake border animation via `CustomPainter` + `PathMetrics` + phase overlay with spinner + label) replaces 4 per-status badge classes in `VacancyCard`; `kActiveStatuses` map in `active_status.dart` is single source of truth — adding a status there auto-enables animation everywhere
- **Launcher — correct startup order + Monitor ready signal**: Bot starts before Monitor (eliminates webhook race on startup); Monitor ready signal fixed to `"Interval:"` (appears on every run, not just first launch)
- **Architecture — AnalysisWorker + CVWorker**: immediate asyncio.Queue dispatch replaces 60s polling; shared `LLMSemaphore` (env `LLM_CONCURRENCY`); `_fresh_llm()` reads user_settings from DB per run; RSSWatcher stripped to RSS-only; workers wired via `app.state` into FastAPI
- **Claude CLI PATH + stdin fix**: `_subprocess_env()` + `shutil.which()` resolves full exe path; prompt passed via stdin (`-p -`) instead of command-line arg — bypasses Windows 32767-char `CreateProcess` limit (`WinError 206`); removes `_find_claude()` which returned `claude.EXE` causing `FileNotFoundError`
- **cv_generate — LLMError propagation**: Phase 3 + 3.5 now `raise` on `LLMError` instead of returning error string; CVWorker resets status to `analyzed` on exception
- **Flutter Detail — Tabs UX (T1–T4)**: `VacancyDetailScreen` → `ConsumerStatefulWidget` with `TabController(length: 4)`; tabs: Analysis | CV | Cover | Activity; `_CvTab` + `_CoverTab` — watch `vacancyCvProvider`, show spinner during `cv_queued`/`cv_generating`, content or empty state otherwise; `didUpdateWidget` auto-switch on `cv_generating → cv_generated` + `ref.invalidate(vacancyCvProvider)`; removed `VacancyCvDialog` + "View CV" button; `vacancy_cv_screen.dart` deleted; Web API :8080 added to `launcher.py` SERVICES list
- **Flutter Detail — context-sensitive action bar**: `_ActionBar` CTA changes per tab via `AnimatedBuilder(animation: tabController)`; Analysis: Decline + Re-analyze; CV: `_SplitButton(Generate/Regenerate CV ▾ → Download PDF)`; Cover: `_SplitButton(Generate/Regenerate Cover ▾ → Download PDF)`; Activity: empty; `_RecommendationCard` (renamed from `_VerdictCard`)
- **Flutter Detail — split button fix**: `tapTargetSize: shrinkWrap` + explicit `minimumSize`/`maximumSize: Size(34, 36)` on both halves; `Container(1px, white@25%)` divider instead of `SizedBox` gap — eliminates M3 invisible tap-padding misalignment
- **Cover generation end-to-end**: `CoverWorker` (Phase 4 background queue, mirrors `CVWorker`); `POST /api/vacancies/{id}/generate-cover`; `generateCover()` in `VacancyRepository`; Cover tab CTA wired; status `cover_generating → cover_generated`; error rollback to `cv_generated`
- **cv_generate — CV split Strategy 4**: H1 heading anchor `^# [A-Z]` as final fallback in `_split_review_and_cv()`; Phase 3.5 prompts: FULL OUTPUT ORDER block + mandatory `---CV---` separator with parser warning; review tables (Word Frequency, Tools & Tech) stay in `JD_analysis.md` only, never in CV.md
- **Flutter — Activity Log tab**: second tab in detail screen showing per-call LLM journal (phase · provider · model · effort · elapsed · tokens in→out · cost); DB migration adds `provider` + `thinking_effort` to `llm_usage`; `GET /api/vacancies/{id}/activity` endpoint; `_budget_to_effort()` helper maps budget_tokens → effort label; Pipeline Runs section above LLM Calls
- **Flutter — Activity tab table layout**: replaced monospace string blocks with `Table` widget (aligned columns, header separator, right-aligned numeric cols); UTC→local timezone conversion via `DateTime.parse(iso).toLocal()`
- **CLI provider — format fixes**: `_normalize_cli_output()` strips CLI-specific artifacts (progress wrapper lines, decimal scores `6.0/10 → 6/10`) before returning to shared parser; `_GUARD` preamble prevents CLI agent from attempting file writes when prompt says "goes to JD_analysis.md"; debug log `logs/cli_debug.log` streams stdout line-by-line in real time
- **CLI provider — stderr deadlock fix**: switched from `proc.stderr.read()` (blocks until EOF) to streaming `async for` on both stdout and stderr via `asyncio.gather`; eliminates pipe-buffer deadlock on large stderr output
- **RSS watcher — `_fresh_llm()`**: reads `user_settings` from DB before each analysis run, builds fresh `ClaudeCodeProvider` / `ClaudeProvider` / `OllamaProvider` with current model + thinking_effort; profile MD re-read from disk; no backend restart required after Settings change; `AgentDeps` type union extended with `ClaudeCodeProvider`
- **Phase 2 parse-fail surfacing**: when LLM call succeeds but output doesn't match parser (`p2 is None`) → writes `analysis_error` to DB, sets `status='analysis_failed'`, returns user-visible message with 300-char raw snippet; previously silent `log.warning` only
- **Flutter — unread badge**: "New" badge shown only for vacancies not yet opened by user; tracked via `readVacanciesProvider` (SharedPreferences `Set<int>`); marked read on card tap
- **Flutter — auto-advance on skip**: after Skip in inbox, automatically selects next unread vacancy instead of showing empty screen; fires only on successful decline
- **Flutter — starred**: star toggle (⭐) in vacancy card Row 1 (right of date) + detail screen action bar; optimistic state; `PATCH /api/vacancies/{id}/starred`
- **Flutter — applied**: "Applied?" / "Applied ✓" toggle button in detail screen action bar only; optimistic state; `PATCH /api/vacancies/{id}/applied`
- **Flutter — Applied folder fix**: `_folderMatch` now passes full `VacancyListItem` instead of just `status`; Applied folder filters by `v.applied` boolean (was `status == 'applied'` which never matched); inbox status list extended with `cover_generating` / `cover_generated`

### 2026-07-05
- **Flutter Settings — dynamic model list**: available models fetched from Anthropic API / Ollama at runtime; 24h TTL cache in `system_kv` table; fallback to hardcoded list on network error
- **Flutter Settings — thinking effort**: `SegmentedButton` (Off/Low/Med/High/xHigh/Max); hidden for Ollama; `PATCH /api/config`; stored in `user_settings` DB table
- **Flutter Detail — hover tooltips**: `_TooltipTitle` on all major sections (Fit, Attraction, Quick Overview, Fit Dimensions, Attraction Breakdown, Role Balance)
- **Flutter Detail — JD always visible**: Job Description section always shown at bottom of detail view; pushed down by analysis, never hidden
- **Flutter Detail — score dot rows**: Fit + Attraction shown as colored dot rows (≥70% green / 40–69% amber / <40% red) in `_VacancyHero`
- **Flutter Detail — sections collapsed by default**: Fit Dimensions, Attraction Breakdown, Role Balance collapsed; Job Description expanded

### 2026-07-03
- **Flutter Inbox — Analyze / Skip / Restore**: action buttons in JD view; Skip → `declined`; Restore from archive → inbox
- **Flutter Inbox — queue animation**: "In queue" badge with pulse animation; "Analyzing..." spinner badge
- **Flutter Inbox — analysis error surfacing**: `analysis_failed` state shown with error message + Retry button
- **Flutter Inbox — markdown JD render**: `flutter_markdown` in JD view and JD section of detail screen

### 2026-07-01
- **Flutter Detail — CV / Cover preview**: `VacancyCvDialog` — side-by-side CV.md + Cover.md with markdown render; Generate CV button in action bar
- **Flutter Detail — full analysis view**: `_VacancyHero`, `_QuickOverviewCard`, `_FitDimsTable`, `_VacScoreTable`, `_RoleBalanceBar`, `_CollapsibleSection`

### 2026-06-30
- **Flutter Inbox — vacancy list with polling**: 30s polling, cache in SharedPreferences, status-based folder routing (inbox / in_progress / applied / archive)
- **Flutter Inbox — filter panel**: status chips + date range picker
- **Flutter Inbox — search**: role + company full-text filter

### 2026-06-20
- **Flutter MVP scaffold**: app shell, navigation rail, VacancyCard, VacancyInboxScreen master-detail layout
- **RSS watcher → Web Push**: after Phase 1+2 analysis completes, push notification sent to Flutter via VAPID

---

## 🟡 P2 — `analyzed_at` — точный timestamp успешного анализа

**Проблема:** `updated_at` обновляется при каждом изменении статуса, включая `analysis_failed`. Чип "Analyzed DD.MM.YYYY HH:mm" показывает время последнего обновления — не последнего успешного анализа. Вводит в заблуждение при retry-failed сценарии.

**Решение:** отдельная колонка `analyzed_at` (DATETIME, nullable), обновляется только при успешном завершении Phase 2 (переход в `analyzed`).

**Scope:**
- `db/schema.sql`: добавить `analyzed_at DATETIME`
- `db/database.py`: миграция `ALTER TABLE vacancies ADD COLUMN analyzed_at DATETIME`; обновлять `analyzed_at = datetime('now')` при `status = 'analyzed'`
- `tools/cv_analyze.py`: при сохранении analysis_json → вызов update с `analyzed_at`
- `web/api.py`: включить `analyzed_at` в vacancy list response
- `flutter/lib/models/vacancy.dart`: поле `analyzedAt`
- `flutter/lib/screens/vacancy_detail_screen.dart`: `_AnalyzedChip` читает `analyzedAt` вместо `updatedAt`

---

## ✅ EPIC-26 — Vacancy Deduplication & Re-publish Detection (DONE 2026-07-09)

**Goal:** Eliminate noise from cross-source duplicates (same JD on Djinni + DOU) and surface re-published vacancies that were previously declined or buried.

**Problem 1 — Cross-source duplicates:**
Same vacancy appears on Djinni and DOU with identical or near-identical text. Currently creates two separate DB entries with no link between them. User wastes time analyzing the same role twice.

**Problem 2 — Re-published/bumped vacancies:**
A vacancy already in DB (analyzed, declined, or buried) gets re-published or bumped in RSS feed. Current behaviour: URL already exists → silently ignored. User never knows the vacancy is active again. A declined vacancy that was re-posted remains declined and invisible.

---

### Design

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
- Current: `ORDER BY id DESC` (insertion order)
- New: `ORDER BY published_at DESC, id ASC`
- `published_at` already stored by RSS watcher; vacancies added manually = `published_at = created_at`

---

### DB changes (migrations)

| Column | Table | Type | Purpose |
|---|---|---|---|
| `duplicate_of` | `vacancies` | `INTEGER REFERENCES vacancies(id)` | FK to original if this is a duplicate |
| `content_hash` | `vacancies` | `TEXT` | sha256 of normalized JD text |
| `republished_at` | `vacancies` | `DATETIME` | Set when re-published after decline |

---

### Task list

**T1 — DB migrations**
- `db/schema.sql`: add 3 columns
- `db/database.py`: migration `ALTER TABLE` for each; helper `find_duplicate(user_id, content_hash, norm_title, company) → int | None`

**T2 — Duplicate detection at fetch**
- `tools/cv_fetch_jd.py`: compute `content_hash` after JD text parsed; call `find_duplicate`; set `duplicate_of` if match found; log duplicate link
- `core/rss_watcher.py`: same check at RSS insert time

**T3 — Re-publish detection in RSS watcher**
- `core/rss_watcher.py`: on URL already-exists case, compare `published_at`; update fields + transition status per design above

**T4 — Inbox sort + API response**
- `web/api.py`: change vacancy list `ORDER BY` to `published_at DESC, id ASC`; include `duplicate_of` and `republished_at` in list + detail responses

**T5 — Flutter model + UI badges**
- `flutter/lib/models/vacancy.dart`: add `duplicateOf`, `republishedAt` fields
- `flutter/lib/widgets/vacancy_card.dart`: "Дубль #X" badge (secondary chip, subtle colour); "↑ Повторно" badge (amber)
- No separate inbox section — all in same inbox, sorted by date

---

### Out of scope
- Merging duplicate vacancies (would lose analysis data from both)
- LLM-based semantic similarity (overkill for this problem)
- Dedup across users (separate user_id = separate namespace)

---

## 🔵 P0 — [EPIC-22](docs/delivery/Epics/EPIC-22-flutter-platform.md) — Flutter Platform (Pivot 2)

**Goal:** Flutter Web = sole UI. Telegram removed. Pipeline emits JSON. RSS → auto Phase 1+2 → Web Push → Flutter.

**Status:** Phase C complete (2026-07-05). Flutter MVP done: VacancyCard + detail redesign, VerdictCard, analysis error surfacing, settings screen, EPIC-23 provider display, EPIC-24 T5/T6/T8 evidence injection. Next: Phase D (Telegram removal, FSM orchestrator) or EPIC-24 T7 after real pipeline test.

**Full delivery plan (all epics, strict order):** `docs/delivery/INBOX-FIRST-FLOW.md` → section "Delivery Plan"

**Critical path:** Phase A (auto-pipeline) → Phase B (JSON contracts + EPIC-21 Tasks 2–3) → Phase C (Flutter MVP) → Phase D (polish + Telegram removal).

---

## ✅ P1 — [EPIC-23](docs/delivery/Epics/EPIC-23-claudecode-provider.md) — Claude Code CLI Provider (done 2026-07-05)

**Goal:** test the full pipeline via Flutter without consuming API credits. `LLM_PROVIDER=claude_cli` → calls go through `claude -p` subprocess → uses Claude Code subscription, cost $0.

**Status:** ✅ All 5 tasks done. `ClaudeCodeProvider` implemented + tested. Flutter Settings shows active provider.

**Activation:** `LLM_PROVIDER=claude_cli` in `.env`.

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
- `ARCHITECTURE.md` — update pipeline phases table, mode comparison table (Mode 4 description changes with Task 6)
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

## 🟡 P2 — Worker-Critic Pipeline (added 2026-07-06)

**Idea:** Two-agent loop per phase. Worker produces output → Critic reviews it as a demanding client → Worker revises → repeat until Critic approves or max iterations reached.

**Goal:** Measurably improve content quality of each pipeline phase without manual intervention. Phase 3.5 (CV self-review) is an early version of this pattern — generalize it.

**Scope:**
- Phase 1+2 (JD analysis + fit) — Critic checks: are barriers honest? is fit score calibrated? any hallucinations?
- Phase 3 (CV draft) — Critic checks: tailoring to JD, no contamination from other vacancies, no generic filler
- Phase 4 (cover letter) — Critic checks: positioning, no evidence leaks, tone matches role seniority
- Phase 3.5 already exists as a single self-review pass — Worker-Critic replaces/extends it with an adversarial loop

**Design:**
```
Worker prompt → Worker output
                      ↓
              Critic prompt (role: "demanding hiring manager / senior recruiter")
              + Worker output + original JD + PROFILE.md
                      ↓
              Critic verdict: APPROVED | NEEDS_REVISION + critique notes
                      ↓ (if NEEDS_REVISION, max 2 iterations)
              Worker revision prompt + critique notes → revised output
                      ↓
              Critic re-review → APPROVED
```

**Key decisions before implementation:**
1. Same model for Worker + Critic, or different models? (Critic could be cheaper/faster)
2. Max iterations: 1 or 2 revision rounds? (each round = 2 LLM calls + cost)
3. Critic persona prompt: generic "demanding client" or role-specific (PM hiring manager vs. tech lead)?
4. Storage: save Critic notes to `analysis_json.critic_notes[]` per phase for Activity log visibility
5. Feature-flag: `CRITIC_ENABLED=true/false` in `.env` — off by default until validated

**Experiment plan:** run same vacancy through pipeline with Critic off vs. on → compare output quality manually → decide if cost is justified.

**Estimated cost impact:** +50–100% per phase (one extra Critic call + possible revision call). Worth it only if quality delta is significant.

---

## 🟡 P2 — Role Tags on Vacancy Cards (added 2026-07-08)

**Goal:** Show 1–2 role-type hashtags on each vacancy card in Flutter inbox — `#discovery`, `#delivery`, `#ops`, etc. — derived from existing `analysis_json.p1.role_balance` without re-running any LLM.

**Use cases:**
- Visual signal at a glance: Discovery-heavy vs. Delivery-heavy role
- Quick reuse: find existing vacancy with similar role type to reuse CV instead of regenerating
- Future: filter inbox by role tag

### Classification logic

Source: `analysis_json.p1.role_balance` — dict with keys: `strategy`, `discovery`, `execution`, `coordination`, `ops` (values sum to 100%).

Mapping to tags:
| key | tag |
|---|---|
| `discovery` | `#discovery` |
| `strategy` | `#strategy` |
| `execution` | `#delivery` |
| `ops` | `#ops` |
| `coordination` | `#coord` |

**Rule:** Take all dimensions ≥ 25%. If none reach 25% — take top-1. Cap output at 2 tags, ordered by value descending.

**Rationale for 25% threshold:** most roles have 1–2 dominant dimensions above 25%; below that, the dimension is background noise, not a defining characteristic. The cap of 2 tags keeps cards readable.

**Examples:**
```
GlobalLogic (#451): ops=45, execution=25 → #ops #delivery
Binotel (#520):     discovery=30, strategy=25 → #discovery #strategy
JustMarkets:        execution=35, strategy=20 → #delivery (only one ≥25%)
```

**Vacancies without `p1`** (not yet analyzed): no tags shown — field returns `[]`.

### Implementation

**Backend (`web/api.py`):**
- `_role_tags(role_balance: dict) -> list[str]` — pure function, ~10 lines
- Add `role_tags: list[str]` to `GET /api/vacancies` response per vacancy

**Flutter:**
- `VacancyListItem` — add `List<String> roleTags`
- `VacancyCard` — show tags row below role/company in muted small text
- Search (`vacancy_inbox_screen.dart`) — extend to also match `#tag` queries against `roleTags`

**No DB migration needed** — computed on-the-fly from existing `analysis_json`.

---

## 🟡 P2 — PDF Download + Auto-Refresh CV Tab (added 2026-07-08)

### PDF Download ("Save As")

**Current state:** `_downloadPdf()` in `vacancy_detail_screen.dart` is a stub — shows SnackBar "coming soon", no file transfer.

**Correct flow:**
```
User clicks "Download PDF"
    → Flutter: GET /api/vacancies/{id}/cv-pdf
    → Backend: reads Oleksii_Bondarenko_CV.pdf from disk → FileResponse(bytes, application/pdf)
    → Flutter: receives bytes → FilePicker.platform.saveFile(bytes, fileName)
    → OS "Save As" dialog → user picks folder
```
Same for Cover PDF via `GET /api/vacancies/{id}/cover-pdf`.

**Open design question — PDF staleness:**
If the user regenerates the CV (new markdown) or edits it manually, the existing `.pdf` on disk is stale. Three options:
1. **Auto-detect**: compare `mtime(CV.md)` vs `mtime(CV.pdf)` → if md is newer, regenerate PDF on-the-fly before serving (transparent to user, adds latency)
2. **Always regenerate on Download**: simplest logic, always fresh, ~1–2s delay — acceptable for "Save As" flow
3. **Separate "Regenerate PDF" button**: explicit user action; split button becomes `Generate CV ▾ → Download PDF → Regenerate PDF`

**Recommended: option 2** — always call pdf-service on Download request. PDF-service is fast (~1s), result is guaranteed fresh. No version-tracking complexity. Backend endpoint regenerates + serves in one request.

**Scope:**
- [ ] `web/api.py` — `GET /api/vacancies/{id}/cv-pdf`: find CV.md in vacancy folder → POST to pdf-service → stream bytes as FileResponse
- [ ] `web/api.py` — `GET /api/vacancies/{id}/cover-pdf`: same for Cover.md
- [ ] Flutter `vacancy_repository.dart` — `getCvPdfBytes(id)` / `getCoverPdfBytes(id)` → `Uint8List`
- [ ] Flutter `vacancy_detail_screen.dart` — `_downloadPdf()`: call repo → `FilePicker.platform.saveFile()`
- [ ] Add `file_picker` to `pubspec.yaml`

### Auto-Refresh CV Tab

**Problem:** after "Generate CV" is triggered, the CV tab stays blank until user manually hits Refresh. Status transitions `cv_generating → cv_generated` happen server-side but Flutter doesn't know.

**Solution:** same polling pattern as analysis — when vacancy status is `cv_generating`, poll every 5s; on `cv_generated` → `ref.invalidate(vacancyCvProvider)` + auto-switch to CV tab.

**Scope:**
- [ ] Flutter `vacancy_detail_screen.dart` — `_StatusPoller` extended (or new `_CvStatusPoller`): watches for `cv_generating` → `cv_generated` transition, invalidates providers, switches tab

---

## 🟡 P2 — CV/Cover Language Selection in Flutter (added 2026-07-08)

**Problem:** `CVWorker` calls `cv_generate(ctx, vacancy_id)` without `language` param → always generates in English. User has no control from Flutter.

**Design:** Auto from JD + explicit override via split-button menu.
- Main "Generate CV" button → `language="auto"` → backend detects from JD (Cyrillic → Ukrainian, else English)
- `▾` menu adds: **Generate in English** / **Generate in Ukrainian**
- Same applies to Cover letter (matches CV language by default)

**Stack changes:**

| # | File | Change |
|---|------|--------|
| 1 | `core/cv_worker.py` | `enqueue(vacancy_id, language="auto")` — pass to `cv_generate()` |
| 2 | `tools/cv_generate.py` | `language="auto"` → detect from JD text (any Cyrillic → Ukrainian) |
| 3 | `web/api.py` | `POST /generate-cv` accept JSON `{"language": "en"\|"uk"\|"auto"}` |
| 4 | `flutter/.../vacancy_repository.dart` | `generateCv(id, {String language = 'auto'})` |
| 5 | `flutter/.../vacancy_detail_screen.dart` | Split-button menu: Generate in English / Generate in Ukrainian |

Same pattern for `generate-cover` + `CoverWorker`.

**Scope:** ~5 files, all connected. No DB changes needed.

---

## 🟡 P2 — Annotated CV Revision (added 2026-07-07)

**Idea:** User selects a block in the CV or Cover markdown preview → adds an annotation comment → submits → AI produces a revised version with that block rewritten to match the note.

**Goal:** Let the user give targeted feedback on generated documents ("make this bullet more concrete", "this sounds too salesy", "add the HostiServer migration here") without re-running the full Phase 3 pipeline.

**Flutter UX:**
- CV tab + Cover tab: long-press or tap-and-hold on a paragraph/section → annotation panel slides up
- User types note in annotation panel → "Request revision" button → sends `{section_text, user_note}` to backend
- Backend responds with revised section text → replaces block in viewer; user can Accept or Undo
- Multiple annotations supported in one round (GitHub code review style)

**Backend:**
- New endpoint: `POST /api/vacancies/{id}/cv-revision` — accepts `{annotations: [{section, note}]}`, returns `{revised_cv_md}`
- Revision prompt: Phase 3.5-style self-review but driven by `user_annotations` instead of word-frequency heuristics
- Saves revised markdown back to DB (same fields as Phase 3 output)
- Activity log entry: `phase=cv_revision`, `model`, `tokens`, `cost`

**Key decisions before implementation:**
1. Section granularity: paragraph-level or heading-level? (paragraph = more precise, harder to anchor)
2. Replace full CV or inject diffs? (full replacement = simpler, diffs = preserve user review position)
3. Revision model: same as Phase 3 or cheaper model? (notes are short; cheaper model may suffice)
4. Max annotations per round: 1 or many? (many = one LLM call, all context at once)

---

## 🟡 P1 — Phase 2.5 Objection Handling (added 2026-06-05)

New pipeline step formalized in `skill/SKILL.md` → "Phase 2.5 — Objection Handling": when Key Barriers ≠ none, resolve weaknesses interactively BEFORE CV draft; resolved evidence appended to PROFILE.md + JD_analysis.md.
**Follow-up:** dedicated `prompts/[skill_type]/phase2_5_objections.md` prompt file (currently spec lives in SKILL.md). Optional DB `analysis_json.p2_5`.

---

## 🟡 P1 — [EPIC-24](docs/delivery/Epics/EPIC-24-progressive-profile.md): Progressive Profile — Structured DB Profile + Onboarding (updated 2026-07-05)

**Central pipeline element.** PROFILE.md = pre-filtered CV. Phase 3 cannot find signals that are absent from context.

**Solution — two profile layers:**

```
users.progressive_profile (SQLite) ← DB profile: rich structured roles, all experience details
                                     Phase 3 reads required sections → rich context
                                     Flutter reads via /api/users/{id}/progressive_profile

PROFILE.md                         ← only: Settings, Name variants, Contacts,
                                     Archetype, Vacancy Preferences, Honest Gaps
                                     Experience moved to DB profile
```

**`progressive_profile` schema (Tasks 1–4 ✅ implemented):**
```json
{
  "meta": { "schema_version": 1, "last_updated": "2026-07-02" },
  "roles": [
    {
      "id": "hostserver_po",
      "company": "HostiServer.com",
      "title": "Product Owner — Platform & Operational Systems",
      "dates": "Jan 2018 – Oct 2021",
      "narrative": "Full role narrative — everything done, context, case studies...",
      "key_results": ["Improved NPS from +19 to +48", "Reduced billing errors by ~95%"],
      "framing": [{"label": "Founder Proxy", "emphasis": "...", "de_emphasis": "..."}],
      "caveats": ["Support team not on LinkedIn — disclose selectively"],
      "tags": ["discovery", "billing", "automation", "funnel", "enterprise"]
    }
  ]
}
```

**Profile switch** — in `/analyze` Step 0: `[4] Profile: Markdown → DB`.
Variable `PROFILE_SOURCE = md|db`. DB profile: read via `SELECT progressive_profile FROM users WHERE id=[id]`.

**Status:**
- Tasks 1–4 + A: ✅ Done 2026-07-02. 4 roles seeded. Toggle `[4]` in `/analyze` Step 0.
- Task 5: ✅ Done 2026-07-05. `scripts/profile_merge.py` + `prompts/pm/phase2_5_writeback.md` + SKILL.md call.
- Task 6: ✅ Done 2026-07-05. `progressive_profile` roles[] injected into Phase 3 user message as "Candidate Evidence (DB Profile)".
- Task 7: 🟡 Pending — waiting for real pipeline test with DB evidence before trimming PROFILE.md.
- Task 8: ✅ Done 2026-07-05. `GET /api/users/{id}/progressive_profile` + 3 tests.

**Next steps:**
- **Task 7:** Trim PROFILE.md — remove Experience + Additional Evidence (after real pipeline test T6)
- **Task 9:** Onboarding interview flow (LLM-driven, EPIC-17 Phase 2)

**Design doc:** `docs/discovery/progressive-profile.md` (gitignored) — schema, fields, rationale.

---

## 🟠 P1 — Архитектура: мгновенный запуск задач вместо polling (added 2026-07-06)

**Проблема:** Анализ и генерация CV запускаются через polling loop (RSSWatcher, 60s интервал). Пользователь нажимает кнопку — ждёт до 60 сек до начала обработки. Неприемлемо.

**Принцип:** Команда пользователя должна выполняться немедленно. Поллер не должен управлять пользовательскими действиями.

**Правильная архитектура:**
- `RSSWatcher` — только RSS: следит за новыми вакансиями из внешних источников. Больше ничего.
- Анализ / генерация CV — отдельный `TaskRunner` с `asyncio.Queue`. API-эндпоинт кладёт задачу в очередь → воркер немедленно подхватывает и выполняет.

**Дизайн TaskRunner:**
```python
class TaskRunner:
    def __init__(self): self._queue = asyncio.Queue()
    async def enqueue(self, task): await self._queue.put(task)
    async def _run(self):
        while True:
            task = await self._queue.get()  # ждёт мгновенно, без polling
            await task()
```

**Scope:**
- [ ] Создать `core/task_runner.py` — `TaskRunner` с `asyncio.Queue`
- [ ] `web/api.py` — `/analyze` и `/generate-cv` кладут задачу в `TaskRunner.enqueue()`, не меняют только статус
- [ ] `core/rss_watcher.py` — убрать `_poll_analyze_queue()` и `_poll_cv_queue()`, оставить только RSS fetch
- [ ] `agent.py` — инициализировать `TaskRunner` рядом с `RSSWatcher`
- [ ] Тесты

---

## 🟡 P1 — Flutter UX: Card Processing Animation (added 2026-07-06)

**Идея:** Визуальная обратная связь когда над вакансией ведётся работа — пользователь должен чётко понимать что происходит без заглядывания в логи.

**Дизайн:**
- **Border animation (змейка):** по периметру карточки бежит подсвеченная линия (CSS border-gradient animation или Flutter custom painter) пока статус = `analyzing` / `cv_generating`
- **Phase overlay:** поверх карточки полупрозрачный текст с названием текущей фазы — не номер, а человеческое описание:
  - `analyzing` → "Analyzing job description..."
  - `cv_generating` → "Generating CV..."
  - `analysis_queued` → "In queue..."
- Оверлей не блокирует клик по карточке — просто декоративный

**Scope:**
- [ ] Flutter: кастомный `AnimatedBorder` painter на карточке для active-статусов
- [ ] Flutter: `Stack` поверх карточки с `PhaseOverlay` виджетом
- [ ] Тексты фаз — отдельный маппинг `status → human label`

---

## 🟡 P1 — Flutter UX: First Testing Round Observations (2026-07-05)

> Source: manual testing session. None implemented yet — backlog only.

### UI Language
- **All text must be English** — currently mixed Russian/Ukrainian (e.g. "В очереди на анализ", "Після завершення аналізу"). Full UI language audit + sweep needed.

### Vacancy List & Cards
- **Return to inbox from archive** — user must be able to move any archived vacancy back to inbox. Currently no such action exists.
- **"In queue" card state** — text is grey, invisible, zero animation. Needs pulse/shimmer animation + non-grey color (e.g. amber). Easy visual win, makes queue state obvious.
- **Queue journal / log panel** — when a vacancy enters the analysis queue, a visible log panel should appear showing all queued vacancies and their status. Useful especially for batch. Consider async parallel processing of queued items.

### JD Text Display
- **Markdown not rendered** — JD text shown for fetched vacancies, but raw markdown (asterisks, etc.) not parsed. Need `flutter_markdown` or equivalent widget.
- **JD view needs UX design** — text is available but UI layout for displaying it (collapsible? separate screen? tab?) not decided. Needs design pass.

### Analysis Flow & Error Handling
- **No visibility into analysis progress** — user cannot tell if backend is actually analyzing or hung. Need:
  - Pre-flight health check before sending analyze request (confirm backend alive)
  - Show some in-progress indicator (timer, phase label, or heartbeat)
  - Surface backend errors to user — e.g. token exhaustion, LLM timeout — must not silently fail
- **Comment:** "is the backend actually analyzing?" — this UX gap is a known complaint. Defer to dedicated issue but track here.

### Settings Screen
- **Model shown as Haiku** — if user wants a different model, no way to change from Flutter. At minimum: show current model from `/api/config`, note that model is set via `.env / LLM_MODEL`. Future: dropdown in settings.
- **Missing settings** — thinking level, max_tokens, provider not configurable from UI. Deeper settings = env-level for now, Flutter = read-only display. Design to revisit.

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
- `skill/SKILL.md` — Batch Mode: silent dedup, `♻️ already processed` in table
- `.claude/commands/analyze.md` — step 3 dedup note added before inbox menu

---

## P1 — Testing & Operations

### 🟢 Tech Debt — Переименовать RSSWatcher → BackgroundWorker (added 2026-07-06)

**Why:** `RSSWatcher` исторически начинался как RSS-поллер, но сейчас это общий планировщик фоновых задач: fetch JD + analysis queue + CV generation queue. Название вводит в заблуждение — новый разработчик будет искать CV-генерацию не там. Рефактор чисто механический (rename class + file).

**Scope:**
- [ ] `core/rss_watcher.py` → `core/background_worker.py`, class `RSSWatcher` → `BackgroundWorker`
- [ ] `agent.py` — обновить импорт и инстанциирование
- [ ] `tests/test_rss_watcher.py` → `tests/test_background_worker.py`
- [ ] CLAUDE.md — обновить структуру проекта

---

### 🔴 Job Monitor — Error Alerting (added 2026-07-06)

**Why:** Monitor is first stage. Silent failure kills entire pipeline. No current alerting — errors only in logs.

**Design:**
1. **Per-feed failure counter** — `seen_jobs.json` → `_feed_health[feed_name]` = `{consecutive_failures, last_success, last_error}`
2. **Telegram alert threshold** — `consecutive_failures >= 3` → POST `/api/alert` or direct Telegram message
3. **Recovery alert** — first success after failure streak → "Feed recovered" notification
4. **`health_check.py`** — reads `_feed_health` from state file; flags feeds with `consecutive_failures >= 3` OR `last_success` older than 2h

**Scope:**
- [ ] `services/job-monitor/monitor.py` — failure counter per feed, alert on threshold, reset on success
- [ ] `services/job-monitor/monitor.py` — `_feed_health` section written to `seen_jobs.json` after each poll cycle
- [ ] `scripts/health_check.py` — `--monitor` flag: read state file, check feed health, exit 1 on stale/failed feeds

**Alert channel:** Telegram (already used by health_check.py). Direct bot API call from monitor (no career-agent dependency).

---

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
💰 Cost estimate — [Vacancy title]
Phase 1 (analysis):  ~$0.04
Phase 2 (fit):       ~$0.06
Phase 3 (CV draft):  ~$0.05
Phase 3.5 (review):  ~$0.07
Phase 4 (cover):     ~$0.05
──────────────────────────
Total:               ~$0.27

Run full pipeline? [Yes] [Analysis only] [Cancel]
```

- [ ] `tools/cv_estimate.py` — token estimate per phase + cost calc
- [ ] Fallback to baseline averages from `docs/discovery/Tokenomics.md` if no DB history
- [ ] Telegram inline keyboard: [Yes] [Analysis only] [Cancel]

---

## ~~P1 — Deterministic pipeline~~ → folded into [EPIC-21](docs/delivery/Epics/EPIC-21-deterministic-vs-cognitive-pipeline.md)

Merged 2026-06-15. The "agent generates content, code applies fixed template" principle and its checklist (strict JD_analysis.md / CV templates, inbox-flow extraction, SKILL.md step review) are now EPIC-21 Tasks 1–4 + 6.

---

## ~~P1 — PDF template system~~ → = [EPIC-21](docs/delivery/Epics/EPIC-21-deterministic-vs-cognitive-pipeline.md) Task 1

Merged 2026-06-15. Engine decision resolved: **weasyprint** (HTML/Jinja2 + CSS → PDF). playwright rejected (~300MB headless-Chrome dependency, heavier in Docker/CI). Drops fpdf2 (no colour emoji, manual spacing). Full task spec in EPIC-21.

---

## 🟡 Docker deploy on VM — next session

`docker-compose.yml` ready (5 services). WeasyPrint requires GTK — Linux container only.

**Plan:**
1. On VM: `git pull && docker compose up --build`
2. Ports bind to `0.0.0.0` — accessible via VM IP
3. From Windows: `http://VM_IP:8080` (tracker), bot via Telegram

**launcher.py** — local startup without Docker (all 5 services in one window, sequential start, Ctrl+C kills all). PDF service on Windows without GTK not functional — Docker only.

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
- **Why:** `cv_analyze.py` logged token usage via `llm.last_call_usage` → AttributeError crash when `LLM_PROVIDER=ollama_api`

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
  - `agent.py` — runtime branch: `LLM_PROVIDER=ollama_api` → `OllamaProvider`; default → `ClaudeProvider`
- **Tests**: 291 → 316 total

---

## ✅ start.vbs → launcher.py (2026-06-16)

Replaced by `launcher.py` — Python orchestrator in a single CMD window.

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

## 📋 P2 — [EPIC-25] Authentication, User Management & Billing

**Status:** Planned. Design-first — DO NOT implement without a design doc.

**Why:** Required before any commercial use. Blocks: user isolation, billing, role-based access to admin features.

**Scope (to be designed):**
- Auth mechanism — JWT / OAuth / magic link (TBD)
- Role model — at minimum `user` / `admin`; admin sees Settings screen, regular user does not
- Billing — per-vacancy pricing; Stripe or equivalent (TBD)
- Session management — Flutter secure token storage
- DB: extend `users` table or separate auth DB (TBD)

**Critical pre-design decisions:**
1. Single-tenant (one company, many users) vs. multi-tenant (many companies)?
2. Self-hosted auth vs. Supabase / Auth0?
3. Billing unit: per vacancy analyzed? per CV generated? subscription?

**Settings screen note:** currently shows all LLM/provider config — intended for dev/testing only. Once this EPIC lands, Settings route is gated on `admin` role. Regular users never see it.

**Start with:** design doc `docs/delivery/Epics/EPIC-25-auth-billing.md` — decisions, data model, API contracts, billing flow. No code until design is approved.

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
