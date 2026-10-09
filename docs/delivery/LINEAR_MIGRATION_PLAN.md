# BACKLOG → Linear: migration plan (draft for the owner)

> Temporary file: delete it when the migration is done. Nothing below has been created in Linear yet. Edit any cell (or tell the dispatcher) before the go.
> **Mapping:** BACKLOG heading P0 → Urgent (1), P1 → High (2), P2 → Medium (3), P3 and Icebox → Low (4). Status: `Backlog` unless the entry is being worked on. Project: AI Career Agent. Entry text goes into the issue description (cleaned to what is still open) with a "from BACKLOG line N" note; the entry is deleted from BACKLOG in the same step.
> **Column "Mark":** `owner` = gets the `needs-owner` label (waits for your decision); `check` = my suggestion to review the priority, the mapping is mechanical; `drop` = do not migrate (reason in the note).

| # | BACKLOG entry (line) | Issue title | Priority | Labels | Mark | Note |
|---|---|---|---|---|---|---|
| 1 | Profile ↔ prompt isolation (16) | Profile and prompt isolation: remaining work | High | prompts, multiuser | | Leak cleanup and lint tests are done; migrate only the open part |
| 2 | User-configurable personal rules (23) | User-configurable personal rules, separate from the profile | Medium | prompts, multiuser | | Not started |
| 3 | Follow-ups from the 2026-10-04 validation runs (31) | Open follow-ups from the validation runs (small defects, owner decisions) | Medium | prompts, docs | owner | Several small items, split later if needed |
| 4 | Functional specification (44) | Functional specification: "how it works" document | Medium | docs | | New home: `docs/reference/` |
| 5 | Auto-tags unreliable (50) | Auto-tags: contradictory tags keep appearing | Medium | backend, Bug | owner | Needs a design discussion |
| 6 | Dedup rework, remaining (53) | Dedup rework (EPIC-26): remaining | Medium | backend | | |
| 7 | Role Balance determinism (58) | Role Balance: is the mechanism deterministic enough | Medium | prompts, backend | owner | Decision needed |
| 8 | EPIC-24 keep or deprecate (64) | EPIC-24 progressive_profile: keep investing or deprecate | High | backend | owner | Needs a dedicated decision session; Roadmap step 5 |
| 9 | Prompt clarity/structure pass (70) | Prompt clarity and structure pass | High | prompts | | You flagged it as top priority; Roadmap step 7 |
| 10 | Audit CLAUDE.md (88) | CLAUDE.md: section-by-section audit (remainder) | Medium | docs | check | Status line already trimmed 2026-10-08 |
| 11 | Duplicate of processed vacancy (98) | Duplicate of an already-processed vacancy: cheap requirements check and salary backfill | Medium | backend | | |
| 12 | Flutter Analytics trends (103) | Flutter Analytics: personal market-research trend view | Low | flutter | | Groundwork exists |
| 13 | Background Activity Indicator (110) | Background activity indicator (discovery only) | Low | flutter | | |
| 14 | Body-scan seniority and business travel (113) | Critical blockers: body scan for seniority and mandatory business travel | Medium | backend | | |
| 15 | Systemic: CV audit optimises JD-matching (118) | CV self-review does not check ground truth: four failure classes | High | prompts | owner | Roadmap steps 2 and 6; structural fix needs a design |
| 16 | Phase 3 fabricates experience (128) | Phase 3 CV draft fabricates experience from JD vocabulary (#844) | Urgent | prompts | check | Marked MAX PRIORITY in July; confirm it is still the top item |
| 17 | End-to-end CLI acceptance test (149) | End-to-end CLI acceptance test on real vacancies | Medium | backend | | Roadmap step 1 |
| 18 | `published_at` is the ingestion time (159) | `published_at` is the ingestion time for manual vacancies | High | backend | check | P0 heading, but the chip is fixed; open part is real platform-date scraping |
| 19 | Cross-role lexical bleed (174) | Phase 3: phrasing leaks from one role to another | Urgent | prompts | | Same root as the building-blocks item (#23) |
| 20 | Competitive landscape analysis (182) | Competitive landscape analysis (overdue since 2026-05-31) | High | docs | check | P0 heading; it is research, consider Medium |
| 21 | Source badge for other boards (192) | Source badge wrong for boards outside Djinni/DOU/LinkedIn | High | flutter, backend | | |
| 22 | Manually added documents not reconciled (203) | Reconcile manually added documents in a vacancy folder into the DB | High | backend | | Point 1 (card refresh) is delivered |
| 23 | Per-archetype building blocks (211) | Per-archetype building blocks instead of free-form Phase 3 | High | prompts | owner | Needs a design pass |
| 24 | Prefilter prompt review pass (220) | Prefilter prompt: holistic review pass | High | prompts | | |
| 25 | Validate gemma4:e4b as pre-filter model (225) | Validate gemma4:e4b as the pre-filter model | High | backend | | Blocks item #26 |
| 26 | Automatic trigger of the pre-filter (231) | Wire the critical-blocker pre-filter into an automatic trigger (Stage 2) | High | backend | | |
| 27 | Physical folder tree mirrors stage (243) | Physical folder tree mirrors the vacancy stage | High | backend | check | Expensive; consider Medium |
| 28 | Settings: auto-refresh models (259) | Settings: auto-refresh the model list on provider switch | High | backend, flutter | check | Manual Refresh exists; duplicate fixed on 2026-10-09 |
| 29 | Dual client architecture note (277) | Architecture: Flutter as user and admin client (decide in EPIC-25) | Low | docs | check | A note, not a task; decision belongs to EPIC-25 |
| 30 | Mass Action queue badge (282) | Mass Action: queue position badge | High | flutter | | |
| 31 | LLM Quality Parity (287) | LLM quality parity: SKILL.md rules into the API system prompt | High | prompts, backend | | Roadmap step 2 |
| 32 | Phase 2.5 in Flutter (297) | Phase 2.5 objection handling in Flutter | High | flutter, backend | | Roadmap step 3 |
| 33 | Activity: real CLI usage (307) | Activity: parse real claude -p usage and estimate output tokens (part 2) | Medium | backend | check | Part 1 delivered |
| 34 | Pipeline phase stepper (320) | Flutter: pipeline phase stepper in the detail card | High | flutter | | |
| 35 | Editable salary, remaining wiring (334) | Tracker: editable salary, remaining wiring | High | backend, flutter | check | `tracker.html` is secondary |
| 36 | Surface JD analysis in Flutter (341) | Flutter: show the full JD analysis in the detail view | High | flutter | | |
| 37 | Editorial Audit into the app (348) | Editorial Audit (3.8): connect it to the app as an optional step | Medium | prompts, backend, flutter | owner | Your decision 2026-10-09: later, form open; Roadmap step 3 |
| 38 | Notifications phase 8 (352) | Notifications phase 8: reference document and its drift test | Medium | notifications, docs | | |
| 39 | Input limits before POST /api/events (356) | — | — | — | drop | Already VBA-9 |
| 40 | Djinni company profile for old rows (360) | Djinni company profile for old rows: re-fetch or slow backfill | Medium | backend | | DB write, needs backup |
| 41 | ~77 old rows with JD text in `company` (365) | Old-import rows have JD text in the company field | Medium | backend | | DB write, needs backup; merge with #43 when started |
| 42 | Backlog structure simplification (370) | — | — | — | drop | Replaced by Linear |
| 43 | Garbled `company` on 188 Djinni rows (376) | Garbled company on 188 pre-existing Djinni vacancies | Medium | backend | | See #41 |
| 44 | Djinni criteria block for pre-filter (381) | Scrape Djinni's structured criteria block for the pre-filter | Medium | backend | | Related to VBA-10 (same missing block) |
| 45 | Phase 3.6 Signal Audit in Flutter (387) | Phase 3.6 Signal Audit: Flutter UI and worker orchestration | Medium | flutter, backend | | Roadmap step 3 |
| 46 | Queue journal panel (405) | Flutter: queue journal panel | Medium | flutter | | |
| 47 | Docs and diagrams freshness (408) | Docs and diagrams freshness review | Medium | docs | | |
| 48 | Worker-Critic pipeline (411) | Worker-Critic pipeline experiment | Low | prompts | | Spec exists |
| 49 | Annotated CV revision (415) | Annotated CV revision | Medium | flutter, prompts | check | Roadmap step 4, waits for your dialogue-option choice |
| 50 | Tech debt: VScore → VacScore rename | Rename VScore to VacScore everywhere | Low | backend, flutter, prompts | | Noisy change |
| 51 | Tech debt: RSSWatcher → BackgroundWorker | Rename RSSWatcher to BackgroundWorker | Low | backend | | |
| 52 | Bug: text selection (425) | Text selection across paragraphs does not work in the detail view | Low | flutter, Bug | | You deprioritised it |
| 53 | Bug: cv_metrics checks Latin-only (430) | Cyrillic support for the other cv_metrics checks | Medium | backend, Bug | | |
| 54 | Check past CVs for "SaaS platform" (435) | — | — | — | drop | Spot-check of old CVs; low value, say if you want it kept |
| 55 | job-monitor Djinni RSS empty XML (439) | job-monitor: Djinni RSS feed returns empty XML intermittently | Low | backend, Bug | | Watch-only; the new alert will catch it |
| 56 | Dedup misses cross-site republish (445) | Dedup misses the same vacancy on different source sites | Medium | backend, Bug | | |
| 57 | PDF bullet extraction (451) | PDF bullet marker separated from text in extraction | Low | backend, Bug | check | Entry says "not a bug" for the encoding part; keep only if you still see the problem |
| 58 | Icebox: keyboard scroll in Detail (462) | Keyboard Up/Down scroll for the Detail panel | Low | flutter | | |
| 59 | Icebox: extend regex pre-filter (465) | Extend the deterministic pre-filter to content-stage blockers | Low | backend | | |
| 60 | Icebox: Ollama think/effort research (466) | Research: does Ollama think/effort grade reasoning depth | Low | backend | | |
| 61 | Icebox: job-monitor seen_jobs → SQLite (467) | job-monitor: seen_jobs.json into its own SQLite file | Low | backend | | |
| 62 | Icebox: Docker deploy (468) | Docker deploy on a VM | Low | backend | | |
| 63 | Icebox: e2e from URL (469) | End-to-end pipeline from URL | Low | backend | | Same area as #17; merge when started |
| 64 | Icebox: health_check → Task Scheduler (470) | health_check.py in Windows Task Scheduler | Low | backend | | |
| 65 | Icebox: Pipeline cost preview (471) | Pipeline cost preview before a full run | Low | flutter, backend | | |
| 66 | Icebox: Telegram webhook (472) | Telegram webhook mode | Low | backend | | Low value |
| 67 | Icebox: asyncio.Queue → Redis (473) | asyncio.Queue to Redis | Low | backend, multiuser | | When concurrency requires |
| 68 | Icebox: MCP server (474) | MCP server: Career Agent as a tool for personal agents | Medium | backend | check | Roadmap step 10 (criterion 3); the entry says Icebox |
| 69 | Icebox: conversational refinement gap (475) | Conversational refinement gap (positioning question) | Low | docs | | Not a ticket; kept for Roadmap step 4 |
| 70 | Icebox: extensions (476) | Extensions: yt_transcribe, quote_store, email_draft, job auto-submit | Low | backend | | Feasibility research first |
| 71 | Icebox: Unit economics dashboard (477) | Unit economics dashboard | Low | backend, flutter | | |
| 72 | Icebox: placeholder in `vacancies.title` (478) | `vacancies.title` once got a placeholder company glued in | Low | backend, Bug | | Not seen since 2026-08 |
| 73 | Icebox: polish and docs (480) | Polish and docs (README diagrams, QUICKSTART, USER_GUIDE) | Low | docs | | |
| 74 | Icebox: Djinni probe retry spacing note | — | — | — | drop | A note, not a task: move into the code comment of the probe if still wanted |
| 75 | Icebox: FailureBlock widget test | — | — | — | drop | Already VBA-8 |

**Migrated in the first wave (2026-10-09):** rows 8, 9, 17, 23, 31, 32, 37, 38, 45, 49 and 68 = VBA-18, VBA-20, VBA-12, VBA-19, VBA-13, VBA-14, VBA-15, VBA-22, VBA-16, VBA-17, VBA-21; their entries are deleted from BACKLOG. Projects: one per Roadmap step (`01` to `11`) plus `Unified notifications`; VBA-5, 8, 9, 10, 11 moved into them.

**Count:** 75 BACKLOG entries → 68 issues to create, 5 dropped, 2 already exist (VBA-8, VBA-9; VBA-5 to VBA-7 and VBA-10 were created earlier). Owner-flagged rows: 3, 5, 7, 8, 15, 23, 37 (7 issues get `needs-owner`). Rows to review for priority: 10, 16, 18, 20, 27, 28, 29, 33, 35, 49, 57, 68.
