---
name: career-agent-pipeline
description: >
  PM vacancy analyzer + tailored CV + cover message generator.
  Use when user provides a job description and wants: fit analysis, CV generation, cover message.
  Triggers on: "проанализируй вакансию", "сделай CV", "напиши кавер", "analyze vacancy",
  "tailor CV", "job fit", "cover message", "разбор вакансии".
---

# Career Agent — Claude Code Skill

> Local pipeline. Claude Code IS the agent. Writes to DB via `scripts/vacancy_track.py` → visible in web tracker.
> Phase prompts live in `prompts/`. This file is orchestration only.
> Active user: `skill/active_user` → ID → `skill/users.yaml` → `skill/users/[id]/PROFILE.md`.

---

## Golden Rule — North Star Mirroring

Marketing's core principle applies across the whole pipeline: understand what's in the employer's head (the Phase 1 North Star — the one-sentence outcome the company is actually paying for) and consciously reflect that same image back through the CV and cover — not just by checking off individual JD signals, but by making the SUMMARY and cover opening recognizably answer the North Star sentence itself.

This runs end to end, not as a single-phase check:
- **Phase 1** — North Star (§1.0.5) is the source of truth; everything downstream traces back to it.
- **Phase 2 Adaptation Plan** — reframing actions should point toward North Star language, not only toward individual signal coverage.
- **Phase 3 CV draft** — the SUMMARY must consciously echo the North Star's own image (paraphrased, never JD-verbatim — see Phase 3.7 JD-Echo Risk) so the opening paragraph reads as a direct answer to "what result is this company buying."
- **Phase 3.5 self-review** — includes a North Star Alignment check alongside the existing word-frequency/tools checks.
- **Phase 3.6 signal audit** — ends with an explicit North Star Check line (✅/⚠️/❌) — the "четкая сверка" (clear compliance check) the pipeline closes on before Phase 4.
- **Phase 4 Cover** — category signal + pain recognition should trace to the same North Star image, not a separate framing.

Applies to both `pm` and `generic` skill_type prompt sets.

---

## Language Rules

**Output language:**
1. User communication in chat: the `language` field in the Settings section of `skill/users/[id]/PROFILE.md` (default `en` if not set).
2. Analysis documents written to disk: **English**, always. That is `JD_analysis.md` and every phase block appended to it (Phase 1, 2, 2.5, 3.5, 3.6, 3.7). Project language policy: analysis output, the tracker and the Flutter UI are English-only. When a phase result is presented in chat, summarize it in the language from point 1.
3. CV and cover follow the rules below, not this setting.

- **CV language** — default = JD language (English JD → English CV, Ukrainian JD → Ukrainian CV). Final choice = user (pre-flight ask before Phase 3). User can override the default.
- **Cover language** = same as the approved CV language.

Default is derived from JD language, not from user language setting. But user always confirms or changes before CV is generated.

**Writing tone — authenticity rule (applies to ALL users, ALL languages):**
CV and cover prose must match the candidate's actual proficiency level in the target language. Check PROFILE.md → Languages for the candidate's level in the CV language.

If the candidate is NOT a native speaker of the CV language — do NOT write in native-fluent idiomatic prose.

Avoid:
- Idioms the candidate couldn't translate or verify themselves
- Complex native-speaker constructions that sound unnatural for a non-native writer
- Phrasing the candidate couldn't confidently stand behind in an interview

Prefer: simple, direct, professional sentences. A strong non-native professional writes clearly — not like a native impersonator.

Universal principle: never make the candidate appear to be something they are not. This applies to any language — English, Ukrainian, French, or otherwise.

---

## Light mode — `/analyze -v [id] -lite` (alias `-lt`)

For low-priority or take-a-chance vacancies that already have Phase 1+2. Goes straight to Phase 3 and replaces the Phase 3.5 model self-review with the mechanical checks (the one exception to the mandatory Phase 3 -> 3.5 self-review); it changes the flow below as follows; every other rule (Phase 3 NON-NEGOTIABLE rules, DB writes, PDF once at the end, Rule 8 delivery) still applies:
- Phase 2.5 skipped, no question asked.
- Pre-flight skipped: CV language English (or the one the user adds, e.g. `-lite uk`), default name variant.
- Short CV: Summary of 2 short paragraphs plus the **1-component** AI paragraph (golden line + portfolio link, never the 2-component form in light mode), one short paragraph per role, ALL Key results kept.
- Checks: `python scripts/cv_checks.py` only. Phase 3.6 and 3.7 do not run.
- No cover unless the user asks.
Full description: `.claude/commands/analyze.md` → `-lite`.

---

## Pipeline Flow (NON-NEGOTIABLE)

```
Phase 1 + Phase 2  [run immediately on JD input, no confirmation needed]
  → Before anything else: run `python scripts/vacancy_track.py applied-twin --id [id]`. If `applied_twin_id`
    is not null, tell the user "уже подавали на #X" with the `twin_folder` path (its CV and cover are there)
    and stop — analyze only if the user explicitly confirms.
  → Before running Phase 1: check `salary` on the vacancy DB row (`vacancy_track.py get --id [id]`).
    If non-null, prepend `**Listed salary:** [value]` before the JD text you hand to Phase 1 —
    `salary` is often extracted from RSS/site metadata the JD.md body never mentions, so skipping
    this check makes Phase 1 score compensation as "not stated" when the system already knows it.
  → Same check for `company` on the vacancy DB row. If non-null, prepend `**Known company:** [value]`
    before the JD text — `company` is extracted structurally by the parser (URL/DOM), and some Djinni
    postings never name the employer in the ad copy body itself. Skipping this makes Phase 1 write a
    placeholder like "[not disclosed in JD]" into §1.0, which also clobbers the DB title.
  → Create folder vacancies/inbox/[user_id]/[Role — Company]/   [silent]
  → Save full output to JD_analysis.md   [silent — no confirmation needed]
  → Save p1+p2 to DB analysis_json       [silent — see Analysis JSON section below]
  → Update DB status → analyzed          [silent]

  ⛔ HARD RULE: JD_analysis.md MUST be written to disk BEFORE Quick Scan is shown to user.
     Quick Scan is derived from the saved file — never from memory or inline reasoning only.
     Violation = showing a conclusion without a saved source. Not acceptable.

  → Display in chat: Quick Scan block ONLY

  ↓ [if Key Barriers ≠ нет → Phase 2.5 Objection Handling FIRST — see section below]

  → Ask: "Генерируем CV?"

  ↓ [user confirms]

Pre-flight (ask once, before Phase 3):
  → CV language: ask only if JD ≠ English (English JD → English CV, obvious — skip)
  → Name variant: ask only if the profile's Name variants section has more than one entry; single variant → use automatically, no ask

Phase 3: CV Draft          [NOT shown to user — internal]
Phase 3.5: Self-Review     [review tables + verdict shown to user; CV body NEVER pasted in chat — see rule below]
  → One command runs every mechanical check below at once (repeated terms, repeated phrases,
    mechanical lint, JD echo, word-frequency and tools tables) with UTF-8 output, so it also works
    on a Windows console:
    `python scripts/cv_checks.py --cv "[path to CV draft]" --jd "[path to JD.md]"`
    The individual calls that follow stay valid: use them to re-run a single check after an edit.
  → Before writing the review: compute Repeated Terms + Repeated Phrases against the Phase 3
    draft. Unlike the Python/API pipeline (`tools/cv_generate.py`), this local Claude Code mode
    does not auto-inject these tables — run them yourself via Bash:
    `python -c "import sys; sys.path.insert(0,'.'); from core.cv_metrics import detect_repetition, detect_phrase_repetition; d=open(r'[path to CV draft]', encoding='utf-8').read(); print(detect_repetition(d)); print(detect_phrase_repetition(d))"`
    `detect_repetition` = single words, 3+ occurrences. `detect_phrase_repetition` = 3-5 word
    phrases, 2+ occurrences — this is the one that actually catches a verbatim construction like
    "as part of the team" reused across unrelated role paragraphs, which single-word frequency
    can't see at all. Feed both lists into the Repetition Check below same as the
    Python pipeline would.
  → Also run the mechanical-violation lint (em-dash + banned-phrase list — rule 25 and
    several dated feedback rules recurred multiple times despite already being stated once
    in the prompt, see BACKLOG.md "Mechanical NON-NEGOTIABLE rule violations..."):
    `python -c "import sys; sys.path.insert(0,'.'); from core.cv_metrics import detect_mechanical_violations; d=open(r'[path to CV draft]', encoding='utf-8').read(); print(detect_mechanical_violations(d))"`
    Any hit is a required fix before presenting the review — this is advisory to a human
    reviewer in the Python pipeline (logged, not blocking), but here there is no separate
    human review step downstream, so treat every hit as something to fix now.
  → Also run the JD-echo scan — a cheap,
    mechanical pre-filter for CV phrases that mirror the JD's own distinctive wording, run
    BEFORE any Phase 3.7 isolated audit (which also catches paraphrased, non-literal echo this
    n-gram scan can't see — the two are layered, not redundant):
    `python -c "import sys; sys.path.insert(0,'.'); from core.cv_metrics import detect_jd_echo; cv=open(r'[path to CV draft]', encoding='utf-8').read(); jd=open(r'[path to JD.md]', encoding='utf-8').read(); print(detect_jd_echo(cv, jd))"`
    Advisory, not auto-blocking — some findings are legitimate shared vocabulary (a required
    tool name, a role title term) a human dismisses on read-through, but any hit that echoes
    the JD's own distinctive editorial voice (not a tool/domain term) is a required fix before
    presenting the review.
  → Also run a grammar/sentence-construction pass before presenting the review: unnecessary
    commas (esp. before "and" joining only two items, or between an adjective and the noun
    phrase it modifies, e.g. "a shipped, production system" should be "a shipped production
    system"), dangling/misattributed participial phrases (e.g. "X starts with discovery,
    identifying the client's problems" attributes "identifying" to the wrong subject — rewrite
    as an infinitive purpose clause: "X starts with discovery to identify..."), and awkward
    verb-object pairings (e.g. "led an automated flow" — you lead delivery/a team, not a flow;
    "led the delivery of an automated flow" is correct). This is a real, separate check from
    the repetition/tone passes above.
  → Save [Name]_CV.md to existing folder (already created after Phase 1+2)
  → Present a markdown link to the saved CV.md — per Rule 8, never paste the CV body itself.
    ⛔ NO PDF YET — PDF is generated exactly once, at the end of the whole CV review arc (see
    "PDF Generation — render once, at the end" below). Do not render/send a PDF here.
  → Ask: "Вносим правки или всё ок?"
  → Apply approved changes → re-save CV.md only (no PDF) → re-present the link (still no inline text)
  → Repeat the edit loop as many times as needed — every round touches CV.md only, never the PDF
  → Save p3 to DB analysis_json          [silent — see Analysis JSON section below]

Phase 3.6: Signal Audit    [runs after save, verdict shown to user — CV body still never pasted]
  → Read saved CV (EXPERIENCE section) + Signal Coverage Table from JD_analysis.md
  → Decompose each sentence into clauses first (split on em-dashes/commas), then assess EACH
    clause's value vs JD requirements (valuable / weak / remove) — a sentence is only "valuable"
    if ALL its clauses are (see phase3_6_signal_audit.md's Algorithm)
  → Check coverage: all high/medium signals present in at least one role?
  → Display audit report (findings only, not the CV text)
  → If 🗑️ sentences found: confirm with user → remove → re-save CV.md only (no PDF) → re-run the
    mechanical lint + repetition check against the re-saved text
  → If ⚠️ only: present to user, they decide → any applied rewrite also gets the same re-lint, .md only
  → If clean: proceed

  → Once the CV reaches a final, no-more-edits state (end of the whole Phase 3.5→3.6[→3.7] arc):
    generate the PDF exactly once via http://localhost:8002/render → save PDF bytes → present the
    CV.md + CV.pdf together (Rule 8 — never paste full CV text in chat). See "PDF Generation —
    render once, at the end" below — do not render/send a PDF at any earlier point in this arc.
  → Ask: "Переходим к cover?"

  ↓ [Phase 3.7 only if recommendation = apply AND fit_score ≥ 7, or user asks explicitly]

Phase 3.7: Editorial Audit  [opt-in final polish — see below]

  ↓ [Phase 4 only if the user explicitly requests a cover; independent of Phase 3.7, a cover can follow Phase 3.6 directly]

Phase 4: Cover Message
  → Review/approval cycle (verdict/summary in chat, never the full cover text — Rule 8). Every
    edit round during this cycle saves Cover.md only — no PDF (see "PDF Generation — render
    once, at the end" below).
  → Before approval: run the same mechanical-violation lint as Phase 3.5 (em-dash + banned-
    phrase list, incl. cover-specific bans like "what's already working well" and robotic
    lead-ins "Чесно:"/"Важливо:"):
    `python -c "import sys; sys.path.insert(0,'.'); from core.cv_metrics import detect_mechanical_violations; d=open(r'[path to cover draft]', encoding='utf-8').read(); print(detect_mechanical_violations(d))"`
    Any hit is a required fix before presenting for approval.
  → Save [Name]_Cover.md
  → Once the user confirms the cover is final (no more edits): generate the PDF exactly once via
    http://localhost:8002/render → save [Name]_Cover.pdf
  → Save p4 to DB analysis_json          [silent — see Analysis JSON section below]
  → Present link to saved Cover.md/PDF (Rule 8 — never paste full cover text in chat)
```

**One question at a time. Never ask two questions in one message.**

**File operations — no permission ask.** Create `.md`, `.pdf`, `.json` files and write DB JSON (analysis_json via `vacancy_track.py update-json`) silently. Report what was created/saved after the fact. Never ask "Сохраняю?" before any of these operations.

**Phase completion report — MANDATORY after each phase.** After completing each phase, output a visually distinct block so the user can scroll and immediately see what was done:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Phase 1+2 — Анализ завершён
Fit: N/10 · VScore: N.N · Рекомендация: [value]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Phase 2.5 — Objection Handling завершён
Resolved: N/N · Genuine gaps: [list]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Phase 3+3.5 — CV сгенерирован
[Name] · [language] · [N] правок · CV.md + CV.pdf
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Phase 3.6 — Signal Audit
Clean / N sentences removed · CV.md + CV.pdf updated
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Phase 3.7 — Editorial Audit
N findings · N JD-echo · N applied · CV.md + CV.pdf updated
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Phase 4 — Cover готов
[language] · [вариант] · Cover.md + Cover.pdf
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Phase 2.5 — Objection Handling (barrier resolution)

**Runs between Quick Scan and "Генерируем CV?" — BEFORE any CV is drafted.**
Purpose: surface and resolve weaknesses first, so Phase 3 writes a CV armed with real counter-arguments — not a CV that silently ignores the blockers.

### Trigger

Run whenever Phase 2 **Key Barriers ≠ нет** (any non-empty barriers — includes strong `apply`, not only `take a chance`).
Skip only when: `decline` (not worth it) OR clean `apply` with zero barriers.

### Input

- Phase 2 **Key Barriers**
- **Fit Breakdown** ⚠️ / ❌ items
- **Adaptation Plan**

### Process

1. Present the weak points compactly as a numbered list — for each: the gap + what the JD actually demands.
2. Ask the candidate (one message, per-item): *"По каким из них есть реальный опыт, которого нет в профиле?"*
3. For each barrier, classify the answer:
   - **✅ Resolved** — candidate gives real evidence not yet in PROFILE.md → capture it.
   - **❌ Genuine gap** — confirmed absent → Phase 3 must NOT fabricate; handle honestly. Candidate may decide not to apply.
4. Summarize: resolved (with new evidence) vs genuine gaps. Then proceed to "Генерируем CV?".

### Output / persistence

- **Resolved evidence → append to `skill/users/[id]/PROFILE.md`** (grows the profile; future vacancies benefit). Add it to the Experience (or Skills) entry it belongs to: a fact about a company or role lives inside that role's own block, never in a standalone "additional evidence" section (the profile's own Maintenance Rule). Factual only — never fabricated.
- **Per-vacancy → append an `## Phase 2.5: Objection Handling` block to `JD_analysis.md`** (resolved + genuine gaps + decision).
- Pass resolved objections into Phase 3 context (CV must surface these counter-arguments).
- Optional DB: store under `analysis_json` key `p2_5` (`{resolved:[...], gaps:[...]}`).
- **DB Profile write-back (EPIC-24 T5) — only when `PROFILE_SOURCE=db` for this session.** The default is `md`; in that mode skip this call, because nothing reads the written store back.
  ```bash
  python scripts/profile_merge.py --user-id [id] --evidence "[resolved evidence text]"
  # Or write evidence to temp file first:
  # python scripts/profile_merge.py --user-id [id] --evidence-file /tmp/p25_evidence.txt
  ```
  Only call when `PROFILE_SOURCE=db` AND ≥1 resolved barriers with real evidence. Skip entirely (including the evidence-summarizing work) when `PROFILE_SOURCE=md` (the default). Use `--dry-run` to preview before saving.

### Nature (per EPIC-21)

Cognitive + interactive (dialogue + judgment) → stays LLM. The barrier-list scaffolding is deterministic. Prompt: `prompts/[skill_type]/phase2_5_objections.md`.

---

## Phase 3.7 — Editorial Audit (opt-in final polish)

**Runs after Phase 3.6, only for vacancies that reached a strong outcome — NOT a default step.**
Purpose: catch writing-craft issues (naturalness, credibility, JD-echo risk) that Phase 3.6 doesn't check — 3.6 audits JD-signal coverage per sentence, 3.7 audits prose quality and whether the document accidentally mirrors the JD's own wording.

**Covers CV and Cover both — run separately, one report each.** Both are external-facing documents with the same em-dash/claim-stacking/JD-echo risk; auditing only the CV and shipping an unaudited cover misses half the point. The cover is short (a few sentences) so even one instance of a pattern can matter proportionally more — see `phase3_7_editorial_audit.md` → "Cover Message Variant" for the two dimensions that don't apply to a cover (Show-vs-Tell / metric-credibility, since the cover is deliberately evidence-free by design, per `phase4_cover.md`).

### Trigger

Run only when Phase 2 `recommendation = apply` AND `fit_score ≥ 7`, or when the user explicitly asks for it. **Never run by default on every vacancy** — this is a multi-pass, higher-cost audit; most vacancies (decline / take-a-chance / weak apply) never reach this bar and shouldn't pay for it. Cost discipline over blanket rigor.

### Why isolated context matters here (Claude Code mode specifically)

Self-audit bias is real and measurable: the same auditor (mid-conversation, same context as the document's author) scores their own writing higher than a zero-context pass does on the identical text. **Run this via an isolated subagent** (`Agent` tool, `isolation: "worktree"`), never inline in the same conversation that drafted the document.

**Note (worktree write persistence):** subagent worktree file writes have been observed to not reliably persist after the agent finishes. Always instruct the subagent to return the FULL audit text verbatim in its final response (not a summary) as the primary deliverable — treat any file it writes as best-effort secondary, and save the returned text yourself.

Give the subagent exactly three inputs, nothing else:
1. The saved document — CV file (post 3.5/3.6) OR Cover file (post Phase 4 approval), one per run
2. The vacancy's `JD.md` (for the JD-Echo Risk check — this is why it's a separate input, not folded into a "context" blurb)
3. A one-two sentence audience/archetype blurb (from Phase 1 `## Quick Scan` → Category, Who they want) — not the full `JD_analysis.md`

Prompt file: `prompts/[skill_type]/phase3_7_editorial_audit.md` (full methodology — 5-step workflow, JD-echo check, output format — lives there, not duplicated here).

**Python/API pipeline (`tools/cv_generate.py`) note:** the self-audit bias above is specific to Claude-Code-style long conversations. Each Python pipeline phase is already a stateless, isolated LLM call — no subagent indirection needed there, just call the LLM with the phase3_7 prompt directly.

### After the audit

- **Quick Win findings** (includes JD-Echo Risk by default) → present to user → confirm → apply → re-save CV.md only. Once all Quick Win fixes for this audit round are applied and confirmed: regenerate the PDF once from the final CV.md (do not render on each individual fix).
- **Medium Investment / Major Rewrite** → present, let the user decide — do not auto-apply.
- Append the full audit output to `JD_analysis.md` under `## Phase 3.7: Editorial Audit`.

### Nature (per EPIC-21)

Cognitive + evaluative → stays LLM, not deterministic. Prompt: `prompts/[skill_type]/phase3_7_editorial_audit.md`.

---

## Company Type Detection → Lexicon Adaptation (Phase 3 Pre-flight)

Before generating the CV draft (Phase 3), identify the target company type from the JD:

- **Enterprise** — large org, regulated, formal hierarchy, structured processes, compliance overhead
- **Scale-up** — Series B+, growing, semi-structured, some process maturity
- **Startup** — early-stage (seed/Series A), small team, product not yet defined, high ambiguity
- **Founder-led** — founder still actively running product/delivery, direct collaboration, strong opinions, low bureaucracy (can be any stage)

These are distinct. A Founder-led company can be Series C. A Startup without founder involvement can already feel corporate.

Adjust CV lexicon accordingly. Vocabulary signals company-context fit immediately to the reader.

| Context | Enterprise | Scale-up | Startup | Founder-led |
|---------|------------|----------|---------|-------------|
| Team | "distributed cross-functional teams" | "cross-functional squads" | "small autonomous team" | "worked directly with founders" |
| Process | "structured delivery", "governance", "milestone-based" | "scaled agile", "OKR-driven" | "built from scratch", "0→1" | "greenfield", "no prior process" |
| Decisions | "stakeholder alignment", "executive visibility" | "data-informed prioritisation" | "rapid iteration", "validated assumptions" | "direct founder collaboration", "full autonomy" |
| Growth | "operational efficiency", "process maturity" | "growth at scale" | "PMF", "early traction" | "founder vision → product reality" |

Use enterprise vocabulary when: large company, regulated domain, multiple stakeholder layers, formal org.
Use founder-led vocabulary when: JD mentions founders, "direct access", "flat structure", "early team" — even at larger orgs.

Store detected type as: `COMPANY_TYPE = enterprise | scaleup | startup | founder-led` in working context — used in Phase 3.5 tone check.

---

## How to Execute Each Phase

Load the prompt file, read it fully, then execute against the provided input.

All prompt paths: `prompts/[skill_type]/phaseN.md` — read `skill_type` from the Settings section of the active user's PROFILE.md.
ALL phases are skill_type-specific. No universal phase files remain in prompts/ root.

| Phase | Prompt file | Input |
|-------|------------|-------|
| Phase 1 | `prompts/[skill_type]/phase1_analysis.md` | JD text + active user PROFILE.md in context |
| Phase 2 | `prompts/[skill_type]/phase2_fit.md` | JD text + Phase 1 output |
| Phase 2.5 | `prompts/[skill_type]/phase2_5_objections.md` | Phase 2 Key Barriers + Fit Breakdown ⚠️/❌ + Adaptation Plan |
| Phase 3 | `prompts/[skill_type]/phase3_cv_draft.md` | JD text + JD_analysis.md + language + name + **resolved objections** |
| Phase 3.5 | `prompts/[skill_type]/phase3_5_review.md` | CV draft + JD_analysis.md |
| Phase 3.6 | `prompts/[skill_type]/phase3_6_signal_audit.md` | Saved CV (EXPERIENCE) + Signal Coverage Table from JD_analysis.md |
| Phase 3.7 (opt-in) | `prompts/[skill_type]/phase3_7_editorial_audit.md` | Saved CV + JD.md + audience/archetype blurb from Phase 1 Quick Scan |
| Phase 4 | `prompts/[skill_type]/phase4_cover.md` | JD text + approved CV + JD_analysis.md |

---

## File Saving Rules

**Vacancy folder:** `vacancies/inbox/[user_id]/[Role — Company]/`

Read `user_id` from `skill/active_user` → `skill/users.yaml` → `id` field (e.g. `1`).

```
vacancies/
├── inbox/                           ← системный (RSS, Telegram, API — только система)
│   └── [user_id]/
│       └── [Role — Company]/
│           ├── JD.md                    ← user drops here (or Claude saves from URL)
│           ├── JD_analysis.md           ← Phase 1 + Phase 2 output (auto-save, no confirmation)
│           ├── [Full Name]_CV.md        ← English CV, named after the CV name variant, e.g. John Doe_CV.md
│           ├── [Full Name]_CV_UA.md     ← Ukrainian CV (if generated)
│           ├── [Full Name]_CV.pdf       ← generated PDF
│           ├── [Full Name]_Cover.md     ← cover (English, no suffix)
│           └── [Full Name]_Cover_UA.md  ← cover (Ukrainian)
└── inbox_manual/                    ← пользователь дропает вручную
```

**[user_id]** — read from `skill/active_user`. Plain integer string: `1`, `2`, etc.
**[Role — Company]** — extracted from JD during analysis. Format: `Product Manager — Acme Corp`. Em dash ( — ).
**Folder name format:** `{vacancy_id} — {Role — Company}` — e.g. `405 — Product Manager — MWDN`. ID from DB (upsert first, then mkdir).
**Strip `#` and `,` from every vacancy folder name, no exceptions — not just N-iX.** These two characters break the chat client's markdown-link decoding for ANY file path that contains them (`%23`/`%2C` stay un-decoded while spaces and dashes decode fine, so every markdown link to that folder gives a 404). Treat it as a hard folder-naming rule, checked on every vacancy, every session, regardless of source site:
- Job-board IDs in the title (a `#` followed by digits, with or without parentheses) — drop entirely, the URL already has this.
- Commas inside the title (e.g. `(Product, UX)`) — drop the comma (join with a space, or use `;` if a separator is really needed).
- Any other punctuation beyond letters/digits/spaces/hyphens/en-dash/em-dash/parentheses that shows up in a scraped title — treat as suspect and strip before using it in a folder name.
- The DB `title` field may keep the original text if useful for display; only the **folder name** (and any path derived from it) must be stripped.
- If an existing vacancy folder is later found to contain `#` or `,`, rename it and update `markdown_path` in the DB the same way — don't leave old ones broken.
**With a tag** (see below): `{vacancy_id} — [TAG] — {Role — Company}` — e.g. `1303 — [DEFTECH] — AI Product Manager — Everstar`. Tag in brackets, uppercase, right after the ID so it's the first thing visible in a sorted folder listing.
**DB title** — stores `Role — Company` only (without ID prefix).

**Tags (user-assigned, free-form, comma-separated):**
When the user flags a vacancy (or a batch/session) as belonging to a category — e.g. "these are deftech vacancies" — set the DB `tags` column via `vacancy_track.py update --id $VACANCY_ID --status [current status] --tags "deftech"` (multiple: `"deftech,ai"`), and include the primary tag in the folder name per the format above. This is distinct from `role_tags` (auto-derived from `role_balance`, display-only) — `tags` is explicit, persisted, and shown prominently in the Flutter UI (badge above the title, editable field next to Salary). Once a tag is set for a session/batch, apply it to every vacancy processed under that context without re-asking.

**inbox_manual processed files** move to `vacancies/inbox/[user_id]/[Role — Company]/` — same standard.

**JD_analysis.md — always starts with Quick Scan header.** This is the Quick Scan block from Phase 2's output section 3, moved to the top of the file, not repeated inside the Phase 2 part. Phase 2's template also lists `Why apply` and `Why not apply`; those are stored in the DB (`p2.why_apply`, `p2.why_not_apply`) and may be left out of the file's block.

```markdown
## Quick Scan

**Fit score:** X/10
**VScore:** X.X/10
**Recommendation:** apply / decline / take a chance
**Category:** [archetype from Phase 1]
**Who they want:** [1 sentence]
**Key Barriers:** нет / [list]
**Hidden Risks:** нет / [list]
**Warnings:** нет / [list]
```

Then: full Phase 1 analysis → full Phase 2 fit assessment.

**Recommendation logic:** blockers ≠ нет OR fit < 5 → `decline` always (VScore cannot override). No blockers + fit 5–6: VScore ≥ 7.5 → `take a chance — premium opportunity`; VScore < 5.5 → `decline — not worth the effort`. Fit ≥ 7 + VScore < 5.5 → `apply — limited upside`. DB stores base value only (`apply` / `take a chance` / `decline`).

`decline` is an advisory recommendation label only — it does NOT block Phase 3. The user is always asked "Генерируем CV?" (see Pipeline Flow above) regardless of recommendation; if they say yes, Phase 3 must produce a real CV draft (Adaptation Plan always provides reframing actions, see phase2_fit.md), never a refusal placeholder. The decision to skip generation belongs to the user, not the pipeline.

**Re-analysis (Повторить Phase 1+2):** if `JD_analysis.md` already exists in the vacancy folder, save the new analysis to `[vacancy_folder]/Claude Desktop/JD_analysis.md` — never overwrite the original. Create the subfolder silently.

**Phase 3.5 self-review — append to JD_analysis.md after user approval:**

```markdown
---

## Phase 3.5: CV Self-Review

Date: [date]

[Full self-review output]

**Decision:** [Changes applied / No changes — approved as-is]
```

---

## PDF Generation — render once, at the end

**NON-NEGOTIABLE: never render or send a CV/cover PDF during an iterative edit/review loop.** Every edit-round save
during Phase 3.5, 3.6, 3.7, or Phase 4's approval cycle touches the `.md` file only. Render the PDF
exactly once — when the document reaches a final, no-more-edits state for that phase (user says
"ок"/"всё ок"/no further changes, or the phase ends and hands off to the next one) — then present
`.md` + `.pdf` together. A PDF render + `SendUserFile` round-trip on every small wording tweak is
pure overhead: the user only needs to see and react to the text while iterating.

Render via the **pdf-service** (`services/pdf/`, live). **NEVER** `../callback-cv/cv_to_pdf.py` — deprecated, external repo, has the old un-fixed renderer.

**HTTP (service running on :8002):**
```bash
python -c "import httpx,pathlib; p=pathlib.Path('vacancies/inbox/[user_id]/[Role — Company]/[Full Name]_CV.md'); r=httpx.post('http://localhost:8002/render',json={'markdown':p.read_text(encoding='utf-8')},timeout=30); r.raise_for_status(); p.with_suffix('.pdf').write_bytes(r.content)"
```

**In-process (no server needed, always uses fresh render.py code):**
```bash
CAREER_AGENT_FONTS=fonts/ python -c "import sys,pathlib; sys.path.insert(0,'services/pdf'); from render import render_to_bytes; p=pathlib.Path('vacancies/inbox/[user_id]/[Role — Company]/[Full Name]_CV.md'); p.with_suffix('.pdf').write_bytes(render_to_bytes(p.read_text(encoding='utf-8')))"
```

Same service renders **CVs and covers** — `render_md` is cover-aware (CV header only when a contacts-links line is present).
**Note:** the HTTP service has no `--reload`; after editing `render.py`, restart it or use the in-process form.

---

## Name Selection (before Phase 3)

1. Read the profile's Name variants section. Count entries.
2. **Single variant** → use automatically, no ask.
3. **Multiple variants** → ask user to choose.

**Decision matrix:**

| JD language | Name variants | Pre-flight ask |
|-------------|---------------|----------------|
| English | 1 | Nothing — proceed directly |
| English | Multiple | Name only |
| Non-English | 1 | Language only |
| Non-English | Multiple | Language + name together |

**Name-only ask (English JD, multiple variants):**
```
Какое имя использовать?
  [1] [variant 1]
  [2] [variant 2]
```

**Language + name together (non-English JD, multiple variants):**
```
На каком языке готовить CV?
  [1] English — [English name variant]
  [2] [JD language] — [local name variant]
  [3] Оба — English: [English name] + [JD language]: [local name]
```

**Language only (non-English JD, single variant):**
```
На каком языке готовить CV?
  [1] English
  [2] [JD language]
  [3] Оба
```

Option "Оба" → two CVs + two covers generated sequentially.

---

## Analysis JSON — Structured DB write per phase

**After Phase 1+2 — save p1 + p2:**

```bash
python scripts/vacancy_track.py update-json --id $VACANCY_ID --phase p1 --data '{
  "role": "[exact role title from JD]",
  "company": "[company name — clean, not a JD text snippet]",
  "north_star": "[one-line North Star from 1.0.5]",
  "primary_archetype": "[Primary archetype label from 1.3]",
  "company_type": "product|hybrid|outsourcing",
  "role_balance": {"strategy": N, "discovery": N, "delivery": N, "growth": N, "stakeholder": N, "operational": N},
  "dominant_culture": "ownership|speed|alignment|process|innovation|predictability",
  "vacscore_dims": {
    "company_tier": N,
    "seniority": N,
    "market_scope": N,
    "company_type": N,
    "company_stage_fit": N,
    "domain_score": N,
    "remote_policy": N,
    "compensation": N
  },
  "vacancy_score": N.N
}'
```

> **`role_balance` — six-axis taxonomy.** Canonical keys are `strategy`/`discovery`/`delivery`/`growth`/`stakeholder`/`operational` — always these exact names, not synonyms (`execution`, `coordination`, `ops` are old names; do not use them). Analyses written earlier may lack `growth`.

> **Every field above is REQUIRED — this must validate against `contracts/pipeline.py:Phase1Data`.**
> `role`/`company` are the most consequential (see below), but any missing field
> (`north_star`, `primary_archetype`, `vacscore_dims`, ...) or a `company_type`
> value outside `product|hybrid|outsourcing` makes the whole `analysis_json`
> fail strict validation — the API then falls back to a legacy parser that
> only reads `role`/`company`.
> If unsure the current template still matches the schema, check `contracts/pipeline.py:Phase1Data`/`Phase2Data` directly —
> don't trust this doc blindly.
>
> **`role` and `company` are MANDATORY, not optional.** The web tracker list view reads `analysis_json.p1.role` and `.company` (`_parse_analysis_summary` in `web/api.py`). If omitted, the UI silently falls back to the raw DB `company`/`title` columns — which for RSS/scraped vacancies can be a garbage JD-text snippet instead of the actual company name.

python scripts/vacancy_track.py update-json --id $VACANCY_ID --phase p2 --data '{
  "fit_score": N,
  "recommendation": "apply|take_a_chance|decline",
  "recommendation_label": "[must start with the recommendation text above, e.g. \"Apply — strong match\" or \"Take a chance — ...\"]",
  "category": "[category string from Quick Scan]",
  "who_they_want": "[one-line ideal-candidate summary]",
  "key_barriers": ["short label 1", "short label 2"],
  "hidden_risks": ["risk 1", "risk 2"],
  "warnings": ["warning 1", "warning 2"],
  "why_apply": ["reason 1", "reason 2"],
  "why_not_apply": ["reason 1", "reason 2"],
  "fit_dimensions": {
    "domain_fit": N.N,
    "execution_fit": N.N,
    "strategy_fit": N.N,
    "systems_fit": N.N,
    "stakeholder_fit": N.N,
    "overall_fit": N.N
  }
}'
```

**key_barriers format:** short labels only, max 5 words each — e.g. `["A/B testing", "consumer product", "PSP/POS integrations"]`. These appear as chips in the tracker.
**fit_score:** integer (7, not "7/10").
**warnings/hidden_risks:** array of short strings, or empty array `[]` if none.
**recommendation:** `take_a_chance` uses an underscore, not a space — `recommendation_label` validates that it starts with the recommendation text (spaces, case-insensitive), so `"take_a_chance"` → label must start with `"take a chance"` (e.g. `"Take a chance — ..."`).
**salary** is a separate DB column, not a `p2` field — set it via `vacancy_track.py update --id $VACANCY_ID --salary "..."` if needed, don't add it to this JSON.

**After p1+p2 saved — update status (MANDATORY):**

```bash
python scripts/vacancy_track.py update --id $VACANCY_ID --status analyzed
```

> **Почему MANDATORY:** без этого шага вакансия остаётся в статусе `fetching` в DB и трекере,
> даже если анализ выполнен и analysis_json сохранён.

**After Phase 3.5 approval — save p3, then update status (MANDATORY):**

```bash
python scripts/vacancy_track.py update-json --id $VACANCY_ID --phase p3 --data '{
  "name_variant": "John Doe",
  "cv_language": "en|uk|ru",
  "changes_count": N
}'
python scripts/vacancy_track.py update --id $VACANCY_ID --status cv_generated
```

**After Phase 4 approval — save p4, then update status (MANDATORY):**

```bash
python scripts/vacancy_track.py update-json --id $VACANCY_ID --phase p4 --data '{
  "cover_language": "en|uk|ru"
}'
python scripts/vacancy_track.py update --id $VACANCY_ID --status cover_generated
```

> **Same MANDATORY reasoning as the p1+p2 status step above** — `stage()`
> (`core/vacancy_stage.py`) maps `cv_generated`/`cover_generated` → "Processed"
> folder; without this step the vacancy stays in "Analyzed" forever even
> after a CV/cover was actually written, because `analysis_json.p3`/`.p4`
> existing is invisible to the stage classifier — only `status` drives it.

---

## Step 0 — Combined menu (always first)

**Every `/analyze` invocation starts here** — ONE message, two blocks, **no round-trip**.
Mirrors the `-v` combined display: Block 1 = profile/mode (`1–10`), Block 2 = actions (`11–20`).

**Before displaying — scan inbox** (populates Block 2):

```bash
python scripts/inbox_scan.py --user-id [user_id] --json
```

Read `skill/active_user` → name + slug. Display **both blocks side by side — vertical split (columns), NOT a horizontal ━━━ divider**:

```
👤 John Doe (john) · [режим ещё не выбран]

  Профиль / Режим              │   📥 Inbox — N вакансий
  ─────────────────────────    │   ──────────────────────────────
  [1] Локально (Claude Code)   │   [11] Role — Company 🆕
  [2] API (расход токенов)     │   [12] Role — Company ♻️
  [3] Другой профиль (-u)      │   [13] обработать все (batch)
                               │   [14] пропустить inbox → новая
```

Left column = Block 1 (`1–10`). Right column = Block 2 (`11–20`). `│` separates them.

**Inbox empty → right column collapses to** `[11] Загрузить новую вакансию — вставь JD или URL`.

### Routing

- **1/2** → set `MODE = local|api`. If no action given too → re-display Block 2 ("Что обрабатываем?").
- **3** → show user list (same as `-l`), stop — re-run with `-u`.
- **11–1X** → process that inbox item · `[batch]` = all · `[skip]` = new vacancy.
- **Combined** (e.g. `2 11`, `1, 13`) → mode + action in one step. **Preferred — kills round-trip.**
- **Action without mode** → default `MODE = local`. Show `[Локально]` in status lines.
- Selected mode applies to **entire session** — all phases, all inbox files, everything.
- **Exception:** `-l` (list users) and `-inbox` (list inbox) → skip Step 0, read-only.
- **`-v [id]`** has its own combined display (vacancy phase actions in Block 2).

**After Step 0 → Step 2 (analysis).** (Inbox scan already done above — no separate Step 1.)

---

## Inbox — Manual Vacancy Drop

**Folder:** `vacancies/inbox_manual/`
**Purpose:** user drops JD files here manually; system picks them up on `/analyze`.

### Inbox scan — part of Step 0 (Block 2), not a separate step

Inbox scan runs **inside Step 0** and populates Block 2 of the combined menu.
**No separate mode-then-inbox round-trip.** This is the Block 2 detail.

> ⚠️ **inbox = папки, не плоские файлы.** Drops лежат как `inbox_manual/Role — Company/<jd>.md`.
> НЕ сканируй `ls`/`find` руками (нерекурсивный `ls` пропустит подпапки → ложное "пусто").
> Каноническая команда — единственный допустимый способ scan:
>
> ```bash
> python scripts/inbox_scan.py --user-id [user_id] --json
> ```
>
> Возвращает массив: `title`, `source_url`, `file`, `raw_folder`, `seen`, `seen_path`.
> Dedup уже сделан: URL → поиск в `JD.md` и `JD_analysis.md`; без URL → совпадение по имени папки в `vacancies/inbox/{user_id}/`.
> `raw_folder` → точный аргумент для `vacancy_track.py delete-inbox --folder`.

1. Run `scripts/inbox_scan.py --user-id [user_id] --json`
2. **Empty array** → Block 2 = `[11] Загрузить новую вакансию`
3. **Items found** → render as Block 2 (`11`=first vac, `12`=second, … `[batch]`, `[skip→new]`):

```
📥 Inbox — N вакансий:
  [11] Role — Company 🆕
  [12] Role — Company ♻️
  [13] обработать все (batch)
  [14] пропустить inbox → новая вакансия
```

   Multi-select via any separator: `11`, `11,12`, `11 12`.
   Profile fixed by `active_user`/`-u` — never re-ask. Mode handled by Block 1.

4. **Always use Batch mode** — regardless of vacancy count (1, 2, or more). Run all selected vacancies through Phase 1+2, then show consolidated table. Ask Phase 3+4 after table.

---

### Batch Mode (any count)

**Trigger:** any inbox selection — 1 vacancy, 2, or more.

**Flow:**

```
Обрабатываем N вакансий [Локально]...
```
*(single line, no per-vacancy progress — desktop app, result matters not the spinner)*

Run **Phase 1+2 silently** for every selected vacancy:
- **Dedup:** use `seen`/`seen_path` from `inbox_scan.py` output (no manual grep)
  - `seen: true` → **do NOT upsert** (vacancy already registered — creating a duplicate is wrong). Note as `♻️ уже обработана` in Ключевой gap column. Skip analysis entirely.
  - `seen: false` → proceed with full pipeline below
- Register in DB: `vacancy_track.py upsert --title "Role — Company"` → captures `$VACANCY_ID`
- Create folder `vacancies/inbox/[user_id]/[ID] — [Role — Company]/`
- Save `JD.md` (original JD text) to that folder
- Run Phase 1+2
- Save `JD_analysis.md` to `vacancies/inbox/[user_id]/[ID] — [Role — Company]/`
- Update DB: `vacancy_track.py update --id $ID --status analyzed --path "<folder>/JD.md"` (always `JD.md`, never `JD_analysis.md` — the path drives the JD view and auto-tags)
- Save p1+p2 JSON: `vacancy_track.py update-json --id $ID --phase p1 ...` and `--phase p2 ...`

⚠️ **All DB writes must complete before table is shown.** The user checks the tracker while thinking — it must already reflect the results. Table = confirmation that tracker is current, not a preview.

```
📊 Batch анализ — N вакансий [Локально]

 #  Компания — Роль                        Src    Fit   Рекоменд.       Уровень / $     Ключевой gap
──────────────────────────────────────────────────────────────────────────────────────────────────
15  SOLAR Digital — AI PM                 DOU   7/10  ✅ Подавать       Mid/Senior      n8n (минор)
11  Oradian — Senior PM (AI)              LI    6/10  ✅ Подавать       Mid–Senior      Fintech = плюс, не требование
12  Pencil — Sr PM Biz Engineering        LI    5/10  ⚠️ Рассмотреть   Senior          API PM gap; 100+ заявок
 7  Alliance Digital — PM                 DJ    5/10  ⚠️ Рассмотреть   Mid, ~$3K       Banking gap; $3K потолок
 5  Kyivstar.Tech — Sr PM KIP             LI    4/10  ❌ Пропустить    Senior          Sr+telco+identity = 3 блокера
...

Рекомендовано к подаче: #15, #11
```

**Table rules:**
- Sort: ✅ first → ⚠️ second → ❌ last; within group by fit score DESC
- `Уровень / $`: extract from JD if mentioned (Senior/Mid, salary range) — show "—" if absent
- `Ключевой gap`: max 1–2 phrases, no full sentences
- Use folder name as `Компания — Роль` (no truncation)
- `Src`: DOU / LI / DJ / — (if unknown)

**After table — ask naturally (no buttons):**

```
Рекомендовано к подаче: #X, #Y.
Какие обрабатываем дальше?
```

Wait for free-form answer: numbers, names, "все рекомендованные", "пропустить".
Proceed with Phase 3+4 for selected vacancies.

> **Note:** "Approve / Try chance" button pattern is for Telegram/web/mobile UI surfaces.
> In local Claude Code mode — natural language only. No menu needed.

**After Phase 1+2 + table — delete raw inbox_manual folders** regardless of Phase 3+4 decision.
Clean `Role — Company/` folders already created under `vacancies/inbox/{user_id}/` during analysis — raw staging folders are no longer needed:
```bash
python scripts/vacancy_track.py delete-inbox --folder "RAW_FOLDER_NAME"
```
Run once per processed raw folder (exact name as it appeared in `inbox_manual/`).

6. After table → Phase 3+4 for selected → "Продолжить с новой вакансией или завершить?"

### File naming convention (recommended for user)

```
vacancies/inbox_manual/
└── Role — Company/           ← user drops folder here; cleared after processing
```

If filename contains ` — ` (em dash) → use as vacancy folder name directly.
Otherwise → extract company/role from JD content during analysis.

---

## `-v [id]` — Resume pipeline for existing vacancy

```bash
/analyze -v 75
/analyze -vacancy 75
```

Inbox check **skipped**. Display **both blocks in one message** — no round-trip for mode confirmation.

```bash
python scripts/vacancy_track.py get --id [id]
```

### Numbering scheme

- **Block 1 (1–10):** profile + mode — informational header, rarely changed
- **Block 2 (11–20):** vacancy pipeline actions — main working block

Answer 1–10 → Block 1 action. Answer 11–20 → Block 2 action. Never ambiguous.

### Display format

```
👤 John Doe (john) · Локально

  [1] Сменить режим → API
  [2] Сменить профиль

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 Вакансия #[id] [Локально]

[title]
[url]
Создана: [created_at date]

Выполнено:
  ✅ Phase 1+2 — анализ (fit [N]/10, rec: apply)
  ✅ Phase 3+3.5 — CV ([name_variant], [cv_language], [changes_count] правок)
  ❌ Phase 4 — cover не сгенерирован

Что делаем?
  [11] Phase 4 — написать cover
  [12] Повторить Phase 3+3.5 — новый CV
  [13] Повторить Phase 1+2 — новый анализ
  [14] Заново с нуля — Phase 1+2 → 3+3.5 → 4
```

### Block 1 logic

- `[1]` toggle mode (Локально ↔ API)
- `[2]` change profile → show user list, ask re-run with `-u`
- If toggled → re-display both blocks with updated mode

### Block 2 logic

Phase done = key present in `analysis_json` (`p2` → Phase 1+2, `p3` → Phase 3+3.5, `p4` → Phase 4).

Menu order: first ❌ phase at `[11]`, then remaining phases in reverse order, last = "Заново с нуля".

**"Заново с нуля"** → Phase 1+2 silent → Quick Scan → "Генерируем CV?" → normal pipeline. Use after prompt/rule/SKILL.md changes.

**Re-analysis save rule:** when running "Повторить Phase 1+2" or "Заново с нуля" on a vacancy that already has `JD_analysis.md` — save new analysis to `[vacancy_folder]/Claude Desktop/JD_analysis.md`. Never overwrite original. Same rule applies in cv_analyze.py (Python pipeline).

**JD source:** `[vacancy_folder]/JD.md` → absent → `JD_analysis.md` → absent → ask user.

Vacancy folder = parent dir of `markdown_path` from DB record.

---

## Loading Context

**Entry point: `/analyze`** — always use this command to start.

**Per-user overrides:** after loading base `skill/SKILL.md`, also load `skill/users/[id]/SKILL.md` if the file exists. Personal rules (language scope, exclusions) live there and extend the base mechanics.

| Command | Action |
|---------|--------|
| `/analyze` | **mode** → inbox → active user → load → start |
| `/analyze -v [id]` | **mode** → load vacancy by DB id → continue pipeline → skip inbox |
| `/analyze -u [id\|slug]` | **mode** → switch user → inbox → load → start |
| `/analyze -l` | show user list → stop (no mode ask) |
| `/analyze -inbox` | show inbox contents → stop (no mode ask) |

Do NOT load `@skill/SKILL.md` manually without going through `/analyze` —
wrong profile may be loaded.

---

## Difference from Telegram Pipeline

| | Claude Code skill | Telegram bot |
|--|------------------|-------------|
| Trigger | `/analyze` or natural language | RSS auto-discovery |
| Profile | `skill/users/[id]/PROFILE.md` | DB (after onboarding) |
| DB writes | Yes — via scripts/vacancy_track.py | Yes |
| PDF | Direct subprocess | CVAdapter → HTTP |
| Multi-user | Yes — `users.yaml` + `active_user` + `/analyze -u` | Yes — DB |
| Use when | Quick analysis, no infra needed | Full production pipeline |
