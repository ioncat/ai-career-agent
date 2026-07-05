# EPIC-24 — Progressive Profile: Structured DB Profile + Onboarding Interview

**Status:** 🟡 In Progress — Tasks 1–4 + A + 5–6 + 8 done; T7 pending (after Phase 3 testing); T9 planned
**Priority:** P1
**Last updated:** 2026-07-05
**Design doc:** `docs/discovery/progressive-profile.md` (gitignored — internal only)

---

## Core Idea

Career Agent should know the candidate better than the candidate's own CV does.

Every interaction — onboarding, Phase 2.5 objection handling, re-interviews — is both a pipeline run AND a profile enrichment. The profile compounds over time.

See design doc for full vision, architecture, and rationale.

---

## Problem

PROFILE.md is a LinkedIn/CV copy-paste — already filtered, already generic. Phase 3 can only surface signals that are already in context. Evidence surfaced during Phase 2.5 is currently appended as freeform text and not indexed for future pipeline runs.

---

## Goal

`users.progressive_profile` — structured JSON DB profile of the candidate's real experience:
- Roles with narrative, key_results[], framing[], caveats[], tags[]
- Populated manually first; enriched by every Phase 2.5 session
- Read by Phase 3 to find signals relevant to each specific vacancy
- Switchable via `/analyze [4]` toggle: Markdown profile | DB profile

PROFILE.md shrinks to: Settings · Name variants · Contacts · Summary · Archetype · Preferences · Gaps.

---

## User Story

```
As a candidate in active job search
I want my evidence to accumulate across every session
So that each new CV generation is stronger than the last — without starting from scratch
```

---

## Architecture Decision

**Storage: `users.progressive_profile` (SQLite)** — JSON column, same pattern as `users.profile_json`.

Not a file. Reasons: multi-user native, Flutter reads via API, Phase 2.5 write-back = atomic DB update, both pipelines (Claude Code + FastAPI) read via `database.py`.

---

## Tasks

| # | Task | Status | Depends on |
|---|------|--------|-----------|
| 1 | Design schema — Path B: narrative + key_results + framing + caveats + tags | ✅ Done 2026-07-02 | — |
| 2 | DB migration: `ALTER TABLE users ADD COLUMN progressive_profile TEXT` | ✅ Done 2026-07-02 | 1 |
| 3 | Seed HostiServer role into progressive_profile | ✅ Done 2026-07-02 | 2 |
| 4 | Seed Marketplace, InsulaLabs, SBC Distribution roles | ✅ Done 2026-07-02 | 3 |
| A | Profile source toggle `[4]` in `/analyze` Step 0 menu (Markdown \| DB) | ✅ Done 2026-07-02 | 2 |
| 5 | Phase 2.5 write-back: `scripts/profile_merge.py` + `prompts/pm/phase2_5_writeback.md` + SKILL.md call | ✅ Done 2026-07-05 | 2 |
| 6 | Phase 3 evidence reader: inject `progressive_profile` roles[] into Phase 3 user message | ✅ Done 2026-07-05 | 2, 5 |
| 7 | Trim PROFILE.md: remove Experience + Additional Evidence sections | 🟡 Pending — after T6 tested in real pipeline run | 3, 4 |
| 8 | GET /api/users/{id}/progressive_profile endpoint for Flutter | ✅ Done 2026-07-05 | 2 |
| 9 | Onboarding interview flow (LLM-driven, EPIC-17 Phase 2) | 🔴 LLM required | — |

**Tasks 1–4 + A + 5 + 6 + 8 done.** T7 pending: trim PROFILE.md after Phase 3 DB evidence tested on real pipeline. T9 backlog.

---

## Dependencies

| Dependency | Status |
|-----------|--------|
| LLM access (Claude CLI) | 🔴 BLOCKED — Tasks 7+ only |
| EPIC-22 Phase C complete | Independent — can start now |
