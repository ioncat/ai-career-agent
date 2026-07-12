# EPIC-21 — Deterministic vs Cognitive pipeline split

**Status:** ✅ Done  
**Priority:** P1  
**Updated:** 2026-07-12  
**Source:** `docs/discovery/hypotheses/H-002-pipeline-optimization-cognitive_vs_determined.md`

---

## Current status

| # | Task | Status |
|---|------|--------|
| T1 | Deterministic PDF render (weasyprint) | ✅ Done 2026-06-15 |
| T2 | Pydantic contracts per cognitive phase | ✅ Done (EPIC-22 B1) |
| T3 | Deterministic metrics → Python, strip from prompts | ✅ Done 2026-07-11 |
| T4 | Python FSM orchestrator + notifier | ✅ Done 2026-07-11 (4-C4 deferred) |
| T5 | ~~Merge cognitive calls (API + CLI)~~ | 🚫 Dropped — quality risk > latency benefit |
| T6 | Local mode: thin delegation to scripts | 🚫 Dropped — saves only 2–3 turns; reasoning floor is architectural, not scriptable |
| T0 | Re-trace happy-path baseline (replaces stale H-002) | 🚫 Dropped |

---

## What's left → moved out

**4-C4** (Phase 2.5 pause-state) — moved to BACKLOG as standalone 🟠 P1 task. Needs Flutter UI design before implementation.

All other remaining items dropped. EPIC goal achieved.

---

## Goal

Draw and enforce the boundary: **deterministic work in Python, cognitive work in LLM — only where irreducible.**

Python FSM owns all I/O, rules, templates, metrics. LLM called only for 4 cognitive touchpoints:
- Phase 1+2 (structured call — JD analysis + fit assessment)
- Phase 2.5 (interactive multi-turn — conditional on Key Barriers)
- Phase 3+3.5 (structured call — CV draft + self-review)
- Phase 4 (structured call — cover letter)

---

## Problem

Two waste sources eliminated by this EPIC:

1. **Agent executes deterministic glue** — each mechanical step (DB write, file rename, menu render) = agent reasoning turn. Expensive model does `if/else` work.
2. **LLM computes things Python should** — VScore formula (arithmetic), recommendation matrix (decision table), word frequency (Counter), tools scan (dict-match), repetition check (n-gram). All moved to Python in Tasks 3–4.

---

## Target architecture

```
Python FSM — owns skeleton + all I/O
   ├─ call_1 → Phase 1+2 → structured output
   │     └─ Python post-step: vacscore composite + recommendation matrix + Quick Scan render
   ├─ [branch] Key Barriers ≠ нет AND not batch:
   │     pause-state → Phase 2.5 (present → await user → classify → persist)
   ├─ call_2 → Phase 3+3.5 → structured output
   │     Pre-step: top_n_words() + scan_tools() + detect_repetition() → injected as context
   └─ call_3 → Phase 4 → cover
```

**Implemented:** `core/pipeline_fsm.py` · `core/pipeline_runner.py` · `core/notifier.py` · `core/vacscore.py` · `core/cv_metrics.py`  
**Diagram:** [`docs/diagrams/EPIC-21-pipeline-fsm.html`](../../diagrams/EPIC-21-pipeline-fsm.html)

---

## Reference

### Execution modes

| | Local (`/analyze` skill) | API (`claude_api`) | CLI (`claude_cli`) |
|---|---|---|---|
| Orchestrator | agent (always reasoning) | Python FSM | Python FSM |
| Glue | agent turns (only thinnable via T6) | pure code | pure code |
| LLM calls | continuous | discrete structured | `claude --print` subprocess |
| T6 benefit | reduces reasoning scope | n/a | n/a |

CLI and API share the same `cv_analyze.py` path — FSM improvements land in both simultaneously.

---

### Classification

**Deterministic (Python) — as of 2026-07-11:**

| Step | Where |
|------|-------|
| Inbox scan + dedup | `scripts/inbox_scan.py` |
| DB operations | `scripts/vacancy_track.py`, `db/database.py` |
| PDF render | `services/pdf/` (weasyprint + Jinja2) |
| VScore composite formula | `core/vacscore.compute_vacancy_score()` |
| Fit×VScore recommendation matrix | `core/vacscore.compute_recommendation()` |
| Top-15 word frequency | `core/cv_metrics.top_n_words()` |
| Tools & Technologies scan | `core/cv_metrics.scan_tools()` |
| Repetition check | `core/cv_metrics.detect_repetition()` |
| Role/Company extraction | `cv_analyze._extract_vacancy_title()` |
| JD language detection | `cv_generate.py` Cyrillic heuristic |
| Quick Scan render | `cv_analyze._extract_quick_scan()` + `_build_analysis_file()` |
| FSM state transitions | `core/pipeline_fsm.fsm_transition()` |
| Pipeline notifications | `core/notifier.notify()` |
| FS/menu/profile resolution | ⏳ still agent-driven (T6 scope) |

**Cognitive (LLM, irreducible):**

| Phase | Type | Why irreducible |
|-------|------|-----------------|
| Phase 1+2 | structured call | interpretation: pain, archetype, culture, fit judgment |
| Phase 2.5 | interactive multi-turn | dialogue: present barriers → await user → classify resolved/gap |
| Phase 3+3.5 | structured call | generation + self-review verdict |
| Phase 4 | structured call | cover letter generation |

---

### Notification strategy (finalized 2026-07-11)

- **Telegram** → new vacancy only (RSS watcher)
- **Web Push** → frozen as-is (`core/push.py`); not expanded
- **Flutter in-app** → all pipeline events via `NotificationProvider` polling `/api/notifications`
- **OS notifications** → future extension (when Flutter minimized/closed)

---

### Dependencies

- EPIC-22 B1 — Pydantic contracts (`contracts/pipeline.py`) ✅
- VScore module (2026-06-14) ✅
- Phase 2.5 Objection Handling design — blocks T4-C4
