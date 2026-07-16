# career-agent — Backlog

> Last updated: 2026-07-16
> Rules: [documentation-conventions.md](documentation-conventions.md) · History: [CHANGELOG.md](CHANGELOG.md) · Specs: [Epics/](Epics/)

**Priority legend:**
- 🔴 **P0** — блокеры / надо делать первым
- 🟠 **P1** — высокая ценность, следующее в очереди
- 🟡 **P2** — ценно, но не срочно
- 🧊 **Icebox (P3+)** — когда-нибудь

---

## 📌 Now

*(empty — pick from P0/P1)*

---

## 🔴 P0

### Competitive landscape analysis (requested 2026-05-31 — overdue)
**What:** research similar services (AI-assisted job search, CV tailoring, fit analysis — PM-focused).
**Why:** understand the market before building further; critique our positioning with real data.
**How:** research prompt from `docs/discovery/product-thesis.md` + `docs/discovery/ideas.md` + README → web search.
**Output:** `docs/discovery/competitive-analysis.md` with verdict: is the gap real, what to adjust.

---

## 🟠 P1

### Pre-filter critical blockers before spending LLM tokens (added 2026-07-16)
**Story:** As a user, I want obviously-disqualifying vacancies (hard blockers like "English C1 required", "must reside in EU", "mobile B2C experience required" when I have none) filtered out cheaply BEFORE Phase 1+2 runs, so tokens aren't spent analyzing a vacancy that was never viable.
**Context:** born from the "Inbox Zero" philosophy discussion (2026-07-16) — a good inbox is a *processed* inbox; obvious non-starters shouldn't even reach the point of costing an LLM call, let alone sitting around for the user to manually skip later.
**Design sketch (not decided, needs its own pass):**
- New `## Critical Blockers` section in `PROFILE.md`, same pattern as the existing `## Vacancy Preferences` (domain_interests etc.) — user-editable list, e.g. `english: C1`, `location: EU-resident-required`, `domain: mobile B2C experience required`.
- Cheap deterministic check (regex/keyword match against JD text) — NOT an LLM call — run right after JD fetch, before Phase 1+2. Inherently fuzzy (phrasing varies: "advanced English", "C1 level", "fluent English" all mean similar things) — expect false negatives, acceptable since it's a pre-filter not a decision-maker.
- **Advisory only, never auto-skip**: surface a flag/badge in Flutter ("⚠️ Possible blocker: English C1 required") so the user makes the final skip call themselves — matches user's own words: "показывать пользователю, а он потом сам скипает." Auto-declining silently would risk false-negative-driven loss of real opportunities.
- Complements (doesn't replace) Phase 2's LLM-driven Key Barriers — this is a cruder, free, earlier gate; Phase 2 remains the nuanced analysis for vacancies that pass the gate.
**Not scoped/estimated yet** — needs its own design session before implementation.

### Physical folder tree mirrors vacancy stage (added 2026-07-16)
**Story:** As a user, I want the filesystem folder structure to match the visual 5-stage taxonomy — `vacancies/inbox/{user}/Analyzed/`, `.../Processed/`, `.../Applied/`, `.../Archive/` — not just the UI, so browsing on disk matches browsing in the app.
**Context:** separate from (and much more expensive than) the computed `stage()` UI work shipped 2026-07-16 — that one is a read-only projection, this one physically moves vacancy folders on every stage transition. Estimated ~12–16h (2–2.5 days), medium-high risk — classic FS+DB consistency problem, not a UI task.
**Risks (why this is its own ticket, not bundled):**
- **Worker race**: CVWorker/CoverWorker write files into the vacancy folder mid-phase; a user-triggered move (e.g. marking Applied) while a phase is active would write into a path that no longer exists. Needs a guard — don't move while status is in the active set (`analyzing`/`cv_generating`/`cover_generating`).
- **Atomicity**: filesystem move + DB `markdown_path` update are two separate operations, not a transaction. A crash between them desyncs DB and disk. Needs idempotent move (check "already at target" before moving) + a startup reconciliation pass.
- **9+ call sites**: every `database.update_vacancy_status(...)` call (web/api.py ×5, analysis_worker, cv_worker, cover_worker, tools/cv_analyze.py, cv_generate.py, cv_cover.py, rss_watcher.py ×3) needs to also trigger the mover — centralize via a wrapper around `update_vacancy_status` rather than patching every site individually.
- **Legacy statuses**: the 344 `fetching`/`queued`/`new`/`done` vacancies (see "DB data cleanup" bug ticket) need explicit stage classification too, or they fall through the new folder structure silently.
**Scope:**
- [ ] `core/vacancy_stage.py` — reuse the `stage()` classifier from the UI work (single source of truth for both Flutter routing and folder placement)
- [ ] `move_vacancy_folder(vacancy_id)` — idempotent mover: compute target dir from stage, `shutil.move` if not already there, update `markdown_path` in same call
- [ ] Guard: skip move while status is in the active set
- [ ] Wrapper around `update_vacancy_status` (or explicit call after each transition) triggering the mover
- [ ] Startup reconciliation: scan for DB/disk drift, fix or log
- [ ] Tests: idempotent move, active-status guard, path update, at least one real transition end-to-end

### Settings: auto-refresh available models on provider switch (added 2026-07-14)
**Story:** As a user, after switching provider I want the model list to reflect what's actually available right now — especially local Ollama, where I `pull`/`rm` models between runs and a stale list is useless.
**Problem:** `_get_available_models` caches 24h for ALL providers (`web/api.py:341,375`). Ollama models change instantly but the cache hides new ones for a day; the localhost fetch is cheap (~5s) so caching it barely helps. On provider switch the PATCH returns the cached list, not a fresh fetch.

**✅ NOW — manual refresh (temporary, shipped 2026-07-14).** Deliberately simple & robust: user clicks "Refresh models" → force-fetch current provider → write to `system_kv` cache → list updates. No TTL guessing, always works. The full auto-refresh below is NOT dropped — this is a stopgap until a smarter algorithm is worth it.
- [x] `_get_available_models(provider, force=False)` — `force=True` bypasses cache
- [x] `POST /api/config/refresh-models` → force-fetch current provider, persist, return list
- [x] Flutter: "Refresh" button next to Model label
- [x] Tests (refresh returns list, force bypasses cache)

**✅ Ollama model selection wired (2026-07-14).** (a) `supportsModelSelection` now = `availableModels.isNotEmpty` (dropdown shows for Ollama too); (b) `_fresh_llm` ollama branch (analysis/cv/cover) uses DB `llm_model` override, falls back to `OLLAMA_MODEL` env. Refresh → pick Ollama model → applies to next run. 2 tests.

**🎯 FULL (deferred) — automatic refresh on provider switch.** Do when it earns its keep, or when a more progressive algorithm emerges.
- [ ] per-provider TTL: `ollama_api → 0 (always fresh)`, `claude_api/claude_cli → 24h`
- [ ] `PATCH /api/config` provider switch → `force=True` (auto, no button needed)
- [ ] `GET /api/config?refresh=true` query param
- [ ] Drop/relegate the manual button once auto is reliable

### Architecture note — Flutter is becoming a dual client (user + admin) (added 2026-07-13)
**Observation:** the Flutter app (Windows/Web) is now both the end-user client (inbox, analysis, CV) AND the system-admin client (Settings: provider/model/effort — billing- and safety-relevant controls). Mixing the two surfaces in one unguarded app is the risk behind the API-leak class: a regular user must never see or flip the provider.
**Direction (decide in EPIC-25):** either (a) role-gated admin route inside the same app (Settings visible only to `admin` after auth), or (b) a separate admin console entirely. Industrial norm = admin surface is separated or RBAC-gated, never open to every user. Until auth lands, Settings stays visible for single-user dev testing — but treat it as an admin surface, not a user feature.
**Ties to:** [Epics/EPIC-25-auth-billing.md](Epics/EPIC-25-auth-billing.md), memory `project_settings_access_control`.

### Flutter: Batch Analysis Mode (mass queue + mass skip) (added 2026-07-08, extended 2026-07-16)
**What:** multi-select in inbox → "Analyze N" (all queued in AnalysisWorker, queue position badge per card) **or** "Skip N" (bulk decline → archive). Same multi-select UI, two actions.
**Why:** biggest daily friction — morning RSS batch drops from 10–15 clicks to 2; makes RSS auto-push feel automated. Skip N needed to clear the 344 legacy-status vacancies (`fetching`/`queued`/`new`/`done`) sitting invisible in the DB — user plans to bulk-skip them once this ships rather than debug why `fetching` accumulates.
**Scope:**
- [ ] `VacancyInboxScreen` — `_multiSelectMode` + `_selectedIds`; long-press entry
- [ ] `VacancyCard` — checkbox overlay + selected highlight
- [ ] `_BatchActionBar` — slides up, count label, **Analyze** + **Skip** buttons
- [ ] Queue position badge ("In queue (3rd)") — derive from `analysis_queued` count
- [ ] `VacancyRepository` — batch decline (loop `PATCH .../decline` or a new bulk endpoint if N is large)
- [ ] Tests: multi-select state, action bar visibility, repository calls (both actions)

### LLM Quality Parity: SKILL.md rules → API system prompt (added 2026-07-08)
**What:** audit SKILL.md → extract output-quality rules (tone, language, positioning, per-user overrides) → inject as cached system-prompt block after PROFILE.md in all API/CLI calls.
**Why:** skill mode sees SKILL.md fully, API mode doesn't → same model produces coarser output ("CLI just follows steps").
**Scope:**
- [ ] Audit `skill/SKILL.md` — classify sections: orchestration (Python has it) vs quality (LLM needs it)
- [ ] Write `prompts/pm/system_quality_rules.md` + `prompts/generic/system_quality_rules.md` + per-user `skill/users/[id]/quality_rules.md`
- [ ] `core/llm_client.py` — load + append after PROFILE.md (second cached block); same for ClaudeCodeProvider
- [ ] Validate: same vacancy skill mode vs API mode — compare tone, barriers, positioning, language compliance

### Phase 2.5 Objection Handling in Flutter (4-C4) (added 2026-07-06)
**What:** after Phase 1+2, present Key Barriers to candidate → user responds with evidence → LLM classifies `resolved | gap` → feeds Phase 3 (address resolved, don't overclaim gaps).
**Why:** without it CV generation is blind to counter-arguments — misses positioning opportunities or covers real gaps generically.
**Scope:**
- [ ] `prompts/pm|generic/phase2_5_objections.md` — classification prompt
- [ ] `POST /api/vacancies/{id}/barrier-responses` → classified `p2_5` saved to analysis_json
- [ ] `tools/cv_generate.py` — inject resolved/gap context before Phase 3
- [ ] Flutter `BarrierResponseScreen` — needs UI design first (blocker)

### EPIC-24 remainder: T7 + T9 (progressive profile)
**What:** T7 — trim PROFILE.md (remove Experience + Additional Evidence) after real pipeline test with DB evidence; T9 — onboarding interview flow (LLM-driven).
**Spec:** [Epics/EPIC-24-progressive-profile.md](Epics/EPIC-24-progressive-profile.md)

### Activity: surface claude_cli token estimates + parse real CLI usage (added 2026-07-14)
**Story:** As a tester comparing providers, I want the Activity tab to show token/cost data for claude_cli runs (currently just "—"), so I can actually compare CLI vs API consumption.
**Findings (verified in code):** `ClaudeCodeProvider` sets `input_tokens=0/output_tokens=0/cost=0` (CLI `claude -p` returns no usage), but DOES compute + store input estimates `profile_tokens/prompt_tokens/user_tokens = len//4` in `llm_usage`. So input-side estimate exists in DB but is never shown; output is not estimated at all.
**Two parts:**
- **Part 1 — surface what we already store:** Activity LLM Calls table falls back to `profile+prompt+user_tokens` (estimated input) when `input_tokens==0`; mark it visually as estimate (e.g. `~12.3k est`). Cheap, no backend change beyond API exposing the fields.
- **Part 2 — get REAL CLI numbers:** `claude -p --output-format json` returns `usage` + `total_cost_usd` in the result JSON. `ClaudeCodeProvider._run` currently reads stream and discards it → parse the final result JSON, populate real `input_tokens/output_tokens/cost_usd`. Then CLI has exact numbers like the API path. Also estimate output (`len(text)//4`) as fallback if JSON parse fails.
**Scope:**
- [ ] `web/api.py` activity endpoint — include profile/prompt/user_tokens; flag estimate vs exact
- [ ] Flutter Activity table — show estimated input when exact==0, `~est` marker
- [ ] `ClaudeCodeProvider._run` — `--output-format json`, parse usage → real tokens/cost
- [ ] Output estimate fallback (`len//4`) when usage missing
- [ ] Tests: CLI usage parse, estimate fallback

### Flutter: pipeline phase stepper in detail card (added 2026-07-13)
**Story:** As a user, I want a strip at the top of the vacancy detail card showing which pipeline phases this vacancy has passed, so I can see at a glance whether every stage ran correctly — a clear health indicator and a strong testing aid.
**Design:** horizontal stepper of phase chips — Analysis (p1+p2) · CV (p3+p3.5) · Signal Audit (p3.6, if enabled) · Cover (p4). Each chip has a state derived from data, not guessed:
  - **done** — key present in `analysis_json` (`completed_phases()` already returns `['p1','p2',...]`)
  - **in progress** — `status` is the active one (`analyzing`/`cv_generating`/`cover_generating`) → pulse
  - **failed** — `status == 'analysis_failed'` (or cv/cover error) → red on the current phase
  - **pending** — not reached yet → muted
**Why testing value:** instantly shows "analysis ran but CV silently skipped", or a phase that failed without surfacing. Reuses existing `ProcessingWrapper` pulse + `analysis_json` keys — no new backend, no DB.
**Scope:**
- [ ] `web/api.py` — expose `completed_phases` (or derive client-side from analysis_json already in detail response)
- [ ] Flutter `_PhaseStepper` widget at top of detail card; state machine done/current/failed/pending
- [ ] Map status → active phase; red state on `*_failed`
- [ ] Tooltips per chip (phase name + fit/score if available)

### Settings: decide what the "Save" button does (added 2026-07-14)
**Problem:** Settings has a mixed save model that misled the user into thinking model changes weren't applied. `_save()` persists ONLY apiUrl / pollInterval / notifications. Provider/model/effort save **instantly** via each control's `onChanged` (patchProvider/patchModel/patchEffort) — Save does not touch them. So "pick model → Save" felt like it saved the model; it didn't (see the model-selection bug fixed 2026-07-14).
**Decision needed — pick one:**
- **(a) Save saves everything** — collect provider/model/effort into `_save()`, remove instant-apply; single explicit commit. Most intuitive, matches user expectation.
- **(b) No Save for LLM config** — drop the Save button's relevance to the AI Provider block (or move Save out); make it visually clear LLM settings apply instantly (e.g. inline "✓ applied" per control). Keep Save only for connection settings.
- **(c) Split** — "Save" only for connection block; AI Provider block shows its own instant-apply affordance.
**Recommendation:** (b) or (c) — instant-apply already works and is safer (no half-saved state); just remove the misleading Save coupling + add per-control applied feedback.
**Scope:** decide → implement chosen option; `settings_screen.dart` `_save()` + AI Provider block affordance.

### Job Monitor — Error Alerting (added 2026-07-06)
**What:** per-feed failure counter in `seen_jobs.json` → Telegram alert at 3 consecutive failures → recovery alert; `health_check.py --monitor` flag.
**Why:** monitor is first stage; silent failure kills entire pipeline — errors currently only in logs.
**Scope:**
- [ ] `services/job-monitor/monitor.py` — `_feed_health` counters, alert on threshold, reset on success
- [ ] `scripts/health_check.py` — `--monitor`: read state file, exit 1 on stale/failed feeds

### Tracker: editable salary — remaining wiring
**What:** API (`PATCH /salary`) + Flutter `SalaryDisplay` done. Remaining: `tracker.html` inline click-to-edit field; auto-fill `p2.salary` → `vacancies.salary` at Phase 2 completion (`tools/cv_analyze.py`).

---

## 🟡 P2

### Phase 3.6 Signal Audit: Flutter UI + Worker orchestration (added 2026-07-12, estimated 2026-07-14)
**What:** wire Phase 3.6 into CVWorker + Flutter. Today it exists ONLY in skill mode — prompt `prompts/pm/phase3_6_signal_audit.md` + SKILL.md orchestration; `p3_6` appears nowhere in `tools/core/web/flutter`. Zero backend/Flutter integration.
**Design:** CVWorker runs Phase 3.6 after CV save → stores findings in `analysis_json.p3_6` (`status: clean|issues`, `findings[]` with `remove|weak` verdicts) → no auto-fix without user confirmation. Flutter `_SignalAuditCard` in CV tab: ✅ clean chip or expandable findings + "Apply fixes".
**Estimate: ~2–2.5 days total, split into 2 milestones.**

**M1 — Audit read-only (visibility) · ~1–1.5 days (6–10h) · low risk.** Delivers 80% of value: user *sees* "CV clean / 3 noise sentences" — the testing/quality indicator. No auto-edit. Consider pulling M1 to P1 as a testing tool.
- [ ] `generic` prompt (copy of `pm` — logic is universal) — trivial
- [ ] `p3_6` schema in `contracts/pipeline.py` + parse findings from markdown output (like `key_barriers` parsing)
- [ ] CVWorker: after CV save → read EXPERIENCE + Signal Coverage Table → LLM call 3.6 → store `p3_6` (+1 LLM call in pipeline: latency/tokens)
- [ ] API: expose `p3_6` in analysis response
- [ ] Flutter `_SignalAuditCard` (clean chip / expandable findings, display only)

**M2 — Apply fixes (auto-edit) · ~0.5–1 day (4–6h) · ⚠️ medium risk.** Do after M1 is proven and the real findings format is seen.
- [ ] `POST /api/vacancies/{id}/apply-audit-fixes` — **LLM-driven removal** (send CV + 🗑️ list → model returns cleaned CV whole), NOT regex/string-match: LLM excerpt won't match file text exactly (punctuation/line-wraps) → fragile. Costs one more LLM call but reliable.
- [ ] Re-save CV.md + re-render PDF; `vacancy_track.py update-json --phase p3_6`
- [ ] Flutter: "Apply fixes" button + `VacancyRepository.applyAuditFixes()`
- [ ] Tests: removal keeps non-🗑️ sentences intact (guard against over-deletion)

### `analyzed_at` — точный timestamp успешного анализа
**What:** `updated_at` меняется при любом статусе (включая failed) → чип "Analyzed" врёт при retry-failed. Отдельная колонка `analyzed_at`, пишется только при переходе в `analyzed`.
**Scope:** schema + migration; `cv_analyze.py` write; API response; Flutter `_AnalyzedChip` reads `analyzedAt`.

### Queue journal / log panel (Flutter)
**What:** visible panel listing all queued vacancies + statuses when anything enters the analysis queue. Useful for future batch mode.

### Docs & diagrams freshness review (post-EPIC-21 — now triggered)
**What:** EPIC-21 closed 2026-07-12 → audit docs vs implemented FSM: `docs/diagrams/EPIC-21-pipeline-fsm.html`, `ARCHITECTURE.md` (pipeline/mode tables), `CLAUDE.md` status line, `docs/local-app.md`, `docs/system-flow.md`, `README.md`, `docs/discovery/Pipeline-Evolution.md` (add Phase 3 entry).

### Worker-Critic Pipeline (experiment)
**What:** adversarial Worker→Critic→revision loop per phase; generalizes Phase 3.5. Experiment first: same vacancy with critic on/off, compare quality vs +50–100% cost.
**Spec:** [../discovery/worker-critic-pipeline.md](../discovery/worker-critic-pipeline.md)

### Annotated CV Revision
**What:** select block in CV/Cover preview → annotate → targeted LLM revision without full Phase 3 re-run.
**Spec:** [../discovery/annotated-cv-revision.md](../discovery/annotated-cv-revision.md)

### Tech debt
- [ ] **VScore → VacScore rename** — везде: prompts, SKILL.md, web/reader.py, tracker.html, Flutter
- [ ] **RSSWatcher → BackgroundWorker rename** — `core/rss_watcher.py` → `core/background_worker.py`; misleading name (added 2026-07-06)

### Docs — Mirror 2026-07-12 prompt changes to generic/ + CLAUDE.md bump
**What:** changes landed in `prompts/pm/` only. Mirror to `prompts/generic/`: phase1 JD Language detection (§1.0 + header field), phase2 Signal Coverage Table, phase3 Rule 24, create `phase3_6_signal_audit.md`. CLAUDE.md: 1.19 → 1.20 + status.

---

## 🐛 Bugs

### job-monitor: Djinni RSS feed returning empty/invalid XML intermittently (found 2026-07-16, watch-only)
**Symptom:** `services/job-monitor/monitor.py`'s `check_feed()` fails with `xml.etree.ElementTree.ParseError: no element found: line 1, column 0` — all 4 Djinni feeds fail together in the same poll cycle, several times over ~20 min (18:30, 18:31, 18:36, 18:49). DOU feeds unaffected. 207 total "fetch failed" lines in `logs/monitor.log` history (broader pattern, includes an unrelated DNS blip on 07-14).
**Likely cause:** today's heavy djinni.co traffic from the 264-row fetching cleanup (258 re-fetches + diagnostic requests, all from this machine) may have triggered a temporary rate-limit/bot-block on djinni's RSS endpoint specifically — individual job pages (via `services/parser`) fetched fine all day, only the RSS feed listing endpoint is affected.
**Severity — lower than it looks:** unlike the RSSWatcher fetch-cap bug, `check_feed()` does NOT accumulate stuck state — on failure it just logs and returns 0 new jobs for that cycle; the next 5-min poll starts clean. Worst case = a blind window where fresh postings are missed until the next successful cycle (self-healing, not a pile-up).
**Action:** watch, no fix attempted yet — if it persists past today (i.e. isn't just today's self-inflicted rate-limit clearing), revisit: add a retry/backoff in `fetch_jobs()`, or a User-Agent/request-pacing review for the Djinni RSS endpoint specifically.

### ~~RSSWatcher retries forever on unparseable pages — no retry cap~~ — ✅ Fixed 2026-07-16
**Found via:** fresh RSS vacancy `https://djinni.co/jobs/837755-product-marketing-manager` (#703) — parser fetches real HTML (title extracts fine) but `.job-post__description` isn't present AND the `<body>` fallback also yields empty markdown → `503 parse_failed`, retrying every poll cycle forever. Same root shape as the 264-row `fetching` pile-up cleaned up hours earlier, different trigger (site template variance, not a broken parser process) — confirms this is a recurring failure class, not a one-off.
**Urgency:** each retry cycle was ALSO re-sending the "🆕 Новая вакансия" Telegram notification (push to phone + desktop) every ~30s — a second, more immediately annoying bug caused by the same unconditional-retry design.
**Fix:**
- `vacancies.fetch_attempts` column (migration in `db/database.py`); `increment_fetch_attempts()` / `give_up_fetch()` helpers.
- `core.rss_watcher.MAX_FETCH_ATTEMPTS = 5` — past the cap, `give_up_fetch()` sets `status='declined'` + records the reason in `analysis_error`, sends one final `❌` Telegram message, and stops retrying (Archive stage, matches "Inbox Zero" — an unparseable page isn't worth indefinite retries).
- `_notified_urls` dedup set — the "🆕 Новая вакансия" notify now fires once per URL, not once per poll cycle a stuck URL happens to still be `queued`.
- 5 new tests (2 DB-level, 3 `RSSWatcher._process`-level) + fixed 2 pre-existing tests whose assertions encoded the old (buggy) re-notify-every-retry behavior. 758 total.
- **Needs `agent.py` restart** to pick up the fix — the running process still has the old unconditional-retry code until restarted.

**Broader design question — not resolved, needs its own pass:** the user reframed this as "not a bug, an exception class — how do we want to handle these going forward." Currently a gave-up vacancy lands in `declined`/Archive, visually indistinguishable from a vacancy the user actively skipped — the `analysis_error` reason is stored but not surfaced anywhere in Flutter for declined items. Open questions for a future design session:
- Should "system gave up after N fetch attempts" be visually distinct from "user skipped" (e.g. a small ⚠️ badge in Archive, or a separate implicit sub-filter)?
- Should there be a manual "force retry" action for gave-up vacancies (distinct from the existing Reset & Retry, which assumes a JD already exists)?
- Does this same retry-cap-and-classify pattern need to apply to OTHER exception classes in the pipeline (LLM timeouts, PDF render failures, etc.), or is fetch-stage the only place unbounded retry is possible?

### Fetch crashes on empty/malformed company name in folder path (found 2026-07-16)
**Repro:** JD's parsed company field is empty (DOU shows "вакансія неактивна" instead of company for closed listings) or ends in a stray separator char (djinni.co listing parsed as `"...в Tailored Tech –"`) → the `{id} — {role} — {company}` folder name ends in a trailing `"— "`/dash → Windows rejects the path when writing `JD.md` → `[Errno 2] No such file or directory`.
**Impact:** `RSSWatcher` retries forever on the exact same doomed write (fetch "succeeds" at the parser level, only the file-write step fails) — looks identical to a dead-URL retry loop from the logs, easy to misdiagnose (did, initially, during 2026-07-16's cleanup — turned out 2 of 264 stuck rows were this, not the html2text parser bug that explained the rest).
**Fix:** folder-name construction (`tools/cv_fetch_jd.py` and/or `services/parser`) needs to strip trailing separator characters when company is empty/malformed, or fall back to a placeholder (e.g. `"— Unknown Company"`) instead of leaving a dangling `"— "`.
**Found via:** 2 real vacancies during the 264-row fetching cleanup (`#252`, `#593`) — deleted as a workaround, root cause not fixed.

### DB data cleanup — NULL published_at + legacy statuses (found 2026-07-13)
**Context:** 196/578 rows (34%) have `published_at=NULL` (rows created before EPIC-26). Two independent problems, both worth fixing.
**Part 1 — backfill dates: ✅ Done 2026-07-16.** Recount before executing found only 45 candidates left (not the original 94 — Part 4's orphan-delete and Part 3's status resets already removed/reclassified most of them): `analyzed`(20) + `fetched`(23) + `cv_generated`(1) + `cover_generated`(1). `UPDATE vacancies SET published_at = created_at WHERE published_at IS NULL AND status IN (...)`. Remaining 104 NULL rows are all legacy-status (`fetching`/`new`/`done`/`queued`, Part 2 scope) + 6 `declined` — correctly out of scope, left alone.
**Part 2 — legacy statuses (344 rows, real debt):** `fetching`(264), `queued`(35), `new`(30), `done`(15) are outside the current state machine. Since the 5-stage taxonomy shipped (2026-07-16) these ARE visible again (mapped into "Inbox" by `core/vacancy_stage.py`'s legacy-status fallback) — no longer silently hidden, but still cluttering Inbox.
  - **Root cause found + fixed 2026-07-16**: `reset_stuck_statuses()` (runs at `agent.py` startup) reset `analyzing`/`cv_generating` but never `fetching` — RSSWatcher's own retry logic (`fetching`→`queued` on fetch error) only fires if the process survives to the `except` block; a hard restart mid-fetch (dev-session kill, crash) skipped it, leaving the row stuck forever. Confirmed by date correlation: every `fetching`-row spike (17.06, 20.06, 29.06–02.07) lines up with a documented heavy dev session in `docs/effort-log.md`; zero new stuck rows since 07-10 once dev activity moved off `rss_watcher.py`. Fix: `fetching`→`queued` added to `reset_stuck_statuses()` (`db/database.py`), mirroring the existing two resets. 3 new tests (753 total). **This prevents NEW accumulation — does not touch the existing 264 rows.**
  - **Existing 264 `fetching` rows: ✅ Done 2026-07-16.** Two-step plan executed live: (1) reset all 264 → `queued`, let the running RSSWatcher actually re-fetch each URL (safe now that the fix above prevents re-sticking) — 258 succeeded (real JD content retrieved), 6 genuinely failed. (2) Split by outcome, per user's "Inbox Zero" philosophy (a good inbox is a *processed* inbox — month-old un-reviewed vacancies aren't backlog, they're noise, even with real content): **6 deleted** (4 real 404s + 2 hit the folder-naming bug below — `#252` confirmed dead via DOU's own "вакансія неактивна" page banner, `#593` status unconfirmed but small enough to not special-case) — both DB rows and their empty/partial on-disk folders removed; **258 archived** — `status='declined'` AND physically moved on disk to `vacancies/inbox/{user_id}/Archive/{folder}/` (one-off script, safe because these are inert `fetched`-only rows with zero active-worker risk — NOT the general "physical folder tree" feature above, which remains unimplemented for live/in-progress vacancies). `markdown_path` updated to the new location for all 258. Verified: 0 dest collisions, 0 failed moves, 753 tests pass, live `stage` distribution confirms Inbox dropped 408→166.
  - **New bug found during this cleanup — folder-naming crash on empty/malformed company name**: when a JD's company field is empty or ends in a stray dash (`"— в Tailored Tech –"`), the vacancy folder name ends in `"— "` or similar, which Windows rejects when writing `JD.md` into it (`No such file or directory`) — `RSSWatcher` then endlessly retries the same doomed write. Not the html2text bug, a separate one. Root cause not yet fixed (folder-name sanitization in `tools/cv_fetch_jd.py`/`services/parser` needs to strip trailing separator chars when company is empty/malformed) — only worked around by deleting the 2 affected rows this round. **Needs its own ticket** if it recurs.
  - Part 1 (`published_at` backfill) was already fully done earlier this session — no remaining rows from this batch need it (all resolved to `declined` or deleted).
**Part 3 — fake "analyzed" rows: ✅ Done 2026-07-16.** Recount after Part 4's delete: 21 remaining (most of the original 64 were the Part 4 orphans, already gone). Found one genuine exception before executing — **#48** has empty `analysis_json` but REAL `*_CV.md`/`*Cover*.md` files on disk (the CLAUDE.md-documented e2e reference vacancy, 2026-06-02 — `analysis_json` persistence was added to the pipeline later than this row's CV/Cover generation) — excluded from the reset, left as `cv_generated`. Checked all other 20 for the same pattern (real docs despite empty p1) — none had it, confirmed genuinely empty. Reset: 18 → `fetched` (JD.md still exists, re-analyzable) — `[50,51,52,54-63,65-69]`; 2 → `declined` (source file gone) — `[49,53]`.
**Part 4 — `user_id IS NULL` orphaned rows (found + fixed 2026-07-16):** ✅ Done. 47 rows, all dated 2026-05-29 (day 1, pre-EPIC-13 multi-user), `markdown_path` pointing at the defunct `callback-cv`/`job-board-monitor` predecessor projects (44/47) — invisible to Flutter (queries always filter by `user_id`), zero real value. Verified no `duplicate_of` pointed at any of them before deleting (would have blocked the FK). `db/agent.db` backed up first (`db/agent.db.backup-20260716-*`). Deleted via `DELETE FROM vacancies WHERE user_id IS NULL`.
  - **NOT hardening `user_id` to `NOT NULL`** — checked first and found `ALTER TABLE vacancies ADD COLUMN user_id ... ON DELETE SET NULL` (EPIC-13, `db/database.py`) is a deliberate design: vacancies survive as orphans if their user is ever deleted, rather than cascade-deleting. A `NOT NULL` constraint would break that intentional soft-orphan behavior. The 47 deleted rows were pre-EPIC-13 import artifacts, not evidence the nullable design is wrong — leaving schema as-is.
**Part 5 — `content_hash` coverage gap: ✅ Done 2026-07-16.** Backfilled 412 rows by reading `markdown_path` (JD.md), stripping the known `# title\n\n[Source: url\n\n]---\n\n{body}` wrapper (both `cv_fetch_jd.py` and the import-jd endpoint use this separator) before hashing — falls back to whole-file hash when the separator isn't found (48 rows), harmless since sha256 can't produce a false-positive dup match, only a hash that won't match a correctly-normalized sibling. Coverage: 18% → 87% (530/607). Remaining 77 NULL are rows with no `markdown_path` yet (JD never fetched) or missing file — can't be backfilled without the source text.

---

## 🧊 Icebox (P3+)

- **Docker deploy on VM** — compose ready (5 services); WeasyPrint needs GTK → Linux container only; plan: `git pull && docker compose up --build` on VM
- **e2e full pipeline from URL** — fetch → analyze → generate → cover (`scripts/e2e_test.py`, costs tokens)
- **health_check.py → Windows Task Scheduler** — recurring monitoring
- **Pipeline Cost Preview** — token/cost estimate before full run (Telegram UI outdated — redesign for Flutter)
- **Telegram webhook mode** — config flag, currently long polling (push-only now, low value)
- **asyncio.Queue → Redis** — when concurrent users justify it
- **MCP Server** — Career Agent as tool for personal AI agents → [../discovery/mcp-server.md](../discovery/mcp-server.md)
- **Extensions** — `yt_transcribe.py`, `quote_store.py`, `email_draft.py`, job auto-submit (feasibility research first)
- **Unit Economics Dashboard** — `GET /api/economics` + Chart.js (cost/vacancy, phase breakdown, cache efficiency, spend)
- **Polish & docs** — README Mermaid diagrams, QUICKSTART.md, USER_GUIDE.md

---

## 📚 Epics overview

| Epic | Title | Status |
|------|-------|--------|
| [EPIC-13](Epics/EPIC-13-multi-user-data-model.md) | Multi-user data model | ✅ Done 2026-06-01 |
| [EPIC-14](Epics/EPIC-14-services-pdf.md) | services/pdf/ | ✅ Done 2026-06-01 |
| [EPIC-15](Epics/EPIC-15-services-parser.md) | services/parser/ | ✅ Done 2026-06-01 |
| [EPIC-16](Epics/EPIC-16-services-job-monitor.md) | services/job-monitor/ | ✅ Done 2026-06-01 |
| [EPIC-17](Epics/EPIC-17-onboarding.md) | Onboarding | ✅ Phase 1 done; Phase 2 → EPIC-24 T9 |
| [EPIC-19](Epics/EPIC-19-local-execution.md) | Local execution mode (web UI) | 📋 Planned |
| [EPIC-20](Epics/EPIC-20-vacancy-path-standard.md) | Unified vacancy path standard | 📋 Planned |
| [EPIC-21](Epics/EPIC-21-deterministic-vs-cognitive-pipeline.md) | Deterministic vs Cognitive split | ✅ Done 2026-07-12 (T5/T6 dropped) |
| [EPIC-22](Epics/EPIC-22-flutter-platform.md) | Flutter Platform (Pivot 2) | 🚧 Phase C done; Phase D remainder: polish |
| [EPIC-23](Epics/EPIC-23-claudecode-provider.md) | Claude Code CLI Provider | ✅ Done 2026-07-05 |
| [EPIC-24](Epics/EPIC-24-progressive-profile.md) | Progressive Profile | 🚧 T1–T6, T8 done; T7, T9 open |
| [EPIC-25](Epics/EPIC-25-auth-billing.md) | Auth, User Management & Billing | 📋 Planned (design-first) |
| [EPIC-26](Epics/EPIC-26-vacancy-dedup-republish.md) | Dedup & Re-publish Detection | ✅ Done 2026-07-09 |

Pre-pivot EPIC 1–12: [epics-archive/EPIC-01-12-pre-pivot.md](epics-archive/EPIC-01-12-pre-pivot.md)
