# EPIC-24 — Progressive Profile: Evidence Bank + Onboarding Interview

**Status:** 🟠 P1 Backlog — not started
**Priority:** P1
**Last updated:** 2026-07-02
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

`evidence.json` — a single structured JSON accumulator of the candidate's real experience:
- Populated via onboarding interview
- Enriched by every Phase 2.5 session
- Read by Phase 3 to find signals relevant to each specific vacancy

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
| 1 | Design evidence JSON schema — Path B: narrative + tags (not typed signal domains) | ✅ Done 2026-07-02 | — |
| 2 | DB migration: `ALTER TABLE users ADD COLUMN progressive_profile TEXT` + seed empty `{}` | 🟠 | 1 |
| 3 | Manual onboarding session: HostiServer → populate progressive_profile via `vacancy_track.py` or direct DB | 🟠 | 2 |
| 4 | Manual onboarding sessions: Marketplace, InsulaLabs, SBC Distribution | 🟡 | 3 |
| 5 | Phase 2.5 write-back: MERGE new signals into narrative/key_results/framing (replaces PROFILE.md append) | 🟡 | 2 |
| 6 | Phase 3 evidence reader: load targeted roles[] sections based on vacancy gap areas | 🟡 | 2, 5 |
| 7 | Trim PROFILE.md: remove Experience + Additional Evidence sections | 🟡 | 3, 4 |
| 8 | GET /api/users/{id}/evidence endpoint for Flutter | 🟡 | 2 |
| 9 | Onboarding interview flow (LLM-driven, EPIC-17 Phase 2) | 🔴 LLM required | — |

**Tasks 1–4** require no LLM, no code changes (except migration). Start here.

---

## Dependencies

| Dependency | Status |
|-----------|--------|
| LLM access (Claude CLI) | 🔴 BLOCKED — Tasks 7+ only |
| EPIC-22 Phase C complete | Independent — can start now |
