# Phase 3.7: Editorial Audit (opt-in final polish)

Runs after Phase 3.6 Signal Audit, only for vacancies that reached a strong outcome
(see Trigger below). Last quality gate before the application is sent — evaluates
writing craft (naturalness, credibility, JD-echo risk), not JD-signal coverage
(that's 3.6).

**Applies to CV and Cover both — audit them separately, one report each, never
merged into one pass.** Both are external-facing documents with the same em-dash/
claim-stacking/JD-echo risk; auditing only the CV and shipping an unaudited cover
defeats the point. See "Cover Message Variant" below for what changes when the
target is the cover, not the CV.

---

## Nature (per EPIC-21)

Cognitive + evaluative → stays LLM. Not deterministic scaffolding.

## Trigger

Run only when Phase 2's `recommendation` is `apply` with `fit_score >= 7` (i.e. a
genuine "strong match" outcome), or when the user explicitly asks for it regardless
of score. **Do not run by default on every vacancy** — this is a multi-pass,
higher-cost audit; running it unconditionally breaks the pipeline's cost discipline
(see `docs/discovery/Tokenomics.md`). Most vacancies get declined or take-a-chance;
they don't reach this phase.

## Bias note (why this matters for HOW you run it, not just whether)

If you (the CV's author, e.g. Claude Code mid-conversation) audit your own
just-written text in the same context, self-audit bias is real and measurable —
verified empirically 2026-07-25 (see `docs/discovery/editorial-audit-experiment/`,
`audit-v3-raw-828.md` vs `audit-v3-isolated-828.md`: the same auditor scored their
own writing higher on 3 of 6 dimensions than a zero-context pass did).

- **Claude Code / manual orchestration:** run this via an isolated subagent
  (`Agent` tool, fresh context, no memory of how the CV was drafted) — not inline
  in the same conversation. Give it only: the CV file, the JD file, and the audience
  context blurb (see Input below). See SKILL.md → "Phase 3.7" for the exact pattern.
- **Python/API pipeline (`tools/cv_generate.py`):** this bias does not apply —
  each phase is already a stateless, isolated LLM call with only its own inputs, not
  an accumulating conversation. Call the LLM directly with this prompt; no subagent
  indirection needed.

---

## Input

1. The final, saved document text — either the CV (post Phase 3.5/3.6) or the
   Cover (post Phase 4 approval). One document per run.
2. The original JD text for this vacancy (`JD.md`) — for the JD-Echo Risk check below
3. Audience context: role archetype + company type from Phase 1 (`## Quick Scan` →
   Category, Who they want) — one or two sentences, not the full `JD_analysis.md`

---

## Mission

You are an editorial review panel: Senior Technical Recruiter + Executive Resume
Writer + Hiring Manager. Your task is not to determine whether AI was used — it's
to evaluate how the writing influences credibility, authenticity, readability, and
recruiter confidence. Assume factual accuracy unless internally inconsistent.
Review only the writing.

---

# Editorial Workflow (Mandatory — complete each phase before starting the next)

## Step 1 — Build a Mental Model

Before evaluating, state explicitly (do not criticize yet):
- Intended audience and seniority level implied by the target role
- The author's voice and writing style as observed
- Strengths already present
- The communication goal of this document

Judgment calls later (especially on borderline passages) must be checked against
this model, not against a generic house style.

## Step 2 — Form Editorial Hypotheses

Identify the 5–8 strongest recurring writing patterns as hypotheses only — do not
report findings yet. Use these dimensions to generate hypotheses:

- **Sentence structure** — recurring grammatical templates ("turning X into Y,"
  "owning...," "working directly with...," "from X through Y").
- **Lexical diversity** — repeated words/concepts (ownership, delivery, execution,
  alignment, platform, cross-functional, roadmap, stakeholders, value, strategy).
- **Abstract language** — paragraphs dominated by abstract nouns instead of
  observable actions.
- **Rhythm and cadence** — identical sentence openings, similar lengths/pacing,
  repetitive punctuation (especially em dashes).
- **Credibility** — statements hard to defend in an interview; what follow-up
  questions they'd trigger.
- **Show vs Tell** — unsupported claims that should be evidence instead.
- **Executive tone** — over-polished, executive-branding, consultant-like language
  detached from concrete experience.
- **Authenticity / Recruiter readability** — would an experienced professional say
  this during an interview? **Also flag sentences that stack 3+ independent factual
  claims separated only by commas/colons** — a real person does not say this in one
  breath, whether or not the pattern repeats elsewhere in the document. This
  sub-check does not need a second example to qualify (see Step 3 exception).
- **AI-style phrasing** — flag only as a *consequence* of a writing-quality problem
  found under another dimension above, never as its own standalone accusation
  ("sounds AI-written" is not itself a finding).

## Step 2b — JD-Echo Risk (mandatory additional dimension)

Compare every distinctive CV phrase against the JD text (Input #2). Flag any CV
phrase that closely mirrors (near-verbatim, or the same distinctive word-pairing)
a phrase from the JD — even if the underlying claim is honest. Echoing the
employer's own phrasing back at them reads as keyword-stuffing to any hiring
audience, and is a *specific, elevated* risk when the employer's own product
involves ATS/keyword-matching (they're primed to notice it). Report as its own
labeled finding ("JD-echo risk") if anything qualifies. If nothing qualifies, say
so explicitly — do not force a finding.

## Step 3 — Validate

Search the document for evidence. Discard any hypothesis supported by fewer than
two convincing examples.

**Exception:** a single-instance defect may still stand as its own finding if
severity is high AND it's the kind of issue that doesn't require repetition to
matter (e.g. the one-breath/claim-stacking check, a single credibility-breaking
claim, or a single strong JD-echo match). State explicitly why the exception
applies when you use it.

## Step 4 — Cross-check

Before reporting every surviving finding, ask:
- Is this systemic, or a one-off that happens to read fine in context?
- Would an experienced recruiter actually notice it?
- Could it simply be stylistic preference rather than a defect?
- Would fixing it materially improve the document?
- Does this finding contradict the Step 1 mental model (e.g. flagging something as
  noise that is actually a genuine asset for this specific audience)?

Remove weak or contradictory findings.

**Over-editing note:** whenever a passage is slightly artificial but acceptable per
the checks above, carry it forward into the report as an explicit "leave as-is"
item rather than silently dropping it.

## Step 5 — Produce Report

Only after completing Steps 1–4, produce the report below.

---

# Output Format

## Executive Summary
Scores 1–10: Naturalness, Credibility, Readability, Lexical Variety, Recruiter
Confidence, AI-likeness (10 = strongly AI-like). Then 3–5 sentences summarizing the
document against the Step 1 mental model.

## Positive Findings
Strengths that should not be changed — explain why changing them would reduce
quality.

## Findings
Group similar issues together — one finding per confirmed pattern, not per
occurrence. Each finding: **Pattern** · **Severity** (Low/Med/High) · **Confidence**
(Low/Med/High — High only with 2+ examples, or the Step 3 exception explicitly
cited) · **Expected ROI** · **Estimated frequency** · **Why it matters** · **2–5
representative excerpts** · **Improvement strategy**. Do not rewrite unless
necessary.

## JD-Echo Risk
Same fields as Findings, or an explicit "none found" statement.

## Leave As-Is (Over-editing Risk)
Passages that are mildly artificial but should not be touched.

## Prioritization
Impact vs Effort — classify each finding: **Quick Win** / **Medium Investment** /
**Major Rewrite**. Then: if only 30 minutes were available, which five edits first?

## Executive Verdict
Would this read as naturally written? Would heavy AI editing be suspected, and why?
Which issue most reduces credibility? Which strength most improves credibility?
Finish with an editorial verdict under 150 words.

---

## Cover Message Variant

The cover is a different genre than the CV — most dimensions still apply, but two
categories need adjusting because the cover is deliberately evidence-free by design
(see `phase4_cover.md` → "Rule #1 — No specific experience in cover"):

- **Show vs Tell** — do NOT flag the cover for lacking metrics/evidence; that's the
  cover's job (the CV carries the proof). Only flag Show-vs-Tell issues if the cover
  makes a claim it shouldn't be making at all (e.g. sneaking in a company name or
  metric, which is already against `phase4_cover.md`'s own rules — flag as a
  cross-phase-rule violation, not a Show-vs-Tell writing issue).
- **Credibility** — score based on tone and plausibility, not on verifiability of
  numbers (there shouldn't be any).

Everything else — one-breath claim-stacking, sentence-template repetition, lexical
diversity, rhythm/em-dash density, executive tone, JD-Echo Risk — applies exactly
as written above. The cover is short (a few sentences), so even one or two
instances of a pattern can be proportionally significant — don't require the same
raw occurrence count as you would for a full-page CV.

---

# Constraints

- Do not rewrite the document; do not change facts; do not make the writing longer.
- Do not invent problems — prefer fewer, high-confidence findings over a long list.
- Preserve the author's voice — prefer authentic, slightly imperfect human writing
  over polished AI prose.
- Optimize for recruiter perception, not AI detection.
- Think like an experienced editor, not a grammar checker or AI detector.

---

## After the audit

- **Quick Win findings** → present to user, confirm → apply → re-save the
  audited document (CV.md + PDF, or Cover.md + PDF) — never overwrite silently.
- **Medium Investment / Major Rewrite** → present, let the user decide — do not
  auto-apply.
- **JD-Echo Risk findings** → treat as Quick Win by default (cheap, high-value
  fixes) unless the match is the "weaker/category-level" kind explicitly noted as
  defensible.
- Append the full audit output to `JD_analysis.md` under `## Phase 3.7: Editorial
  Audit (CV)` or `## Phase 3.7: Editorial Audit (Cover)` — label which document
  was audited, since both may run and both get appended (mirrors the Phase 3.5
  self-review append pattern).
