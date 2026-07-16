# career-agent — Changelog

> Delivered features and fixes, reverse-chronological.
> Rules: [documentation-conventions.md](documentation-conventions.md).
> Entries here are history — never edited after the fact, only appended.

---

## 2026-07-16

- **DB cleanup — full normalization pass (4 of 5 audit findings resolved)**: full audit of `db/agent.db` (654 rows) surfaced 5 data-hygiene gaps.
  - **Backfilled `published_at` for 45 rows** (recount after the other fixes dropped this from the original 94): `UPDATE ... SET published_at = created_at WHERE published_at IS NULL AND status IN ('analyzed','fetched','cv_generated','cover_generated','analysis_failed')` — these now sort correctly by real date instead of falling to the bottom by id. Remaining 104 NULL rows are legacy-status (Part 2 scope) or `declined`, correctly untouched.
  - **Deleted 47 orphaned `user_id IS NULL` rows**: dated 2026-05-29 (day 1, pre-EPIC-13 multi-user), `markdown_path` pointing at the defunct `callback-cv`/`job-board-monitor` predecessor projects — invisible to Flutter (every query filters by `user_id`), zero real value, no `duplicate_of` referencing them (verified before deleting, would have blocked the FK). Includes vacancy #10, reported same session as incorrectly showing in "Analyzed" — not a `stage()` bug, dead data (empty `analysis_json`, source file gone). **Deliberately did NOT harden `vacancies.user_id` to `NOT NULL`**: `ON DELETE SET NULL` (EPIC-13) is intentional soft-orphan design, not an oversight — a NOT NULL constraint would break it. 654→607 rows.
  - **Backfilled `content_hash` for 412 rows** (18%→87% coverage): re-read `markdown_path` (JD.md), stripped the shared `# title\n\n[Source: url\n\n]---\n\n{body}` wrapper before hashing (matches `cv_fetch_jd.py`'s exact normalization so future fetches can match against these), whole-file fallback when the separator wasn't found (48 rows, harmless — sha256 avalanche means no false-positive dup risk, worst case is just a hash that won't match a sibling). 77 rows still NULL — no `markdown_path` yet or file missing, can't backfill without source text.
  - **Reset 20 fake-"analyzed" rows**: recount after the orphan-delete dropped this from 64 to 21 (most were the same orphans). Found and excluded one real exception before executing — **#48** has empty `analysis_json` but genuine `*_CV.md`/Cover files on disk (CLAUDE.md's documented e2e reference, 2026-06-02 — `analysis_json` DB persistence was added to the pipeline later than this row's generation); checked all other 20 for the same pattern, none had it. 18 → `fetched` (JD.md still exists, re-analyzable), 2 → `declined` (source gone).
  - `db/agent.db` backed up before each mutating step. 750 tests pass throughout. Two findings deferred: legacy-status growth (344 rows, user's own bulk-skip plan via upcoming Batch Mode) and `published_at` backfill (Part 1, low urgency).
- **5-stage vacancy taxonomy — Inbox/Analyzed/Processed/Applied/Archive**: replaces the old 3-folder model (Inbox/Applied/Archive, where Inbox lumped fetched-through-cover_generated together). `core/vacancy_stage.py` — pure `stage(status, applied)` classifier, single source of truth (declined→Archive wins over everything, applied→Applied wins over pipeline progress since a user can apply having only analyzed, or CV-only, or CV+Cover — Applied stays an orthogonal boolean, not a terminal status, to avoid losing that information). Legacy statuses (`fetching`/`queued`/`new`/`done`) mapped to their nearest current equivalent so they don't silently fall out of the taxonomy. `GET /api/vacancies` now returns a `stage` field; Flutter `_folderMatch` reduced to a straight lookup (`v.stage == folder`) instead of reimplementing the classification — nav rail now shows 5 folders + Settings (was 3 + Settings); empty-state copy added for Analyzed/Processed. 25 new tests (750 total). Physical folder-tree mirroring (moving files on disk to match) is a separate, much more expensive ticket — deferred to BACKLOG (FS+DB consistency, worker-race guards, ~12-16h).
- **Config single source of truth — provider/model/effort**: closes the two-masters ambiguity flagged 2026-07-13 (DB override vs `.env` snapshot read once at startup — the exact shape of bugs like the API-billing leak, where nobody could say which source was authoritative). `core/config_store.py` is now the ONLY module that knows where truth lives — `get_config()` / `set_config()` / `effective_model()`. `.env` `LLM_PROVIDER` seeds the DB **once**, on the first read after process start; after that, env is never consulted again for provider selection, for the rest of the process lifetime (and across restarts — the seed persists). `web/api.py`'s `/api/config` GET/PATCH and all three workers' `_fresh_llm` (analysis/cv/cover) now read/write exclusively through the store — no more per-call `database.get_user_settings(...) or self._settings.llm_provider` fallback scattered across files. **Drift guard:** `PATCH /api/config` accepts `expected_provider`; if it doesn't match the store's current value (someone/something switched providers since the client last read config), the backend returns **409** instead of silently attaching a model/effort change to the wrong provider — Flutter (`ConfigDriftException`) catches this, refreshes state from `/api/config`, and shows an amber SnackBar with the reason. `scripts/set_provider.py` — dev CLI to inspect/set the provider through the store (never hand-edit the DB row). `core/config_store.py` seam means a future multi-tenant/SaaS move only touches this one module.
  - **Found and fixed along the way — a real pre-existing test-isolation bug**: `web/api.py`'s `_DB_PATH` was a module-level constant frozen at import time (`Path(os.getenv("DB_PATH", ...))`), and `lifespan()` re-applied it on every `TestClient` startup — silently resetting each test's DB back to whichever `tmp_path` the *first* test in the session happened to use. Same bug class as the `_VACANCIES_PATH` fix (2026-07-14, `core/analysis_worker` pytest pollution): frozen import-time env reads defeat `monkeypatch`. Fixed with the same pattern — `_db_path()` reads env at call time. This had been silently accumulating state across ALL `client`-fixture tests in `test_web_api.py` for a while (invisible because most assertions filter by a just-created id) — became visible only once config_store started reading/writing a real process-wide singleton row (`user_settings` id=1). Several pre-existing tests (`test_set_salary`, `test_set_salary_clear`, `test_refresh_models_returns_list`) turned out to be unknowingly relying on that leak (never created their own user) and needed an explicit `insert_user` once the leak was closed.
  - **Caught and reverted a real production-DB mutation from a unit test**: `test_analysis_worker.py::test_execute_timeout_sets_analysis_error` mocked `database.get_user_settings` (returning `None`) but not `database.set_user_settings` — under the new `config_store` seeding path, a falsy read triggers a real DB write. Run in isolation (real `db/agent.db`, no test fixture configuring a temp DB), it silently overwrote the user's actual `llm_provider`/`llm_model` (`ollama_api`/`gemma4:e4b` → `claude_cli`/`None`). Caught before commit, real DB restored, test rewritten to mock `config_store.get_config` directly instead of the DB layer underneath it — matching the file's own "no real DB needed" contract.
  - Flutter: `_ProviderRow`, `_ModelDropdown`, `_EffortControl` all route through a shared `_patchConfigAndReport` helper (drift → amber toast, other errors → red toast) instead of firing-and-forgetting the patch.
  - 725 tests total (config_store: 13 new; web_api: 8 new/updated; analysis_worker: 2 rewritten).
- **Bug fix — "Open Folder" opened default Documents instead of the vacancy folder**: `folder_path` returned by `GET /api/vacancies` was `Path(markdown_path).parent` verbatim, but `markdown_path` is stored **relative** to the backend's CWD (`vacancies\inbox\1\554 — ...`). Flutter's `Process.run('explorer.exe', [folderPath])` resolves that relative path against its own CWD (not the project root) → invalid path → Windows Explorer silently falls back to the default Documents folder. Fix: `web/api.py` resolves `markdown_path` against `_PROJECT_ROOT` when it isn't already absolute, before deriving `folder_path`. 2 new tests (707 total).

## 2026-07-14

- **Bug fix — model selection silently ignored (root cause of "weak model crashes")**: user picked `gemma4:e2b` in Settings + Save, but analysis ran on `cas/aya-expanse-8b` (the `OLLAMA_MODEL` env fallback). Three compounding bugs: (1) `_save()` only persists apiUrl/pollInterval/notifications — provider/model/effort save separately via dropdown `onChanged`, so Save does NOT commit the model (misleading); (2) `_ModelDropdown` showed the first model as "selected" (firstOrNull) when the DB model wasn't in the list, but `onChanged` never fired without a manual click → `user_settings.llm_model` stayed NULL → pipeline used the env fallback; (3) provider switch resets model to NULL, feeding (2). Fix: `_ModelDropdown` now auto-commits the displayed model via post-frame `patchModel` when the saved model isn't in the list → what you see = what's stored = what runs. Requires backend restart to pick up the 006750c `_fresh_llm` DB-model change.
- **Bug fix — Phase 2 fails on decimal fit score**: small/local models emit `**Fit score:** 8.5/10`; `_FIT_SCORE_RE` required an integer (`(\d+)/10`) → no match → `p2=None` → `analysis_failed` (this was `cas/aya-expanse-8b` on #660). Regex now accepts decimals and the parser rounds (`8.5 → 8`). Previously only the CLI path normalised decimals (`_normalize_cli_output`); Ollama/API didn't. 3 new parser tests.
- **Bug fix — Phase 2 "analysis failed" on capitalised recommendation (provider-dependent)**: `Phase2Data.recommendation_label` validator used case-sensitive `v.startswith(base)` → a provider that emitted `**Recommendation:** Apply` (capital A) failed `"Apply".startswith("apply")` → `Phase2Data` raised → `p2=None` → vacancy stuck `analysis_failed`. Worse, the user-facing error lied ("missing Fit score/Recommendation" — both were present). Fixes: (1) validator now case-insensitive (`v.lower().startswith(base.lower())`); (2) `_parse_phase2_data` logs the real build exception instead of silently returning None; (3) reworded the surfaced error to not claim missing fields. Vacancy #660 (Empat, switched provider) restored from its existing JD_analysis.md without re-running the LLM. Regression test added (702 total).
- **Settings — manual "Refresh models" button + Ollama model selection**: `_get_available_models(provider, force=False)` gained a `force` flag that bypasses the 24h cache; `POST /api/config/refresh-models` force-fetches the active provider's model list (Ollama = `GET /api/tags`), persists to `system_kv`, returns it. Flutter Refresh button next to the Model label. **Ollama selection now fully wired:** `supportsModelSelection` = `availableModels.isNotEmpty` (dropdown shows for Ollama), and `_fresh_llm` (analysis/cv/cover workers) uses the DB `llm_model` override for Ollama, falling back to `OLLAMA_MODEL` env (previously always env → UI choice was ignored). Refresh → pick model → applies to next run, no restart. Deliberate stopgap over auto-refresh-on-switch (full auto-refresh + per-provider TTL deferred). 4 new tests (701 total).
- **Bug fix — Ukrainian CV/Cover files saved with Cyrillic names**: `re.sub(r"[^\w\-]", "_", name)` left Cyrillic intact because Python `\w` is Unicode-aware → `Олексій_Бондаренко_CV.md` (breaks filesystems/sync/email attachments). New `core/translit.py` (`to_latin` UA+RU table, `safe_filename_stem`) → filenames are always Latin ASCII (`Oleksii_Bondarenko_CV.md`); document content stays in its original language. Applied in `cv_generate` + `cv_cover` (same stem so the CV glob still matches; PDF inherits the Latin name from the MD path). 8 new tests (697 total). Note: pre-fix CVs saved with Cyrillic names must be regenerated to get Latin filenames.

## 2026-07-13

- **Bug fix — pytest littered `vacancies/inbox/` with throwaway user folders**: `web/api.py` bound `_VACANCIES_PATH` at import time from `VACANCIES_PATH` env → the test fixture's `monkeypatch.setenv` ran too late, so `POST /api/vacancies/import-jd` created real folders (`inbox/15..23/…`) under the project dir on every test run (real users are only 1, 2). Fix: replaced the import-time constant with a `_vacancies_root()` helper that reads env at call time → fixture's temp dir now wins. Verified: full 689-test suite leaves `inbox/` with only real users 1, 2. Cleaned 9 stray test folders (15–23) off disk. (`test_cv_analyze`/`test_cv_fetch_jd` were already safe — they use `deps.vacancies_path=tmp`.)
- **Settings — switch LLM provider from UI**: Provider row in Flutter Settings changed from read-only text to a dropdown (Claude API / Ollama (local) / Claude CLI ($0)). Provider stored in `user_settings.llm_provider` (new column + migration; NULL = `LLM_PROVIDER` env default), same override pattern as model/effort. `/api/config` reads provider from DB override + exposes `valid_providers`; `PATCH /api/config` accepts `llm_provider`, validates against `{claude_api, ollama_api, claude_cli}`, and on switch resets `llm_model=NULL` (a model of one provider is invalid for another) → new provider's env default + refreshed `available_models`. Provider stored only when it diverges from env (stays NULL otherwise). Workers' `_fresh_llm()` (analysis/cv/cover) now read provider from DB per task → change applies to the next queued vacancy without a backend restart. Flutter: `config_provider.patchProvider()`, `patchConfig(llmProvider)`, `_ProviderRow` dropdown. 4 new API tests + valid_providers assertion (689 total)
- **Bug fix — re-publish bump for analyzed vacancies never fired**: EPIC-26 design said a settled (`analyzed`/inbox) vacancy re-published in RSS with a newer `published_at` should update its date and rise in the inbox, but `api_new_vacancy` only handled `declined`/`skipped` (republish) and fell through to `409 duplicate` for everything else — so employer bumps on already-analyzed roles were silently dropped and the vacancy stayed buried (also left pre-EPIC-26 rows with `published_at=NULL` stuck at the bottom, e.g. #73 DOU come-back-agency). Fix: `bump_published_at()` DB helper + new branch — settled statuses → update `published_at` only (no status change, no badge, returns `status=bumped`); active statuses (`analyzing`/queued/generating) left untouched; `declined`/`skipped` still reopen. Rewrote `test_new_vacancy_analyzed_still_409` (locked the buggy behaviour) → `_bumps_published_at`; +3 tests (NULL bump, same-date 409, active-not-disturbed). 684 total

## 2026-07-12

- **EPIC-21 closed** — Deterministic vs Cognitive pipeline split: T1 (weasyprint PDF), T2 (Pydantic contracts), T3 (metrics → Python: `core/vacscore.py` + `core/cv_metrics.py`), T4 (FSM orchestrator, 4-C1/C2/C3/C5). T5/T6/T0 dropped (quality risk > latency benefit). 4-C4 (Phase 2.5 Flutter) → backlog P1
- **Reset stuck vacancies**: `POST /api/vacancies/{id}/reset` — allowed for `analyzing`/`analysis_queued`/`analysis_failed` → resets to `fetched`; 10-min `asyncio.wait_for` timeout on `_execute()` → `analysis_failed` on hang; Flutter Reset & Retry button (orange) in ActionBar when `status=='analyzing'`; Reset & Retry replaces bare Retry in `_AnalysisErrorView` + `_AnalysisErrorBanner` — all retry paths now `/reset` → `/analyze` chain; `VacancyRepository.reset()`; 5 new tests
- **Worker availability detection**: `GET /api/health` endpoint returns `{"status":"ok","worker_available":bool}` (checks `app.state.analysis_worker`); `HealthStatus.degraded` added to Flutter enum; `HealthRepository` now calls `/api/health` and returns `degraded` when worker absent; `BackendStatusDot` shows amber 🟡 with tooltip "no analysis worker" for degraded state; Analyze / Re-analyze buttons disabled (greyed + tooltip) when `workerAvailable == false`; 2 new tests (681 total)
- **AnalysisWorker periodic sweep**: `asyncio.wait_for(queue.get(), timeout=300)` + `_recover_queued()` on `TimeoutError` → picks up vacancies queued while worker was down
- **Standalone tracker port moved to 8081**: `.claude/launch.json` updated so tracker preview never conflicts with agent.py on 8080
- **"Add New Vacancy" via file upload**: `POST /api/vacancies/import-jd` endpoint (content_hash dedup, synthetic `import://` URL, folder creation, `JD.md` write); `VacancyRepository.importJd()` in Flutter; FAB triggers `FilePicker.platform.pickFiles(md/txt)`; SnackBar feedback on success/dup/error; site detection from URL in JD content (`_detect_site()`); role/company extraction from H1 (`_extract_title_and_company()`, work.ua pattern); 5 new API tests
- **NavigationRail Add button — ghost style + snake hover**: `_AddVacancyButton` StatefulWidget with `AnimationController`; ghost `Border.all(outlineVariant)` at rest; on hover → `SnakePainter` animated border + `primaryContainer` bg; `SnakePainter` made public (renamed from `_SnakePainter` in `processing_wrapper.dart`) for cross-file reuse; button placed in nav group above `Spacer` (Inbox/Applied/Archive/Add ↑ Spacer ↓ Settings)
- **Cursor fixes app-wide**: `SystemMouseCursors.click` on `VacancyCard` `MouseRegion`, `StarToggle`, `DuplicateBadge` (conditional), `RelatedBadge` (conditional), `SalaryDisplay`, `JdSection` `InkWell`; `_NavRailItem` `InkWell.mouseCursor`
- **`docs/ui/flutter-ui/` directory**: moved from `docs/architecture/flutter-ui/` (git rename, history preserved)
- **`docs/ui/flutter-screen-anatomy.html`**: annotated anatomy diagram of all named Flutter UI elements; published as Artifact

## 2026-07-10

- **Bug fix — wrong `PROFILE_MD_PATH`**: `.env` default pointed to `../callback-cv/skill/PROFILE.md` (old sibling repo); subprocess received stale profile without `## Contacts` verbatim line, Portfolio link, or `## Additional Evidence` caveats → CV contacts wrong, portfolio missing. Fixed: `PROFILE_MD_PATH=skill/users/1/PROFILE.md`
- **Bug fix — `phase2_fit.md` display rule vs `_GUARD` conflict**: old rule said "All other sections go to JD_analysis.md only — never shown in chat" → model tried to use Write tool → `_GUARD` blocked it → model output "File write was denied." → Python saved that text to file. Fixed: rule rewritten to "Output ALL four sections in full. The calling system handles file storage."
- **Fix — `JD_analysis.md` Phase 3.5 overwrites instead of appends**: each CV re-run was appending a new `## Phase 3.5: CV Self-Review` block to `JD_analysis.md`; after N reruns: N review blocks in file → context bloat + signal pollution in next Phase 3 run. Now: read file → strip existing Phase 3.5 block → write Phase 1+2 base + single latest review. Always exactly one review, always current.
- **Flutter — starred-only filter chip in inbox**: `_starredOnly` flag + `FilterChip` with star avatar in `_FilterPanel`; counts toward `_activeFilterCount`; resets with `_clearAllFilters()`; `/analyze` skill: added `[N+3] Вакансия по ID` option to inbox menu + routing rule

## 2026-07-09

- **EPIC-26 complete** — T1: DB migrations (duplicate_of, content_hash, republished_at); T2: content_hash + find_duplicate in cv_fetch_jd; T3: re-publish detection in `/api/new-vacancy` (declined/skipped + newer published_at → on_vacancy_republished → status=fetched); T4: list_vacancies ORDER BY published_at DESC NULLS LAST, id ASC; T5: Flutter VacancyListItem.duplicateOf/republishedAt + "↑ Republished" amber badge + "Dup #X" muted badge; clickable badges → cross-navigation (card Dup#X tap + detail _RelatedSection with Original/Dup chips, _crossFolderNav flag); hover tooltips on all dedup/republish badges; 527 tests. Design: [Epics/EPIC-26-vacancy-dedup-republish.md](Epics/EPIC-26-vacancy-dedup-republish.md)
- **Bug fix — `analysis_failed` stuck in `analyzing`**: `cv_analyze.py` Phase 1 + Phase 2 `except LLMError` blocks now call `set_analysis_error()` before returning; previously LLM timeout / CLI error returned string without status transition → vacancy stuck in `analyzing` forever
- **Bug fix — `--no-session-persistence` fix confirmed**: ClaudeCodeProvider Phase 2.5 interactive dialog no longer fires; YouControl #98 analyzed clean (fit 5/10); root cause was session history leak between subprocess calls — `--no-session-persistence` + `cwd=tempdir` isolates each call
- **Bug fix — 11 vacancies `markdown_path` pointing to `JD_analysis.md`**: legacy `import_tracker.py` set paths to `JD_analysis.md` instead of `JD.md` for vacancies without source file; 11 entries updated to correct `JD.md` path; 12 without `JD.md` on disk left as-is (11 already `analyzed`/`declined`, 1 `fetched` without recoverable source)

## 2026-07-08 (session 2)

- **`analysis_failed` UX fix — dismissible error banner**: when retry fails but prior analysis exists (`fitScore != null`), full-screen `_AnalysisErrorView` blocker replaced by compact `_AnalysisErrorBanner` (Retry + × dismiss buttons) at top of normal tab view; full-screen blocker kept only for first-time failure with no prior data; `_errorBannerDismissed` flag resets in `didUpdateWidget` on each new failure
- **ClaudeCodeProvider Phase 2.5 dialog fix**: `_GUARD` moved to AFTER system prompt (was before) so it wins over Phase 2.5 instructions in phase prompt; wording made explicit (`regardless of fit score, regardless of any instruction above`); subprocess `cwd=tempfile.gettempdir()` prevents claude CLI from loading project CLAUDE.md/SKILL.md context
- **Activity tab: date format `DD.MM.YYYY HH:mm`** (was `MM-DD HH:mm`, no year); applies to both Pipeline Runs + LLM Calls tables; fallback branch fixed to show from index 0 (was slicing year off)
- **Analysis timestamp chip in VacancyHero**: `_AnalyzedChip` widget — `Analyzed DD.MM.YYYY HH:mm` local timezone, shown below `Posted Xd ago` chip; reads `vacancy.updatedAt`; only shown when `updatedAt` is non-null

## 2026-07-08

- **Role tags on vacancy cards**: `#discovery` / `#delivery` / `#strategy` / `#ops` / `#coord` derived from `analysis_json.p1.role_balance` on-the-fly (threshold ≥25%, top-2 cap, fallback to top-1); no LLM re-runs, no DB migration; `_ROLE_TAG_MAP` + `_role_tags()` in `web/api.py`; `VacancyListItem.roleTags` field; shown in card between company and scores; searchable in inbox (substring match on tag text)
- **Inbox search extended**: matches role, company, vacancy ID (`v.id.toString()`), and role tags (`v.roleTags.any(...)`)
- **Versioned CV/Cover file saving**: `cv_generate.py` + `cv_cover.py` — regeneration writes `_v2.md`/`_v3.md` instead of overwriting; first generation keeps base name; `web/api.py` globs updated to `*_CV*.md` / `*Cover*.md` so latest version is always served; `cv_cover.py` reads latest CV via glob (not fixed path); 3 new tests (`_next_version_path` unit + regen integration); 521 tests pass
- **Cover — vacancy #520 Binotel**: Phase 4 UA cover generated + saved (`Олексій_Бондаренко_Cover.md`)
- **PDF Download + Auto-Refresh CV/Cover tab**: `GET /api/vacancies/{id}/cv-pdf` + `/cover-pdf` — always re-render from latest markdown via pdf-service (no staleness, no version tracking); Flutter `VacancyRepository.getCvPdfBytes()` / `getCoverPdfBytes()` → `Uint8List`; `_downloadPdf()` real implementation — "Preparing PDF..." SnackBar → `FilePicker.platform.saveFile(bytes: ..., fileName: ...)` → error SnackBar on failure; auto-refresh polling 3s when `cv_queued`/`cv_generating`/`cover_generating` → stops on completion; `didUpdateWidget` auto-switch Cover tab on `cover_generated`; `file_picker: ^8.1.7` added
- **Telegram stripped to push-only**: `core/router.py` deleted; `core/telegram.py` rewritten (469→65 lines) — Dispatcher, FSM, onboarding (`/start`, `/update_profile`, `/set_skill`, PDF upload), inline keyboards, `on_message`/`on_callback`, `multi_user_enabled` all removed; `agent.py` main loop now uses `stop_event.wait()` instead of long polling; TelegramBot init simplified to `token + chat_id`; closes last direct-API leak source (Router used `AnthropicProvider` for every incoming Telegram command)
- **Bug fix — API leak: claude_cli billing via ANTHROPIC_API_KEY**: `ClaudeCodeProvider._subprocess_env()` was copying full `os.environ` including `ANTHROPIC_API_KEY` into the `claude` subprocess — CLI used the key for direct API billing instead of its OAuth subscription, causing unauthorized charges (38K–41K input tokens per analysis call observed in Anthropic dashboard). Fix: `env.pop("ANTHROPIC_API_KEY", None)` before passing env to subprocess. Second leak: `web/api._get_available_models()` was calling `_fetch_anthropic_models()` (HTTP GET `/v1/models` with API key) for `claude_cli` provider — now restricted to `claude_api` only; CLI uses `_FALLBACK_MODELS` entry. See `docs/discovery/retrospective.md`.

## 2026-07-07

- **Vacancy #543 — Kiss My Apps (AI Learning Platform)**: Fit 6/10 · VScore 8.8 · take a chance — premium opportunity; CV EN + UA generated; Application_answers.md (Djinni); PROFILE.md updated (feature adoption rate evidence + 2-component AI paragraph EN+UA)
- **Vacancy #545 — RedCore (PM Finance)**: Fit 7/10 · VScore 7.9 · apply — strong match; CV EN + Cover generated; BOS-from-scratch positioning; ERP-like framing
- **CV markdown bug fix**: blank line required before bullet lists after `**Key results:**` — Python markdown parser collapses to inline without it
- **AnalysisWorker — DB recovery on startup**: `_recover_queued()` runs once at AnalysisWorker start; picks up `analysis_queued` vacancies left from crash or restart and re-enqueues immediately (no polling delay)
- **launcher.py — removed standalone Web API**: `Web API :8080` entry removed from SERVICES; agent.py now owns the embedded FastAPI server with workers in the same process → `app.state.analysis_worker` always set → Flutter Analyze button hits real worker directly
- **db.reset_stuck_statuses() — isolated from init_db()**: DB crash-recovery (`analyzing → analysis_queued`, `cv_generating → cv_queued`) moved out of `init_db()` into separate `reset_stuck_statuses()`; called explicitly in agent.py before workers start; web API lifespan `init_db()` no longer clobbers active work on startup

## 2026-07-06

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
- **cv_generate — Cyrillic split fix**: Strategy 4 regex extended to `[A-ZЀ-ӿ]`; Phase 3.5 output with Ukrainian name (`# Олексій`) previously fell through all 4 strategies; Phase 3.5 prompts updated — `---CV---` must be plain text, not inside code block; 5 new tests (vacancy #570 reproducer)
- **CV/Cover Language Selection**: `CVWorker.enqueue(language="auto")`; `cv_generate` auto-detects Cyrillic → Ukrainian else English; `POST /generate-cv` accepts `{"language": "en"|"uk"|"auto"}`; Flutter split-button: main = auto, ▾ menu = English / Ukrainian; `vacancy_repository.generateCv({language})`
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

## 2026-07-05

- **EPIC-23 complete** — Claude Code CLI Provider: `LLM_PROVIDER=claude_cli` → calls go through `claude -p` subprocess → uses Claude Code subscription, cost $0. `ClaudeCodeProvider` implemented + tested; Flutter Settings shows active provider. All 5 tasks done.
- **Flutter Settings — dynamic model list**: available models fetched from Anthropic API / Ollama at runtime; 24h TTL cache in `system_kv` table; fallback to hardcoded list on network error
- **Flutter Settings — thinking effort**: `SegmentedButton` (Off/Low/Med/High/xHigh/Max); hidden for Ollama; `PATCH /api/config`; stored in `user_settings` DB table
- **Flutter Detail — hover tooltips**: `_TooltipTitle` on all major sections (Fit, Attraction, Quick Overview, Fit Dimensions, Attraction Breakdown, Role Balance)
- **Flutter Detail — JD always visible**: Job Description section always shown at bottom of detail view; pushed down by analysis, never hidden
- **Flutter Detail — score dot rows**: Fit + Attraction shown as colored dot rows (≥70% green / 40–69% amber / <40% red) in `_VacancyHero`
- **Flutter Detail — sections collapsed by default**: Fit Dimensions, Attraction Breakdown, Role Balance collapsed; Job Description expanded

## 2026-07-03

- **Flutter Inbox — Analyze / Skip / Restore**: action buttons in JD view; Skip → `declined`; Restore from archive → inbox
- **Flutter Inbox — queue animation**: "In queue" badge with pulse animation; "Analyzing..." spinner badge
- **Flutter Inbox — analysis error surfacing**: `analysis_failed` state shown with error message + Retry button
- **Flutter Inbox — markdown JD render**: `flutter_markdown` in JD view and JD section of detail screen

## 2026-07-01

- **Flutter Detail — CV / Cover preview**: `VacancyCvDialog` — side-by-side CV.md + Cover.md with markdown render; Generate CV button in action bar
- **Flutter Detail — full analysis view**: `_VacancyHero`, `_QuickOverviewCard`, `_FitDimsTable`, `_VacScoreTable`, `_RoleBalanceBar`, `_CollapsibleSection`

## 2026-06-30

- **Flutter Inbox — vacancy list with polling**: 30s polling, cache in SharedPreferences, status-based folder routing (inbox / in_progress / applied / archive)
- **Flutter Inbox — filter panel**: status chips + date range picker
- **Flutter Inbox — search**: role + company full-text filter

## 2026-06-20

- **Flutter MVP scaffold**: app shell, navigation rail, VacancyCard, VacancyInboxScreen master-detail layout
- **RSS watcher → Web Push**: after Phase 1+2 analysis completes, push notification sent to Flutter via VAPID
- **Phase A blockers — auto-pipeline foundation** (4 infrastructure gaps unblocked):
  - **#1 CandidateProfile schema**: `contracts/profile.py` — `CandidateProfile(BaseModel)`: `skill_type`, `language`, `domain_interests`, `company_stage_prefs`; `phase1_context()` returns compact JSON for Phase 1 injection; `core/profile_loader.py` — `parse_profile_md(text)` parses `## Settings` + `## Vacancy Preferences`; `AgentDeps.profile` field; 20 tests
  - **#2 OllamaProvider.last_call_usage**: property tracks `prompt_eval_count` / `eval_count`; matches ClaudeProvider shape; fixes AttributeError crash when `LLM_PROVIDER=ollama_api`; 4 tests
  - **#3 cv_fetch_jd returns vacancy_id**: split into `fetch_jd(deps, url) -> int` (core) + `cv_fetch_jd(ctx, url) -> str` (tool wrapper); `FetchError` exception replaces string error returns; 26 tests
  - **#4 RSS batch semaphore**: `asyncio.Semaphore(concurrency)` guards `cv_fetch_jd` in `_process`; `RSS_CONCURRENCY` env var (default 2); prevents parallel LLM rate-limit hits; 5 tests
  - Tests total: 320 → 362

## 2026-06-18

- **Ollama error handling + model testing**:
  - No-timeout mode — `OLLAMA_TIMEOUT=0` → `read_timeout=None` in httpx (for slow thinking models like qwen3:8b)
  - `done_reason` logging — every OllamaProvider call logs `model / elapsed / in / out / done_reason`
  - Truncation detection — `done_reason='length'` → raises `LLMError` with actionable message
  - `scripts/test_ollama_pipeline.py` — `--phase 1|2` flag
  - Model comparison (vacancy #120): best for logic testing = `gemma4:31b-cloud` (105s, full structure, free); qwen3:8b ★★★ but 19 min
  - Tests: 316 → 320

## 2026-06-17

- **RSS watcher hardening**: notify-first (Telegram before processing), salary from title, status machine fix (fetching→done), concurrent processing via `asyncio.gather`; `_site_from_url()` + site set at webhook insert; `published_at` column added + backfilled
- **Inbox folder naming** — `{vacancy_id} — {role} — {company}` format: `ParsedDocument.company` field; `_extract_company()` in parser (DOU from URL slug, Djinni from `<title>`); DB insert before folder creation; `_safe_folder_name()` strips forbidden Windows chars
- **Ollama LLM provider**: `OllamaProvider` full httpx implementation (POST `/api/chat`, 300s timeout, `LLMUnavailableError` on connect fail); `LLM_PROVIDER` / `OLLAMA_BASE_URL` / `OLLAMA_MODEL` env vars; runtime branch in agent.py
- Tests: 291 → 316

## 2026-06-16

- **start.vbs → launcher.py**: Python orchestrator in a single CMD window replaces VBS launcher

## 2026-06-15

- **RSS automation + local startup**: `scripts/import_seen_jobs.py` (`--today`, `--dry-run`); 7 feeds migrated to `services/job-monitor/feeds.json`; monitor .env path fix; docker-compose `:ro` removed from web-tracker DB volume; per-service `run_*.bat` files; telegram_chat_ids seeded for users 1+2
- **Decision — services/job-monitor divergence is intentional**: our monitor pushes to career-agent webhook (`POST /api/new-vacancy`), original repo pushes to Telegram. Do not sync from original. One-time import via `import_seen_jobs.py`.

## 2026-06-14

- **VScore + Recommendation Matrix**:
  - VScore — 8-dimension vacancy attractiveness score (1–10): company_tier, seniority, market_scope, company_type, company_stage_fit, domain_score, remote_policy, compensation
  - `prompts/pm/phase1_analysis.md` + `prompts/generic/phase1_analysis.md` — section 1.7 (formula, output, domain_score detail)
  - `skill/SKILL.md` — Quick Scan format `**VScore:** X.X/10`; p1 JSON schema extended with `vacancy_score` + `vacancy_dims`
  - `skill/users/1/PROFILE.md` — `## Vacancy Preferences` (domain_interests + company_stage_prefs)
  - `web/reader.py` + `tracker.html` — VScore column (green ≥7.5 / amber 5.5–7.4 / gray <5.5)
  - Fit × VScore recommendation matrix: hard blockers OR fit < 5 → `decline` always; Fit 5–6 + VScore ≥7.5 → `take a chance — premium opportunity`; Fit 5–6 + VScore <5.5 → `decline — not worth the effort`; Fit ≥7 + VScore <5.5 → `apply — limited upside`

## 2026-06-04

- **Pipeline hardening (2nd session)**:
  - `scripts/inbox_scan.py` — canonical recursive inbox scanner (title + Source URL parse, dedup, `raw_folder`, `--json`); root cause: non-recursive `ls` missed folder-based drops
  - `/analyze` Step 0 → combined two-block menu (profile/mode + inbox), no round-trip
  - `services/pdf/render.py` — `render_md` cover-aware (CV-header parsing only when contacts-links line present); fixes cover overflow
  - `prompts/pm/phase3_cv_draft.md` — CV contacts line fixed verbatim
  - PDF sections rewritten to use `services/pdf` only; deprecated `../callback-cv/cv_to_pdf.py` references removed

## 2026-06-02

- **Batch inbox — move-to-clean-folder flow**: `vacancy_track.py delete-inbox` subcommand (path traversal guard, idempotent); SKILL.md Batch + Sequential modes updated
- **Inbox deduplication**: Sequential mode step a.5 dedup (URL grep → skip/reprocess prompt); Batch mode silent dedup with `♻️ already processed`
- **health_check.py**: parser + pdf-service HTTP checks, SQLite SELECT 1, optional Telegram alert; exit 0/1; `--telegram`, `--parser-url`, `--pdf-url` flags
- **e2e verify: generate+cover** — vacancy #48, CV.md ✅ PDF ✅ Cover.md ✅ ($0.10); fixed pdf-service font path (relative → absolute) + `load_dotenv` in render.py
- **Batch mode for inbox**: 3+ vacancies → auto batch mode; Phase 1+2 silent for all → consolidated table (#, Company — Role, Src, Fit, Rec, Level/$, Key gap) → Approve / Try chance / Skip; sequential mode unchanged for 1–2
- **URL deduplication + Local mode → Tracker**: `normalize_url()` (strips UTM, trailing slash, lowercases host); `extract_site()`; `insert_vacancy()` stores normalized URL; `get_vacancy_by_url()` legacy fallback; `scripts/vacancy_track.py` CLI (`upsert` / `update` / `move-processed`); +14 tests, 279 total
- **Tracker: source grouping + site filter**: rows grouped by date → source; colored site chips (DOU green, Djinni blue, LinkedIn navy); source filter dropdown with localStorage persistence; sort date DESC → site ASC → rec_order; 6 new tests, 259 total
- **Skill pipeline improvements**: `/analyze` Step 0 mode selection (Local vs API); `vacancies/inbox_manual/` drop zone; cover letter two variants (A narrative + B bullets); Ukrainian CV no РЕЗЮМЕ header (Rule 15); PDF paragraph spacing fix (`ln(1)` → `ln(4)`); legacy KMP cleanup

## 2026-06-01

- **EPIC-18** — Rename `agent-hub` → `career-agent`
- **EPIC-13** — Multi-user data model: `users` table, `user_id` FK, default user seeding, user-scoped vacancy paths, tracker filter (241 tests)
- **EPIC-14** — services/pdf/: render.py + FastAPI /render endpoint, CVAdapter subprocess → httpx (235 tests)
- **EPIC-15** — services/parser/: stripped knowledge-mirror-parser, djinni+dou only, docker-compose updated
- **EPIC-17 Phase 1** — Telegram onboarding: /start FSM, PDF upload (pypdf), profile_json in DB, /update_profile, /set_skill, ClaudeProvider loads from DB, MULTI_USER_ENABLED flag (250 tests)
- **Multi-skill routing Phase 1** — `prompts/pm/` + `prompts/generic/`, skill_type in AgentDeps

## Pre-pivot (EPIC 01–12)

See `epics-archive/EPIC-01-12-pre-pivot.md`
