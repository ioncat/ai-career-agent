# Progressive Profile — Architecture & Vision

**Status:** Design doc — P1 backlog (EPIC-24)
**Last updated:** 2026-07-02

---

## The Problem

The current profile is a LinkedIn export or a generic CV copy-paste.

This is the candidate's **already-filtered self-presentation** — what they chose to show, in the format they thought worked, optimized for general impression. It is NOT the raw material of their actual experience.

**What's lost:**

- Deep role-specific context (HostiServer = "platform + operational" on LinkedIn, but under the surface: wrote all website copy, ran PPC, did JTBD segmentation, managed billing support department, ran enterprise pre-sales)
- Evidence that surfaces only under pressure (Phase 2.5 → user recalls specific cases they would never think to include in a CV)
- Framing nuance that generic CV cannot capture (co-founder contribution vs delivery contribution vs discovery contribution — depends entirely on the vacancy context)

**The result:** Phase 3 can only surface signals that are already in the context. Hidden experience = invisible to the pipeline. Every "we can't find strong evidence for X" is a false negative — the evidence exists, but was never captured.

---

## The Vision

**Progressive Profile** — a knowledge base about the candidate that grows with every pipeline interaction.

The profile is never "filled in" once and used forever. It is a **living accumulator**:

```
Onboarding interview
  ↓ initial signals extracted
Phase 2.5 — Objection Handling
  ↓ vacancy-specific evidence surfaces (the richest signal source)
Re-interviews, Q&A sessions
  ↓ gaps filled, framing sharpened
Evidence Bank
  ↑ used by Phase 3 for each new vacancy
```

Every session the user has with Career Agent makes future CVs stronger. The system compounds.

---

## Why This Matters Architecturally

Phase 2.5 (Objection Handling) is where the most valuable signal appears — but only under the right conditions:

> A specific vacancy creates a specific pressure: "Employer needs X. Do you have X?" The candidate then recalls a case they would never have written down unprompted.

That recalled case:
- is factual (pressure-tested, not generic self-description)
- is framed for a real use case (already contextualized)
- would be forgotten after the session if not captured

Currently: evidence from Phase 2.5 goes into `## Additional Evidence` sections appended to PROFILE.md — unstructured, unindexed, growing without organization.

**The fix is not "better formatting" — it's a different data model.**

---

## Architecture

### evidence.json — The Accumulator

`skill/users/[id]/evidence.json`

Single JSON file. Machine-readable. One entry per role. Each role has:
- `signals{}` — capability signals, organized by domain (discovery, delivery, metrics, stakeholders, etc.)
- `metrics{}` — hard numbers, measurable outcomes
- `framing{}` — what to emphasize for Founder Proxy vs Executor archetype
- `caveats[]` — what NOT to fabricate or overstate
- `phase25_evidence[]` — evidence surfaced during objection handling sessions (dated, with vacancy context)

PROFILE.md shrinks to:
- Settings (language, skill_type)
- Name variants + Contacts
- Summary (narrative, rarely changes)
- Archetype & Role Positioning
- Vacancy Preferences
- Honest Gaps

### Signal Sources (inputs to evidence.json)

| Source | Mechanism | Signal type |
|--------|-----------|-------------|
| CV/LinkedIn upload | Onboarding — Phase 0 | Baseline (surface) |
| Onboarding interview | Structured Q&A per role | Deep role narrative |
| Phase 2.5 sessions | Vacancy-driven objection handling | Contextualized, pressure-tested |
| User corrections | Manual updates | Ground truth |

### How Pipeline Uses It

- **Phase 1+2**: reads `evidence.json` for domain signals + VScore computation
- **Phase 3 (CV draft)**: reads role-specific sections + `phase25_evidence` for the current vacancy's gap areas
- **Phase 3.5 (self-review)**: cross-checks claims against `caveats[]`
- **Future**: profile quality score — tells user which roles have thin evidence coverage

---

## What Changes in the Pipeline

**Today:**
```
PROFILE.md (flat, generic) → Phase 1+2 → Phase 3 → CV
```

**After Progressive Profile:**
```
PROFILE.md (identity + framing only)
evidence.json (accumulated, structured experience)
  ↓
Phase 1+2 → identifies gaps → targets evidence.json sections
Phase 3 → pulls relevant signals + phase25_evidence for this vacancy
```

Phase 2.5 adds to `evidence.json` in real time. Next run for a similar vacancy: the evidence is already there.

---

## Implementation Plan

### Step 1 — Schema + first entry (no LLM required)

Design `evidence.json` schema. Manually populate HostiServer role (richest, most underrepresented in current CV). This immediately improves Phase 3 output without any code changes — just richer context.

### Step 2 — Phase 2.5 write-back

After each objection-handling session, new evidence is written to `evidence.json` (currently appended to PROFILE.md as freeform text). Structured insert, not text append.

### Step 3 — Phase 3 evidence reader

Phase 3 prompt reads targeted `evidence.json` sections based on vacancy gap areas identified in Phase 2.

### Step 4 — Onboarding interview

New user flow: structured interview per role → populates `evidence.json` → replaces manual profile editing.

---

## This Is Not a JSON Schema Task

The JSON is the implementation detail. The idea is:

**Career Agent should know the candidate better than the candidate's own CV does.**

Every interaction is both a pipeline run AND a profile enrichment. The two are inseparable. The system gets smarter about each candidate over time — which is what makes it a counselor, not a CV generator.
