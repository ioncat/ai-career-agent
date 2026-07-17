# EPIC-27 — Per-Phase LLM Routing + Critical Blocker Pre-filter

**Status:** 🚧 Core implementation done (Tasks 1–15) — pre-filter ships manual-trigger-only
by design (Rollout section, Story 1); automatic wiring is a deliberate follow-up, not scoped yet.
**Priority:** P1
**Last updated:** 2026-07-17
**Design baseline:** [docs/discovery/per-phase-llm-routing.md](../../discovery/per-phase-llm-routing.md) — full architecture facts, all 6 open decisions resolved there.

**Goal:** Let each pipeline phase (pre-filter, Phase 1, 2, 3, 3.5, 4) run on an independently
chosen LLM provider/model/effort instead of one global setting — first concrete use: a cheap
local-model gate that flags obviously-disqualifying vacancies before Phase 1+2 spends real
tokens on them. Strategic framing (not just cost): local/CLI mode is today's quality reference;
API mode is the commercial target this needs to reach — per-phase routing is the lever for
closing that gap phase-by-phase, not only a cost-cutting mechanism.

---

## User Story 1 — Critical Blocker Pre-filter

```
As a job seeker
I want obviously-disqualifying vacancies flagged before I spend time reviewing them
So that I don't waste attention on vacancies I could never realistically get
```

### Acceptance Criteria

**Given** a vacancy has `JD.md` and `PROFILE.md` has a `## Critical Blockers` section
**When** the user taps "Check blockers" on the vacancy (manual trigger — see Rollout below)
**Then** it calls the pinned LLM (Ollama, per `phase_llm_config`) with the JD text + blocker criteria and records the result

**Given** the pre-filter finds one or more blockers
**When** the vacancy card is viewed in Inbox (after a manual check)
**Then** Flutter shows a visible warning badge naming the specific blocker(s) — max 2–5, scannable at a glance

**Given** the pre-filter finds no blockers
**When** it completes
**Then** the vacancy proceeds to Phase 1+2 exactly as today, no visible change

**Given** the pre-filter call fails (Ollama unreachable, timeout, unparseable output)
**When** this happens
**Then** the vacancy proceeds to Phase 1+2 as if no blockers were found (fail-open, never fail-closed) and the failure is logged, not surfaced as a false blocker

**Given** a blocker flag is shown
**When** the user reviews it
**Then** the user decides to skip or keep the vacancy — the system never auto-skips

### Edge Cases

- `PROFILE.md` has no `## Critical Blockers` section → pre-filter step is skipped entirely, vacancy proceeds normally
- Pre-filter LLM output doesn't parse into the expected format → treated as "no blockers found" (fail-open), logged as a parse warning
- Vacancy re-analyzed (already passed pre-filter once) → pre-filter does NOT re-run automatically; the manual button can be re-run any time regardless

### Out of Scope

- Auto-skip/auto-decline based on blockers — advisory only, by explicit prior decision
- Any change to Phase 2's existing Key Barriers logic
- Flutter UI to edit `## Critical Blockers` — edited directly in `PROFILE.md` like other profile sections, for now

### Rollout — ✅ Implemented 2026-07-17: manual trigger only, automatic deferred

**Decision (user, 2026-07-17):** do NOT auto-trigger the pre-filter yet. Ship a manual
"Check blockers" button first, so the `prefilter.md` prompt and `PROFILE.md`'s
`## Critical Blockers` format can be validated/tuned against real vacancies before
any automatic wiring is turned on. This also sidesteps a real gap found while
scoping automatic triggering: `POST /api/vacancies/import-jd` (manual JD paste,
`web/api.py:764`) creates vacancies through a completely different code path than
`RSSWatcher`, and would have been silently excluded from an RSS-only auto-hook.
The manual button works identically regardless of how the vacancy was created.

- `POST /api/vacancies/{id}/prefilter` (`web/api.py`) — synchronous, single call,
  returns `{vacancy_id, blocked, reasons}` directly (not queued — this is a cheap
  debugging/tuning action, not a background pipeline phase). Builds a minimal
  `SimpleNamespace`-based `ctx.deps` (`get_llm`, `skill_type`, `user_id`) rather than
  requiring a full `AgentDeps` — the endpoint has no `parser_adapter`/`cv_adapter`
  to offer and `cv_prefilter` doesn't need them. Resolves `skill_type` from the
  vacancy's owning user (more correct than `RSSWatcher`'s single startup-baked
  `skill_type`, though not fixed there — out of scope here).
  Requires `core.settings.load_settings()` to succeed (needs `ANTHROPIC_API_KEY` +
  Telegram vars) — 503 if unavailable, matching `web/api.py`'s own documented
  "standalone tracker, no LLM required" contract for every OTHER endpoint.
- Flutter: "Check blockers" button in `_JdModeView` (`vacancy_detail_screen.dart`,
  next to Skip/Analyze) → result dialog showing blocked/not-blocked + full reasons
  list, so the user can immediately judge prompt quality — not just a snackbar.
- `core/rss_watcher.py`'s automatic hook was written, then explicitly reverted the
  same session once this decision was made — see git history / CHANGELOG, not
  present in the current code. A regression test
  (`test_process_does_not_auto_trigger_prefilter`) locks in "manual-only for now"
  so a future refactor can't silently reintroduce the auto-call without a
  conscious decision.
- **Next step (not started):** once the prompt/format are validated manually,
  design the actual automatic trigger point (RSS fetch? Import-jd path too? Both?)
  as its own follow-up — not scoped further here.

### Notes for Engineering

- New prompt file: `prompts/[skill_type]/prefilter.md` — done.
- `## Critical Blockers` section format in `PROFILE.md`, same pattern as existing
  `## Vacancy Preferences` — done, template added to both users' profiles (empty by
  default — pre-filter passes everything through until real blockers are filled in).
- Storage: `vacancies.blocker_flag` (INTEGER) + `vacancies.blocker_reasons` (JSON
  TEXT) — done, additive migration.

---

## User Story 2 — Per-Phase LLM Routing + Settings UI

```
As the product owner / operator
I want to configure LLM provider, model, and thinking effort independently for each pipeline phase
So that I can run cheap/fast providers where quality doesn't matter, and experiment with closing
the quality gap between the local reference and the commercial API path, without a full-pipeline
provider switch
```

### Acceptance Criteria

**Given** no phase has an override
**When** any phase runs
**Then** it uses the existing global default (`user_settings`) exactly as today — zero behavior change for unconfigured phases

**Given** an admin sets a specific provider+model for one phase via Settings
**When** that phase's worker runs next
**Then** it uses the pinned provider+model; other phases remain unaffected

**Given** an admin picks a model not valid for the selected provider
**When** they submit
**Then** the request is rejected (422) before anything is persisted

**Given** the phase's provider changed on the backend since Settings was last loaded
**When** a stale change is submitted
**Then** the request is rejected (409) and the UI refreshes + informs the user

**Given** a phase has an override
**When** the admin clicks "Reset to default"
**Then** the override is removed and the phase falls back to the global default on the next run

**Given** a call runs on `claude_cli`
**When** its usage is recorded in `llm_usage`
**Then** cost fields are identifiable as "not tracked" via `provider='claude_cli'` — never silently summed as real $0 by any future aggregate view

### Edge Cases

- Ollama model that doesn't support thinking + effort set to non-`off` → open technical unknown (Ollama's behavior when `think` is requested on an unsupported model isn't documented) — needs empirical testing (Task list) before the UI safely exposes this combination for arbitrary Ollama models
- Unknown/typo'd phase name passed to the API → 404, not silently ignored

### Out of Scope

- Multi-tenant / per-user phase pins — global-only today; `user_id` column deferred until EPIC-25 lands
- Worker-Critic experimentation/reporting tooling itself ([worker-critic-pipeline.md](../../discovery/worker-critic-pipeline.md), separate P2 idea) — this epic only builds the *ability* to route Phase 3 vs 3.5 independently, not the critic loop
- Full `think` parameter support in `OllamaProvider` for arbitrary models — only required if a pinned phase actually needs it (the pre-filter model doesn't); implement the parameter plumbing as part of this epic, but the broader "which models support thinking" UX polish can follow later

### Notes for Engineering

- Storage: new table `phase_llm_config` (`phase` PK, `provider`, `model`, `thinking_effort`, `updated_at`) — additive, `user_settings` untouched. See design doc for full rationale (SWOT + Descartes square already worked through — no dimension favored an alternative).
- `config_store.get_config()` gains a `phase: str | None = None` parameter; `None`/unset phase = today's global behavior unchanged.
- API: `GET /api/config/phases`, `PATCH /api/config/phases/{phase}` (validation + `expected_provider` drift-guard, mirroring the existing global endpoint exactly), `DELETE /api/config/phases/{phase}` (explicit reset — not a PATCH sentinel value).
- Model list validation reuses `_get_available_models()` as-is (`web/api.py:390`) — no new fetch/cache logic.
- **Bug fix bundled in, found during design:** `_FALLBACK_MODELS["claude_cli"]` (`web/api.py:353`) is stale (old generation IDs, missing Fable). Update to current aliases. Do NOT point it at `_fetch_anthropic_models()` — verified the full Anthropic API catalog (10 entries, incl. old dated snapshots) is not the same set the CLI's own `--model` flag actually accepts (~5 current aliases). Follow-up research, not blocking: does `claude` CLI expose its own model-listing command?
- Granularity: 6 independently-routable units (`prefilter`, `phase1`, `phase2`, `phase3`, `phase3_5`, `phase4`) — requires `AgentDeps.llm` (one pre-built client per worker) to become phase-aware (e.g. `AgentDeps.get_llm(phase)`), touching `cv_analyze()` and `cv_generate()` to resolve per sub-call instead of once per worker call.
- Flutter: `phaseConfigProvider` (mirrors `remoteConfigProvider`) + `_PhaseLlmConfigTile(phase)` — parameterized clone of the existing `_AiProviderTile` (`settings_screen.dart:210`), reusing `_ProviderRow`/`_ModelDropdown`/`_EffortControl` as-is. New collapsible "Advanced: Per-Phase Routing" section in `SettingsScreen`, below the existing "AI Provider" block. Applies each field change immediately (matches existing global block's behavior, not the batched Save button used for URL/poll/notifications).
- **Related bug, not required for this epic's AC:** `supportsEffort => llmProvider != 'ollama_api'` (`config_provider.dart:28`) is a blanket-Ollama oversimplification — real thinking support is model-capability-dependent. Fix after the Ollama `think` research above lands; the conditional-render pattern doesn't need to change structurally, just the boolean logic.
- Cost-aggregation convention (`provider='claude_cli'` → exclude/footnote, never sum as $0) already cross-referenced into the [Unit Economics Dashboard](../BACKLOG.md) backlog entry — apply it there whenever that ships, no action needed in this epic beyond what's listed.

### Dependencies

- None blocking. Loosely related: EPIC-25 (Auth+Billing) is where per-user phase pins would eventually matter; not required for this epic.

---

## Design

Full architecture — execution modes, complete phase inventory (all 9 prompt files),
ASCII process flow (current + pre-filter insertion point), and the worked-through
rationale for all 6 decisions below — lives in
[docs/discovery/per-phase-llm-routing.md](../../discovery/per-phase-llm-routing.md).
Summary of what was decided:

1. **Granularity:** 6 independently-routable units, not 4 worker-paired units.
2. **Storage:** new additive `phase_llm_config` table; `user_settings` untouched.
3. **Validation/models:** reuse `_get_available_models()`; fixed a real staleness bug
   found along the way (`claude_cli` fallback list); `thinking_effort` is
   model-capability-dependent, not provider-blanket (Ollama `think` research needed).
4. **Drift-guard:** mirror the existing global `expected_provider` 409 pattern, keyed
   per phase.
5. **UI:** full 6-card Settings UI, built now (not deferred) — cheap given how much of
   the existing `_AiProviderTile` is directly reusable.
6. **`claude_cli` cost gap:** query-layer convention (exclude/footnote
   `provider='claude_cli'`), not a schema change.

---

## Tasks

| # | Task | Story |
|---|------|-------|
| 1 | `phase_llm_config` table — schema + migration (`db/schema.sql`, `db/database.py`) | 2 |
| 2 | `config_store.get_config(phase=None)` — phase-aware resolution + fallback to global default | 2 |
| 3 | `GET /api/config/phases`, `PATCH /api/config/phases/{phase}` (validation + drift-guard), `DELETE /api/config/phases/{phase}` | 2 |
| 4 | Bug fix: update stale `_FALLBACK_MODELS["claude_cli"]` to current aliases | 2 |
| 5 | `AgentDeps.get_llm(phase)` — phase-aware client resolution; update `cv_analyze()` (phase1, phase2 calls) and `cv_generate()` (phase3, phase3_5 calls) to resolve independently | 2 |
| 6 | `OllamaProvider` — add `think` parameter plumbing (bool/level → Ollama `/api/chat` payload) | 2 |
| 7 | Spike: test Ollama's actual behavior requesting `think` on a non-thinking model — resolve the open unknown before UI exposes it broadly | 2 |
| 8 | `prompts/[skill_type]/prefilter.md` — new prompt, blocker-detection task | 1 |
| 9 | `## Critical Blockers` section format in `PROFILE.md` | 1 |
| 10 | ~~Pre-filter call site in `RSSWatcher._process()`~~ → reverted; manual trigger instead: `POST /api/vacancies/{id}/prefilter` + Flutter "Check blockers" button | 1 |
| 11 | Storage for blocker flag/reason — `vacancies.blocker_flag`/`blocker_reasons` columns | 1 |
| 12 | Flutter: blocker badge in Inbox vacancy card | 1 |
| 13 | `phaseConfigProvider` (Riverpod) — `GET /api/config/phases` | 2 |
| 14 | `_PhaseLlmConfigTile(phase)` + "Advanced: Per-Phase Routing" section in `SettingsScreen` | 2 |
| 15 | Tests — DB layer, `config_store` phase resolution, API endpoints (validation + drift-guard), `RSSWatcher`/worker integration, Flutter widget tests | 1 + 2 |

Not yet estimated. Sequencing above is logical dependency order (storage → backend →
pipeline wiring → prefilter feature → UI → tests), not a time commitment.
