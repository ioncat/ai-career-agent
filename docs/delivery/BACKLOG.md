# career-agent — Backlog

> Last updated: 2026-07-23 (session 2)
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

### Prompt review pass — `prompts/pm|generic/prefilter.md` (added 2026-07-23)
**What:** the prefilter prompt has grown reactively all session (Requirements-vs-Responsibilities rule, quote-only-JD rule, output-format examples) — do a holistic pass to see what can be tightened, consolidated, or dropped, rather than just keep bolting on more rules as new failure modes surface.
**Why:** user's own instinct after finding the self-correction-leak bug (#725) — fix the parser first (done, see CHANGELOG), but the prompt itself deserves a step-back review, not just incremental patches.
**Scope:** re-read both prompt files fresh; check for redundancy between rules; check whether the growing rule count itself might be part of the instability (matches today's broader finding that `gemma4:e2b` real-world hit rate stayed flat regardless of prompt rewrites — worth checking if that pattern holds for the CURRENT prompt too). Re-test on the same batch (`batch_validate.py`-style, scratchpad) after any change.

### Validate `gemma4:e4b` as the pre-filter model (unfinished from 2026-07-17)
**What:** after fixing two real bugs (context bloat, `num_ctx`/VRAM overflow), `gemma4:e4b` hit 3/3 clean catches on vacancy #716 (~30s, 100% GPU) — the best result found that day. Investigation stopped there ("plan for tomorrow") and was never resumed — never validated on the broader real-vacancy set (#717/#718/#720/#722) or repeated beyond one vacancy.
**Why:** blocks picking a reliable local pre-filter model, which in turn blocks the automatic-trigger ticket below. Also directly relevant to any other JD-analysis-shaped task considered for a local model (e.g. the archetype/frequency analysis idea discussed 2026-07-23) — reliability here isn't proven yet, don't assume it generalizes.
**Scope:** `scripts/e2e_prefilter.py --model gemma4:e4b --effort medium` (with `num_ctx=4096`, already wired for `phase="prefilter"`), 60s cutoff / ~30s target, sequential only — run on #717/#718/#720/#722, 3× each. Also queued but untested: `phi4:14b`. Decide single-run vs OR-logic multi-run based on results.
**Spec:** [docs/discovery/prefilter-local-model-selection.md](../discovery/prefilter-local-model-selection.md) "Plan for 2026-07-18" section (gitignored, full methodology + prior results).

### Wire Critical Blocker pre-filter into an automatic trigger (added 2026-07-17)
**What:** `POST /api/vacancies/{id}/prefilter` + Flutter "Check blockers" button ship manual-trigger-only (EPIC-27, delivered 2026-07-17) — deliberate, so the prompt/`## Critical Blockers` format can be validated first. This ticket is the follow-up: decide and wire an actual automatic trigger point once that validation is done.
**Why:** manual button proves the mechanism works; automatic triggering is what actually saves the user time day-to-day (the original point of the feature).
**Scope:** needs to cover BOTH vacancy-creation paths — `RSSWatcher._process()` (RSS feed pickup) AND `POST /api/vacancies/import-jd` (manual JD paste, bypasses RSSWatcher entirely) — an RSS-only hook would silently miss imported vacancies. See [EPIC-27's Rollout section](Epics/EPIC-27-per-phase-llm-routing.md) for full context and the reverted auto-hook's exact prior location.
**Design — ✅ resolved (user, 2026-07-17):** one Settings toggle, "Auto-analyze blockers: on/off", is a master switch for BOTH logic and UI — the two modes are mutually exclusive by design, never both active:
- **ON** → pre-filter runs automatically on every vacancy, regardless of creation path (RSS or `import-jd`). The manual "Check blockers" button (vacancy detail screen) is **hidden** — showing it alongside automatic mode would be confusing (re-running raises "what does this even do now?" questions) and pointless (already covered).
- **OFF** → no automatic run anywhere. The manual button is shown; the user decides per vacancy whether to check.
No dual-availability state — the button's visibility is a direct, deterministic function of the toggle.
**Not scoped/estimated yet.**

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

### Scrape Djinni's own structured job-criteria block for pre-filter (added 2026-07-17)
**What:** Djinni job pages render a public, unauthenticated `<aside>` block with structured job-side criteria — min years experience, remote/hybrid/office format, countries considered, required language level, employment type, domain, company stage. Confirmed live (anonymous browser session, no login) on a real job page — these are the JOB's own stated thresholds, not a personalized comparison against a specific candidate account (that comparison IS login-gated and stays out of reach; not needed anyway since we already have the candidate's own attributes in PROFILE.md).
**Why:** Djinni already curates "hardest, most explicit" criteria structurally — could feed the pre-filter directly (skip/cheapen LLM reasoning for categories Djinni already classifies) or serve as a second signal to cross-check LLM output. Ties directly into the reliability problem being investigated in [EPIC-27](Epics/EPIC-27-per-phase-llm-routing.md) / `docs/discovery/prefilter-local-model-selection.md` — local-model instability (see that doc's stability findings) is exactly the gap this structured data could shrink.
**Scope (not started):** `services/parser/`'s Djinni site config needs a second selector for this `<aside>` block (separate from `.job-post__description`); `ParsedDocument` contract needs a field for structured criteria; decide how it feeds the pre-filter (hard pre-check before the LLM call, or extra context appended to the prompt).
**Priority:** low — the local-model pre-filter work itself is currently exploratory/low-priority; this is an enhancement on an unstable foundation, not urgent.

### Re-analyze UX: vacancy visually "disappears" from Analyzed folder mid-run (found 2026-07-16, vacancy #665)
**Repro:** vacancy #665 ("Senior Product Manager — MAKEUP", talentC) was `status='analyzed'`, sitting in the Analyzed folder. User triggered a re-analysis (Re-analyze button) without noting the ID first — while it ran, the vacancy was nowhere to be found: not in Analyzed, not in any other folder user checked. It reappeared once analysis completed.
**Root cause (traced, not yet fixed):** re-analyze transitions status through `analysis_queued`/`analyzing` before landing back on `analyzed`. `core/vacancy_stage.py`'s `stage()` only maps `analyzed`/`analysis_failed` to the "Analyzed" folder — `analyzing`/`analysis_queued` fall through to "Inbox". So mid-re-analysis, the vacancy correctly (per current logic) moves to Inbox — but this is a new, more confusing behavior since the 5-stage taxonomy shipped (2026-07-16): previously Inbox absorbed the whole fetched→cover_generated range, so this transition was invisible (still "Inbox" before and during). Now that Analyzed/Processed are separate folders, a re-analyze is a visible, unexpected folder-jump — not tested when the taxonomy shipped.
**Needs a design decision, not just a fix:**
- (a) Accept the move-to-Inbox-during-reanalysis as correct, but make it clearly communicated in UI (e.g. a toast "Moved to Inbox — re-analyzing", or a persistent "🔄 Re-analyzing" badge visible even while it's technically in Inbox)
- (b) Keep it visually in Analyzed during a *re*-analysis specifically (distinct from a first-time analysis) — `stage()` would need to know "this already has real p1/p2 data, just re-running" vs "never analyzed" — doable (check `analysis_json` content, not just `status`) but adds complexity to what's currently a pure (status, applied) function
- (c) Something else — needs a proper think, not a quick patch
**Scope:** repeat the re-analyze scenario end-to-end (trigger on an already-analyzed vacancy, watch folder transitions live in Flutter), decide the intended UX, implement + test. Same question likely applies to re-generating CV/Cover on an already-`processed` vacancy — check if that has the same disappearing-folder issue.

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

### Design: distinguish "system gave up after N fetch attempts" from "user skipped" (found 2026-07-16)
**Context:** `RSSWatcher`'s fetch-retry cap (`MAX_FETCH_ATTEMPTS=5`, fixed 2026-07-16 — see CHANGELOG) sends a gave-up vacancy to `declined`/Archive, visually indistinguishable from a vacancy the user actively skipped. The `analysis_error` reason is stored but not surfaced anywhere in Flutter for declined items.
**Open questions:**
- Should "system gave up" be visually distinct from "user skipped" (⚠️ badge in Archive, or a sub-filter)?
- Manual "force retry" action for gave-up vacancies (distinct from Reset & Retry, which assumes a JD already exists)?
- Does this retry-cap-and-classify pattern need to apply to OTHER pipeline exception classes (LLM timeouts, PDF render failures)?

### Fetch crashes on empty/malformed company name in folder path (found 2026-07-16)
**Repro:** JD's parsed company field is empty (DOU shows "вакансія неактивна" instead of company for closed listings) or ends in a stray separator char (djinni.co listing parsed as `"...в Tailored Tech –"`) → the `{id} — {role} — {company}` folder name ends in a trailing `"— "`/dash → Windows rejects the path when writing `JD.md` → `[Errno 2] No such file or directory`.
**Impact:** `RSSWatcher` retries forever on the exact same doomed write (fetch "succeeds" at the parser level, only the file-write step fails) — looks identical to a dead-URL retry loop from the logs, easy to misdiagnose (did, initially, during 2026-07-16's cleanup — turned out 2 of 264 stuck rows were this, not the html2text parser bug that explained the rest).
**Fix:** folder-name construction (`tools/cv_fetch_jd.py` and/or `services/parser`) needs to strip trailing separator characters when company is empty/malformed, or fall back to a placeholder (e.g. `"— Unknown Company"`) instead of leaving a dangling `"— "`.
**Found via:** 2 real vacancies during the 264-row fetching cleanup (`#252`, `#593`) — deleted as a workaround, root cause not fixed.

---

## 🧊 Icebox (P3+)

- **Research: does Ollama's `think`/`effort` parameter actually grade reasoning depth, and in which local models?** (idea, 2026-07-17, ties to [EPIC-27](Epics/EPIC-27-per-phase-llm-routing.md) / `docs/discovery/prefilter-local-model-selection.md`) — found while debugging the Critical Blocker pre-filter: a direct `think=low` vs `think=high` comparison on `gemma4:e2b` showed no measurable difference in reasoning length/depth (<1%), while `think=off` vs any `think=<level>` clearly does matter (on/off, not graduated). Working theory: Ollama's `think` API param is a generic slot — some architectures (gpt-oss, some Qwen3 variants) use the string value to modulate depth, but Gemma 4's `ollama show` capability listing is a plain boolean (`thinking`, no levels), so the level is likely ignored. Not confirmed against source, just one comparison + the model card. Two separate questions worth a real answer someday: (1) does the `think` level string do ANYTHING model-observable for architectures that don't advertise graduated support, or is it silently ignored; (2) which of our locally-available models (qwen3:8b, phi4:14b, etc.) genuinely support graduated effort vs boolean-only. Not blocking — current pre-filter work treats `effort=medium` as just "thinking on" and moves forward on that basis.
- **job-monitor: `seen_jobs.json` → own SQLite file** (idea, 2026-07-16) — dedup source of truth is already `vacancies.url` UNIQUE in career-agent's DB (`/api/new-vacancy` returns 409 on dup); `seen_jobs.json`'s real job is just avoiding redundant webhook POSTs + delivery-retry/backoff bookkeeping. Not urgent at current load (722 entries, 5-min poll) — the `--debug`-mutation bug found today was a logic bug, not a storage-format bug, and would've happened in SQLite too. If revisited: own SQLite file (NOT shared `agent.db` — job-monitor is deliberately decoupled from career-agent internals, no aiosqlite/sync-sqlite3 cross-process contention), gets atomic writes + queryability for free. Explicitly deferred — not a bug, just a "someday, if the JSON file starts actually hurting" cleanup.
- **Docker deploy on VM** — compose ready (5 services); WeasyPrint needs GTK → Linux container only; plan: `git pull && docker compose up --build` on VM
- **e2e full pipeline from URL** — fetch → analyze → generate → cover (`scripts/e2e_test.py`, costs tokens)
- **health_check.py → Windows Task Scheduler** — recurring monitoring
- **Pipeline Cost Preview** — token/cost estimate before full run (Telegram UI outdated — redesign for Flutter)
- **Telegram webhook mode** — config flag, currently long polling (push-only now, low value)
- **asyncio.Queue → Redis** — when concurrent users justify it
- **MCP Server** — Career Agent as tool for personal AI agents → [../discovery/mcp-server.md](../discovery/mcp-server.md)
- **Extensions** — `yt_transcribe.py`, `quote_store.py`, `email_draft.py`, job auto-submit (feasibility research first)
- **Unit Economics Dashboard** — `GET /api/economics` + Chart.js (cost/vacancy, phase breakdown, cache efficiency, spend). ⚠️ Before aggregating `cost_usd`/`input_tokens`/`output_tokens`: `claude_cli` rows store these as literal `0` (not NULL, no real data — `core/llm_client.py:704-719`), indistinguishable from genuinely-free. Exclude/footnote `WHERE provider='claude_cli'` explicitly instead of summing — see [per-phase-llm-routing.md](../discovery/per-phase-llm-routing.md).
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
| [EPIC-27](Epics/EPIC-27-per-phase-llm-routing.md) | Per-Phase LLM Routing + Blocker Pre-filter | 🚧 Core done 2026-07-17; auto-trigger deferred |

Pre-pivot EPIC 1–12: [epics-archive/EPIC-01-12-pre-pivot.md](epics-archive/EPIC-01-12-pre-pivot.md)
