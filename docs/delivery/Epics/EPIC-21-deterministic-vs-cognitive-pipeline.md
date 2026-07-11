# EPIC-21 — Deterministic vs Cognitive pipeline split

**Status:** 🚧 In Progress
**Priority:** P0
**Last updated:** 2026-07-11 (rev 3 — status update + three-mode clarification; see Revision log)
**Source:** `docs/discovery/hypotheses/H-002-pipeline-optimization-cognitive_vs_determined.md`

---

## Revision log

- **rev 3 (2026-07-11):** Status → In Progress. Tasks 1–2 done. Task 3 partial (VScore + rec matrix ✅; freq/tools/repetition still in prompts). Three-mode table added (CLI mode = same boundary as API). Tasks 4–6 remaining.
- **rev 2 (2026-06-15):** Re-audited against live code after VScore (06-14) and Phase 2.5 (06-05) landed. Changes:
  - Phase 2.5 Objection Handling added to classification as **interactive cognitive** (not a single structured call).
  - VScore composite formula + Fit×VScore recommendation matrix added to deterministic list (Task 3) — currently computed by the LLM by hand (arithmetic + decision table).
  - Headline "49 steps" retired — the H-002 trace is stale/atypical (excludes Phase 4, predates inbox_scan collapse, includes one-off feedback edits). Cognitive touchpoints recounted: see Target architecture.
  - PDF engine decided: **weasyprint** (HTML→PDF). Three overlapping backlog items merged into this EPIC (see Backlog consolidation).
  - Scope paths corrected (`.claude/commands/analyze.md` → skill command).
- **rev 1 (2026-06-04):** Original, from H-002.

---

## Problem

The `/analyze` → cover pipeline interleaves a handful of cognitive phases with a large amount of deterministic glue. Two waste sources:

1. **Cognitive agent executes deterministic glue.** In local mode Claude Code (a reasoning agent) hand-clicks every mechanical step. Each glue step = an agent turn (read context → decide → tool-call → parse). The expensive thinking model does work an `if` should do.
2. **LLM does work that rules/code could do, inside cognitive phases.** Examples currently in prompts:
   - Phase 1 §1.7 — the LLM computes the **VScore composite formula** (`round((company_tier/4*12 + …)/10, 1)`) and `domain_score = max(1, interest+longevity)` by hand. Pure arithmetic.
   - Phase 2 / SKILL.md — the LLM applies the **Fit×VScore recommendation matrix** (decision table) by reasoning. Pure `if/elif`.
   - Phase 3.5 — the LLM computes Top-15 word frequency, scans a tools registry, detects repetition. Pure Python (`Counter`, dict-match, n-gram).
   - Phase 1 §1.0 — `Role`/`Company` extraction and JD language detection. Regex/lib jobs.

Plus: ad-hoc generative rendering is fragile. `services/pdf/render.py` `render_md()` is line-by-line markdown parsing → layout bugs surfaced repeatedly (cover overflow, contacts misparse). fpdf2 also can't render colour emoji.

Result: high latency (agent reasoning + redundant LLM), `Python→AI→Python→AI` flip-flops, arithmetic done by a language model (error-prone), unpredictable output.

> **Note on the H-002 trace:** the 49-step log in H-002 is a single 2026-06-04 run and is **not** a reliable baseline. It excludes Phase 4 (stops at "Переходим к cover?"), predates the `inbox_scan.py` collapse of manual Glob/Grep (steps 8–10), predates VScore and Phase 2.5, and counts one-off feedback edits (steps 26–31) as pipeline. **Re-trace the current happy-path before quoting any step count** (Task 0).

---

## Goal

**Draw and enforce the boundary: deterministic work in Python, cognitive work in the LLM — called only where irreducible.**

- Deterministic skeleton = a Python orchestrator (FSM) that owns all I/O + rule/template/metric steps.
- LLM invoked only for irreducible cognitive work, as **structured calls returning JSON** wherever the step is single-shot — and as a **bounded interactive exchange** only where genuine dialogue is required (Phase 2.5).
- One skeleton, both modes: **API/headless** → orchestrator runs without an agent; **Local** → Claude Code calls the same scripts thinly instead of hand-doing steps.

---

## Execution modes (scope boundary)

Three modes exist; the deterministic/cognitive boundary applies differently to each:

| | Local (`/analyze` skill) | API (`claude_api`) | CLI (`claude_cli`) |
|---|---|---|---|
| Entry point | Claude Code skill | `cv_analyze.py` → ClaudeProvider | `cv_analyze.py` → ClaudeCodeProvider |
| Orchestrator | the agent (reasoning always present) | Python (0 reasoning) | Python (0 reasoning) |
| Glue (FS/DB/menu) | agent turns (can only be *thinned*) | pure code | pure code |
| LLM calls | agent itself = LLM (continuous) | discrete structured calls | `claude --print` subprocess per call |
| Merge calls benefit (Task 5) | **n/a** | real — fewer round-trips | real — fewer subprocesses |
| Reasoning floor | **cannot be removed** | removed for glue | removed for glue |
| Implementation path | Task 6 (thin delegation) | Task 4 FSM + Task 5 | Task 4 FSM + Task 5 |

**CLI and API modes share the same `cv_analyze.py` pipeline** — the cognitive/deterministic boundary is identical for both. ClaudeCodeProvider (`claude_cli`) is a drop-in LLM backend; it doesn't change the orchestration model. Any FSM improvement lands in both API and CLI simultaneously.

**Consequence:** the full deterministic win lands in **API + CLI modes**. Local (`/analyze` skill) can only *thin* the agent (Task 6), never zero its reasoning loop. The skeleton is shared so local benefits where it can.

---

## Classification (H-002 framework applied, re-audited rev 2)

### 🟢 Deterministic — Python, never AI
| Step | Mechanism | State |
|------|-----------|-------|
| inbox scan, dedup (URL + folder fallback) | `scripts/inbox_scan.py` | ✅ done |
| DB: upsert / update / status / delete-inbox | `scripts/vacancy_track.py` | ✅ done |
| FS: mkdir / copy JD / write / cleanup | os/pathlib | ⏳ agent-driven |
| mode / profile / user resolution | config + FSM | ⏳ agent-driven |
| Step 0 menu, inbox menu rendering | string templates | ⏳ agent-driven |
| **PDF render (CV + cover)** | **weasyprint HTML template (Task 1)** | ⏳ fpdf2 `render_md` |
| Quick Scan rendering | render from phase JSON | ⏳ agent-driven |
| `Role — Company` extraction (1.0 header) | regex/parser | ⏳ in prompt |
| JD language detection (en/uk/ru) | `langdetect` / heuristic | ⏳ in prompt |
| **VScore composite formula (1.7)** | **arithmetic from 8 LLM dim-scores** | ⏳ **LLM does it by hand** |
| **Fit×VScore recommendation matrix** | **decision table from fit + blockers + vscore** | ⏳ **LLM does it by hand** |
| Top-15 frequency check (3.5) | `collections.Counter` | ⏳ in prompt |
| Tools & Technologies scan (3.5) | dict match over registry | ⏳ in prompt |
| Repetition check (3.5) | n-gram frequency | ⏳ in prompt |

### 🔴 Cognitive — LLM, irreducible
| Phase | Type | Why irreducible |
|-------|------|-----------------|
| Phase 1 — JD analysis | structured call | interpretation (pain, archetype, culture); emits 8 VScore **dim-scores** (judgment) — composite is Python |
| Phase 2 — fit assessment | structured call (merged with P1) | judgment + barriers + adaptation; emits fit + barrier presence — recommendation matrix is Python |
| **Phase 2.5 — objection handling** | **interactive (multi-turn)** | present barriers → **wait for candidate** → classify resolved/gap → persist. Cannot be a single call. Conditional (only when Key Barriers ≠ нет) and skipped in batch mode. |
| Phase 3 — CV draft | structured call | targeted generation |
| Phase 3.5 — self-review verdict | structured call (merged with P3) | judgment what to cut/strengthen (metrics → Python; only the verdict stays LLM) |
| Phase 4 — cover | structured call | generation |

**Cognitive touchpoints: 4** — three structured JSON calls (`P1+2`, `P3+3.5`, `P4`) + one bounded interactive exchange (`P2.5`, conditional).

---

## Target architecture

```
Python orchestrator (FSM) — owns skeleton + all I/O + deterministic checks
   ├─ call_1 → Phase 1+2 → JSON {analysis, 8 vscore dims, fit, barriers, adaptation...}
   │     └─ Python post-step: compute vscore composite + recommendation matrix + Quick Scan render
   ├─ [branch] Key Barriers ≠ нет AND not batch mode:
   │     pause-state → Phase 2.5 interactive exchange (present → await user → classify)
   │        └─ Python: persist resolved → PROFILE.md + JD_analysis.md
   ├─ call_2 → Phase 3+3.5 → JSON {cv_md, review}
   │     └─ Top-15 / tools-scan / repetition computed in Python BEFORE the call, passed as context
   └─ call_3 → Phase 4 → {cover_md}
   └─ everything else (vscore, recommendation, Quick Scan, PDF, DB, files, menu) = Python
```

**Phase 2.5 is a pause-state, not a synchronous call.** The FSM must model "await user response" between *present barriers* and *classify*. In Telegram this is natural (async messages). In pure headless/batch there is no interactive user → P2.5 is **skipped** (batch already skips it; headless single-vacancy must decide a default: skip + flag barriers honestly).

3 structured calls + 1 conditional interactive exchange instead of a scatter of agent steps → kills the `Python→AI→Python→AI` flip-flop for the deterministic parts.

---

## Diagram & notation rationale

**Visual:** [`docs/diagrams/EPIC-21-pipeline-fsm.html`](../../diagrams/EPIC-21-pipeline-fsm.html) — standalone HTML (open in a browser). Two complementary UML views rendered via Mermaid:
1. **State Machine** — the FSM this EPIC builds (Task 4): states, guards, conditional Phase 2.5 pause-state.
2. **Sequence** — the control inversion: FSM originates every call; the LLM only responds; the user is an awaited actor.

**Why UML, not BPMN:**
- We are literally building a state machine (Task 4). UML State Machine maps 1:1 to the code — states = states, guards = `if`, entry-actions = LLM call / Python compute, pause-state = `await user`. BPMN models a business process, not a state machine — it would describe the flow but not the structure we implement.
- BPMN's strengths (cross-org actor pools, message/timer events, transactions/compensation) are irrelevant here: one orchestrator, one LLM, one user, services. The single overlap — a human task for Phase 2.5 — is expressed cleanly in UML as a pause-state.
- Consumers of this EPIC are developers implementing the FSM; UML (state + sequence) is developer-facing, BPMN reads as analyst-facing.

**Control principle the diagram encodes:** the FSM is primary and owns control flow + I/O; the LLM is a subordinate pure function (text → JSON), with no FS/DB access and no say in what runs next. Cognitive output *influences* branching (data-dependent guards) but never *executes* a transition. Code runs the model, not the model the code.

---

## User Story

```
As the pipeline operator
I want deterministic steps run by Python and the LLM called only for genuine reasoning
So that the process is fast, predictable, cheap, and error-free — especially in API mode
```

---

## Acceptance Criteria

**Given** the pipeline runs end-to-end (analyze → [objections] → CV → cover)
**When** a deterministic step executes (render, dedup, DB, metrics, title/lang, **vscore composite, recommendation matrix**)
**Then** it runs in Python with no LLM call

**Given** a single-shot cognitive phase runs (P1+2, P3+3.5, P4)
**When** the LLM is called
**Then** it is a single structured call returning JSON — no agentic multi-step loop for that phase

**Given** Phase 2.5 runs (barriers present, interactive surface)
**When** the candidate is asked about barriers
**Then** the FSM holds a pause-state awaiting input — and in batch/headless contexts P2.5 is skipped, not faked

**Given** API/headless mode
**When** the full pipeline runs
**Then** no agent reasoning is spent on glue — only the cognitive touchpoints hit the model

**Given** CV or cover rendering
**When** PDF is produced
**Then** layout is identical every run, no overflow/misparse, colour emoji supported (weasyprint HTML template)

---

## Tasks (blocker-ordered)

| # | Task | Severity | Depends on | Status |
|---|------|----------|-----------|--------|
| 0 | **Re-trace current happy-path** — honest step inventory on today's pipeline (inbox_scan collapsed, Phase 4 included, Phase 2.5 conditional). Replaces the stale H-002 49-step count. Output: corrected baseline table. | 🟠 | — | ❌ |
| 1 | **Deterministic PDF templating (weasyprint)** — CV-template + cover-template (Jinja2 HTML + CSS → weasyprint). Content slots in; no markdown line-shape guessing. Replaces fpdf2 `render_md`. Emoji/colour/spacing all in CSS. | 🔴 BLOCKER | — | ✅ Done 2026-06-15 |
| 2 | **Structured JSON contracts per cognitive phase** (Phase 1+2, Phase 3+3.5, Phase 4) — Pydantic models in `contracts/`. LLM returns JSON; orchestrator renders. P1+2 schema includes 8 vscore dim-scores, fit, barrier presence (NOT the composite or recommendation — those are Python). | 🔴 BLOCKER | — | ✅ Done (EPIC-22 B1) |
| 3 | **Move deterministic metrics to Python** — VScore composite formula, Fit×VScore recommendation matrix, Top-15 freq, Tools registry scan, repetition check, `Role — Company` extraction, JD language detection, Quick Scan render. Strip these instructions from prompts. | 🟠 | Task 2 | ⚠️ Partial: VScore + rec matrix ✅ (`core/vacscore.py`); freq/tools/repetition/lang still in prompts |
| 4 | **Python orchestrator (FSM)** — drives the skeleton, calls LLM only on cognitive phases, models Phase 2.5 as a conditional pause-state. Shared for API + CLI modes; Local mode delegates via Task 6. | 🟠 | Task 2 | ❌ |

**Task 4 implementation plan (2026-07-11):**

| Chunk | File | What | Effort |
|-------|------|------|--------|
| 4-C1 | `core/pipeline_fsm.py` | `VacancyState` enum + `VALID_TRANSITIONS` dict + `fsm_transition(vacancy_id, target)` — validates and writes to DB. No orchestration yet. Tests: all legal/illegal transitions. | ~2h |
| 4-C2 | `core/pipeline_runner.py` | `run_analyze()`, `run_generate_cv()`, `run_generate_cover()` — each: pre-condition check → fsm_transition → call tool → fsm_transition (or failed). API endpoints and rss_watcher become thin wrappers. Tests: runner under various starting DB states. | ~4h |
| 4-C3 | `core/cv_metrics.py` | Task 3 remainder: `top_n_words()`, `scan_tools()`, `detect_repetition()` — pre-computed and injected into Phase 3.5 prompt. Strip compute-instructions from `phase3_5_review.md`. Tests: metric functions on real CV samples. | ~3h |
| 4-C4 | Phase 2.5 pause-state | Present barriers → await user → classify resolved/gap. Needs Flutter UI. **Deferred** — separate task, does not block 4-C1/C2/C3. | TBD |

**Order:** 4-C1 (no breakage, new file only) → 4-C2 (runner alongside old code, then switch endpoints) → 4-C3 (prompt + code change).|
| 5 | **Merge cognitive calls (API + CLI)** — Phase 1+2 = one call, Phase 3+3.5 = one call (metrics pre-computed, passed in). Applies to both `claude_api` and `claude_cli` (same `cv_analyze.py` path). No-op for local `/analyze` skill. | 🟡 | Tasks 2, 4 | ❌ |
| 6 | **Local mode delegates to orchestrator/scripts** — Claude Code calls scripts thinly instead of hand-doing glue (vscore, recommendation, render, Quick Scan). | 🟡 | Task 4 | ❌ |
| 7 | **Measure latency + cost** before/after (per-phase timing in ClaudeProvider; add orchestrator timing). | 🟢 | Tasks 4, 5 | ⚠️ Partial: `pipeline_runs` timing exists; formal before/after comparison pending |

> **Task 1 = cleanest "remove from AI contour" win.** Independent of the rest — can land first.
> **Task 0** should run alongside Task 1 to give honest before/after numbers for Task 7.

---

## Backlog consolidation (rev 2)

This EPIC is the **single source of truth** for the deterministic/cognitive split. Two older BACKLOG entries describing the same theme are folded in and should be removed from BACKLOG (replaced by a pointer to this EPIC):

- `P1 — Детерминированный pipeline: минимизировать роль агента` (2026-06-02) → its checklist (strict JD_analysis.md / CV templates, inbox script, SKILL.md step review) maps to Tasks 1–4 + 6.
- `P1 — PDF template system` (2026-06-02) → **= Task 1**. Engine decision resolved: **weasyprint** (was "weasyprint vs playwright"). playwright rejected: ~300MB headless-Chrome dependency, heavier in Docker/CI.

---

## Top findings (H-002 deliverables, rev 2)

**Top remove-from-AI-contour:** PDF render · **VScore composite** · **recommendation matrix** · Top-15 freq · Tools scan · repetition check · title-extraction + language-detection.
**Top unjustified agent use (local):** the entire glue block executed by a reasoning agent.
**Top latency sinks (keep AI, optimize):** Phase 3 CV generation · Phase 1+2 (extended thinking) · Phase 4 — optimize via single structured call, JSON output, PROFILE caching (done).

---

## Scope

### Code (new / changed)
| File | Change |
|------|--------|
| `services/pdf/` | weasyprint template renderer (CV + cover Jinja2/CSS templates); replace `render_md` — Task 1 |
| `contracts/` | phase JSON models (analysis+fit, cv+review, cover) — Task 2 |
| `tools/` or `core/` | Python metrics module (vscore composite, recommendation matrix, freq, tools, repetition, title, lang) — Task 3 |
| `core/` | orchestrator FSM (with Phase 2.5 pause-state) — Task 4 |
| `prompts/pm/`, `prompts/generic/` | phases emit JSON; drop in-prompt vscore-composite, recommendation-matrix, Top-15/tools/repetition instructions (moved to code) — Tasks 2,3 |
| `skill/SKILL.md`, skill `/analyze` command | local mode delegates to orchestrator; recommendation-matrix prose → "computed by Python" — Task 6 |

### Out of scope
- Onboarding interview (genuinely cognitive — stays LLM)
- Telegram/RSS surfaces beyond the shared skeleton
- Migrating existing `vacancies/` artifacts

---

## Dependencies
- EPIC-14 (services/pdf) — base renderer exists ✅ (Task 1 replaces its `render_md`, swaps fpdf2 → weasyprint)
- VScore + recommendation matrix (2026-06-14) — Tasks 2/3 must consume their JSON contract
- Phase 2.5 Objection Handling (2026-06-05) — Task 4 must model it as a pause-state

---

## Notes
- `H-002` workflow log is stale (see Problem note + Task 0). Step 44 shows deprecated `cv_to_pdf.py` (removed 2026-06-04); steps 8–10 predate `inbox_scan.py`; steps 26–31 are one-off feedback edits; Phase 4 + Phase 2.5 + VScore absent.
- H-002 covers only the `/analyze` happy path — extend classification to onboarding/Telegram when those are touched.
- weasyprint needs system libs (pango/cairo) — verify Docker base image includes them before Task 1 lands.
