# Epic 10: Cover Message Tool

**Status:** 🟢 Done
**Phase:** 2 — CV Pipeline
**Priority:** 🟡 P2
**Blocks:** EPIC-11 (cv_get_tracker)

---

## Strategic Context

Fourth and final pipeline step. Takes a fetched + analysed + CV-generated vacancy and produces
a short, targeted cover message ready to copy-paste into a job application.

Cover language is auto-detected by Claude: Ukrainian JD → Ukrainian cover, English JD → English cover.
No approval flow — message returned directly to Telegram.

---

## Goal

`tools/cv_cover.py` exposes `cv_cover(ctx, vacancy_id) → str`.
Registered in `agent.py` ToolRegistry.

---

## Phase

| Phase | Prompt file | Input | Output |
|-------|-------------|-------|--------|
| Phase 4 | `phase4_cover.md` | JD text + JD_analysis.md + [Name]_CV.md | Cover message (greeting + 3 bullets + closing) |

Cover structure (Ukrainian-language JD — greeting/closing in Ukrainian, bullets in target language):
```
[Ukrainian greeting]

[2–3 bullet matches — specific, active verbs, concrete fact]

[Ukrainian closing referencing company/role]

[Name]
```

---

## File Layout

```
vacancies/{site}/YYYY-MM/{slug}/
├── JD.md                    ← EPIC-7
├── JD_analysis.md           ← EPIC-8 (+ Phase 3.5 review appended by EPIC-9)
├── CV_draft_p3.md           ← EPIC-9 (debug)
├── [Name]_CV.md             ← EPIC-9
├── [Name]_CV.pdf            ← EPIC-9
└── [Name]_Cover.md          ← EPIC-10 (this)
```

---

## User Stories

### US-1001: Generate cover message for a vacancy with approved CV

**Given** vacancy has status `cv_generated`, JD.md + JD_analysis.md + [Name]_CV.md exist
**When** `cv_cover(ctx, 42)` runs
**Then**:
- Phase 4 cover message generated
- `[Name]_Cover.md` saved to vacancy folder
- Vacancy status → `cover_generated`
- Telegram reply: "✅ Cover message готов" + full cover text + file path

### US-1002: JD_analysis.md missing

**Given** analysis not yet run
**When** `cv_cover` runs
**Then** return user-friendly error "⚠️ JD_analysis.md не найден"

### US-1003: [Name]_CV.md missing

**Given** CV not yet generated
**When** `cv_cover` runs
**Then** return user-friendly error "⚠️ {Name}_CV.md не найден"

### US-1004: LLM error on Phase 4

**Given** Claude returns `LLMError`
**When** `cv_cover` runs
**Then**:
- `pipeline_runs` row marked `error`
- `[Name]_Cover.md` NOT written
- Status not updated
- User-friendly error returned

---

## Implementation

| File | Change |
|------|--------|
| `tools/cv_cover.py` | New — Phase 4 cover tool |
| `agent.py` | Register `cv_cover` in `_register_tools` |

---

## Acceptance Criteria

- Phase 4 called with JD + analysis + approved CV as single user input
- `[Name]_Cover.md` saved to vacancy folder
- Vacancy status updated to `cover_generated`
- `pipeline_runs` tracked: insert → running → done/error
- LLM error → message + no Cover.md + status not updated
- Cover text returned verbatim in Telegram reply (ready to paste)
