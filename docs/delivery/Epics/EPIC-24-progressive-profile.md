# EPIC-24 — Progressive Profile: Structured DB Profile + Onboarding Interview

**Status:** 🟡 In Progress — Tasks 1–4 + A + 5–6 + 8 done; T7 pending (after Phase 3 testing); T9 planned
**Priority:** P1
**Last updated:** 2026-07-05
**Design doc:** `docs/discovery/progressive-profile.md` (gitignored — internal only)
**Re-scope proposal (2026-10-04, draft, not applied):** `docs/discovery/profile-schema-v0-2026-10-04.md` (gitignored). One structured profile with atomic, rule-annotated facts would replace both `users.profile_json` and `users.progressive_profile`; tasks T-A to T-G are in its section 10. Decided so far (owner, 2026-10-04): one profile per person, JSON as the source of truth, Markdown only as a rendered view, work starts after the `prompt-audit-pm-2026-09-21` merge. The task table below stays as the record of what shipped until the proposal is approved.

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

---

## Status update (2026-09-21) — see BACKLOG.md "Now" for the current, authoritative status

This file is stale relative to the task table above (last updated 2026-07-05). As of 2026-09-21:
`progressive_profile`'s Phase 2.5 write-back (T5) ran unconditionally regardless of session mode,
but `PROFILE_SOURCE` defaults to `md` and every real session traced so far has run in that mode —
meaning T5 wrote to a store nothing downstream ever read back, in production, for months. Write-back
is now gated on `PROFILE_SOURCE=db` (stops the silent cost, doesn't resolve the question below).
**Open, undecided, explicitly not downgraded to icebox:** is finishing T7/T9 worth it, or has
months of exclusive PROFILE.md-markdown usage already settled this in markdown's favor? Needs a
dedicated decision session — not yet scheduled as of 2026-09-23.

**Future consideration, if EPIC-24 is picked back up (added 2026-09-23):** the North Star Signal
Tree design (`docs/discovery/north-star-signal-tree-discovery-2026-09-21.md`) proposes a
candidate-side "differentiation weight" that partly depends on PROFILE.md's own existing rarity
language — freeform notes like *"rare, edge-case signal, default omit"* vs. *"universal, baseline
evidence for ANY commercial PM/PO role"* — which the LLM currently has to notice by reading prose.
If `progressive_profile`'s structured evidence format is ever built out, that rarity/universality
marker could become an explicit structured field per evidence item instead of a phrase the model
has to find in an 800-line markdown file — more mechanically reliable. **Not a current dependency**
— the Signal Tree work proceeds against PROFILE.md prose (the only thing actually populated today)
regardless of what happens with this epic; revisit only if prose-based rarity detection turns out
to hit a real reliability ceiling.
