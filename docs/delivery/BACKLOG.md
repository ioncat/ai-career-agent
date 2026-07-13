# career-agent — Backlog

> Last updated: 2026-07-13
> Rules: [documentation-conventions.md](documentation-conventions.md) · History: [CHANGELOG.md](CHANGELOG.md) · Specs: [Epics/](Epics/)

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

### Flutter: Batch Analysis Mode (mass queue) (added 2026-07-08)
**What:** multi-select in inbox → "Analyze N" → all queued in AnalysisWorker; queue position badge per card.
**Why:** biggest daily friction — morning RSS batch drops from 10–15 clicks to 2; makes RSS auto-push feel automated.
**Scope:**
- [ ] `VacancyInboxScreen` — `_multiSelectMode` + `_selectedIds`; long-press entry
- [ ] `VacancyCard` — checkbox overlay + selected highlight
- [ ] `_BatchActionBar` — slides up, count label, Analyze button
- [ ] Queue position badge ("In queue (3rd)") — derive from `analysis_queued` count
- [ ] Tests: multi-select state, action bar visibility, repository calls

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

### Phase 3.6 Signal Audit: Flutter UI + Worker orchestration (added 2026-07-12)
**What:** wire Phase 3.6 (prompt + SKILL.md pipeline already work in local mode) into CVWorker + Flutter.
**Design:** CVWorker runs Phase 3.6 after CV save → stores findings in `analysis_json.p3_6` (`status: clean|issues`, `findings[]` with `remove|weak` verdicts) → no auto-fix without user confirmation. Flutter `_SignalAuditCard` in CV tab: ✅ clean chip or expandable findings + "Apply fixes" → `POST /api/vacancies/{id}/apply-audit-fixes` → 🗑️ sentences removed, CV+PDF re-saved. No new vacancy status.
**Scope:**
- [ ] CVWorker: Phase 3.6 step after CV save; `p3_6` schema + `vacancy_track.py update-json --phase p3_6`
- [ ] `POST /api/vacancies/{id}/apply-audit-fixes` endpoint
- [ ] Flutter: `_SignalAuditCard` + `VacancyRepository.applyAuditFixes()`

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

### test_web_api.py creates real folders in vacancies/inbox/ (found 2026-07-12)
**Repro:** run `pytest` → garbage user folders `vacancies/inbox/12..16` with fake vacancy subfolders.
**Cause:** test DB is ephemeral, but `VACANCIES_PATH` points at the real project dir → endpoint folder creation lands on disk.
**Fix:** monkeypatch vacancies dir to `tmp_path` in test fixtures. Check same pattern in `test_cv_analyze.py`, `test_cv_fetch_jd.py`.

### DB data cleanup — NULL published_at + legacy statuses (found 2026-07-13)
**Context:** 196/578 rows (34%) have `published_at=NULL` (rows created before EPIC-26). Two independent problems, both worth fixing.
**Part 1 — backfill dates (94 inbox-visible rows):** `analyzed`(80) + `fetched`(7) + `cover_generated`(5) + `cv_generated`(2) sit at the bottom of the date-sorted inbox ordered by `id` (random by date). Backfill `published_at = created_at` → they take their real chronological position. Low urgency (main "newest on top" flow already works — new rows have dates), helps only "find a vacancy I analyzed N days ago".
  - Fix: `UPDATE vacancies SET published_at = created_at WHERE published_at IS NULL AND status IN ('analyzed','fetched','cv_generated','cover_generated','analysis_failed')`
**Part 2 — legacy statuses (98 rows, real debt):** `fetching`(47, stuck — process never finished), `new`(30), `done`(13), `queued`(8) are outside the current state machine → invisible in Flutter inbox (`_folderMatch` filters them) but pollute the DB and skew any status analytics.
  - Investigate: are `fetching`(47) recoverable (re-fetch) or dead? Map legacy → current statuses (`done`→`analyzed`?, `new`→`fetched`?) or purge.
  - Then backfill their `published_at` too, or delete if dead.

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
