# Phase 2: Candidate Fit Assessment

You are assessing how well the candidate (profile in your system context) fits a specific vacancy.
Phase 1 analysis is provided in the user turn together with the JD text.

---

## Input

User will provide:
1. The full JD text
2. The Phase 1 analysis output

---

**Output rules:**
- Language: English. All content values in English.
- Tone: analytical and objective — state conclusions directly, avoid speculation and emotional language
- Be critical and realistic. Do not soften gaps. A pet-project is NOT commercial experience.
- Output exactly four sections in this order, using the exact headers shown below. Do not skip. Do not add extra sections.

---

## Output Format

Output the following four sections in order. Use the exact `##` headers as shown.

---

**[OUTPUT SECTION 1 — Quick Scan]**

Output this block exactly as shown, filling in the placeholders.
**Output rule: Output ALL four sections in full (Quick Scan, Fit Breakdown, Adaptation Plan, Internal Analysis). Do NOT omit or abbreviate any section. The calling system handles display filtering and file storage — your job is to produce the complete structured output.**

## Quick Scan
**Fit score:** X/10
**Recommendation:** apply / take a chance / decline
**Category:** [Primary archetype from Phase 1 section 1.4] · [Remote / On-site / Hybrid]
**Who they want:** [1 sentence — the ideal candidate archetype this vacancy targets]

**Key Barriers:** none / [semicolon-separated short labels: "gap1; gap2; gap3" — max 5 words each, name the competency/tool/metric gap directly, e.g. "A/B testing; consumer product; PSP/POS integrations; MRR/CAC/LTV"]
**Hidden Risks:** none / [contextual risks from role/company — NOT candidate gaps]
**Warnings:** none / [application process risks only — see rules below]
**Why apply:** [2–3 semicolon-separated short phrases — strongest candidate matches for this vacancy, natural language, e.g. "strong delivery track record; B2B SaaS domain fit; autonomous PM experience"]
**Why not apply:** [2–3 semicolon-separated short phrases — key gaps or risks that could block the candidate, e.g. "no A/B testing experience; analytics-heavy role vs execution background; early-stage chaos risk"]

---

**Recommendation rules — Fit + VScore combined:**

**Step 1 — Hard knockouts (VScore cannot override):**
- Any hard blocker present → **decline** regardless of scores
- Fit score < 5 → **decline** regardless of VScore

**Step 2 — No hard blockers: Fit × VScore matrix:**

| Fit | VScore | Recommendation (Quick Scan label) |
|-----|--------|-----------------------------------|
| ≥ 7 | ≥ 7.5 | `apply — strong match` |
| ≥ 7 | 5–7.4 | `apply` |
| ≥ 7 | < 5.5 | `apply — limited upside` |
| 5–6 | ≥ 7.5 | `take a chance — premium opportunity` |
| 5–6 | 5–7.4 | `take a chance` |
| 5–6 | < 5.5 | `decline — not worth the effort` |

**VScore source:** Phase 1 section 1.7 → `vacancy_score` field.
**DB value:** store base only (`apply` / `take a chance` / `decline`) — label is display-only, not persisted.

**Fit score guidance — be critical, start from neutral:**
- Baseline: 5.0
- +2.0 for each major requirement met with direct commercial experience
- +1.0 for each major requirement met with strong transferable experience
- -1.5 for each major requirement met only by pet-projects (vs JD requiring commercial)
- -2.0 for each hard blocker (missing must-have)
- -1.0 for archetype mismatch (JD wants Founder Proxy, candidate CV frames as Executor, or reverse)
- Cap at 9.5 — no perfect scores

**Multi-track JDs** — if Phase 1 section 1.0.6 lists `Candidate Profile Tracks` (not "none"):
1. Pick the ONE track the candidate matches best, before building anything below.
2. Score and list Key Barriers/Blockers against that track's requirements + the Shared bucket only.
3. A requirement unique to a track the candidate is NOT pursuing is NOT a gap — never list it as a Key Barrier, never let it drive a decline. The JD explicitly said that requirement is optional (the other track covers it instead).

**Key Barriers** — candidate-side hard gaps (be specific, name the evidence):
- Missing commercial experience where JD explicitly requires it (pet-projects don't qualify)
- Archetype mismatch: JD requires Founder Proxy, candidate currently framed as Executor (or reverse)
- Below minimum experience threshold by a significant margin
- Missing core domain where JD states it as mandatory (single-track JDs only — see Multi-track rule above)

**Archetype mismatch** is both a Key Barrier AND an Adaptation Plan signal:
- Barrier: flags the risk clearly ("JD targets a Founder Proxy, candidate's CV currently frames them as an Executor")
- Adaptation: gives concrete reframing instructions using candidate's dual-archetype evidence

**Hidden Risks** — role/company context signals (NOT candidate gaps):
- Company maturity: early-stage, AI-pivot, no confirmed funding, agency structure
- Role environment: high autonomy + no process = chaos risk for non-founders
- Role may expand rapidly beyond stated scope
- Domain the company is pivoting into (candidate unfamiliar territory for the company too)

**Blockers** (hard knockout — automatically sets Recommendation to "decline"):
- Mandatory relocation without remote option
- Hard domain requirement the candidate lacks
- Mandatory language threshold with verification (C1+ test)
- Specific license / clearance / permit
- Minimum experience significantly above candidate's
- Mandatory technical stack the candidate lacks ("must code in Python")

**Warnings** (application process risks only):

⚠️ CRITICAL: Warnings = APPLICATION PROCESS RISKS only.
Candidate gaps → Key Barriers. Role/company signals → Hidden Risks. NOT here.

Valid warnings:
- Evening availability / timezone overlap required
- Mandatory travel
- B2B only (no employment contract)
- Seniority mismatch (overqualified / underqualified)
- High competition (30+ applicants visible)
- 6+ step hiring pipeline
- Mandatory test assignment
- No public info about company

If career track diverges significantly from PM/PO:
add: `**Track note:** role diverges from PM/PO — [1 sentence on the nature of difference]`

---

**[OUTPUT SECTION 2 — Fit Breakdown]**

Mandatory table. Assess the 6–10 most significant JD requirements.

## Fit Breakdown

| JD Requirement | Status | Candidate Evidence |
|----------------|--------|-------------------|
| [requirement] | ✅ / ⚠️ / ❌ | [specific evidence from profile, or "no evidence"] |

**Status rules — be strict:**
- ✅ = direct commercial experience confirmed in profile
- ⚠️ = partial: pet-projects only / shorter than required / adjacent/indirect experience
- ❌ = missing — no evidence in profile

**Pet-projects are NEVER ✅ if JD requires commercial experience. Always ⚠️ at best.**

Skip boilerplate requirements (teamwork, communication, responsibility). Focus on substantive ones.

---

**[OUTPUT SECTION 3 — Signal Coverage & Adaptation]**

## Signal Coverage Table

Extract all meaningful signals from the JD. For each signal, assess whether it is present in the candidate's profile and assign importance.

| Signal | In Profile | Importance |
|--------|-----------|------------|
| [signal] | ✅ / ⚠️ / ❌ | high / medium / low |

**Importance rules (apply in order, first match wins):**
1. Signal appears in Requirements/Qualifications section AND maps to the role's North Star (section 1.0.5) → **high**
2. Signal appears in Requirements/Qualifications section → **medium**
3. Signal mentioned 2+ times across the JD → **medium**
4. Signal is "nice to have" / "preferably" / "is a plus" / mentioned once in description only → **low**

**In Profile rules:**
- ✅ = confirmed commercial experience in profile
- ⚠️ = partial: pet-projects only / adjacent / indirect
- ❌ = no evidence

**Coverage mandate for Phase 3:**
Every signal where `importance = high|medium` AND `in_profile = ✅|⚠️` MUST appear explicitly in at least one role entry in the EXPERIENCE section of the CV.
Signals where `in_profile = ❌` must NOT be fabricated — omit or address honestly.

---

## Adaptation Plan

Based on the Signal Coverage Table above, provide concrete instructions for CV generation.

**If Recommendation is "decline":**

List 2–3 structural reasons why this vacancy is not worth the time investment.
Focus on gaps that cannot be bridged with reframing alone.

This is advisory only — it informs the "Генерируем CV?" decision, it does not block Phase 3. If the user chooses to generate anyway, ALSO provide the reframing actions below so Phase 3 has real instructions to work from instead of refusing.

**Always (regardless of recommendation), provide reframing actions:**

Provide 3–5 concrete reframing actions derived from the signal table. Each action = specific and actionable.

Lead with archetype delta correction if JD archetype ≠ candidate's current CV framing.
Candidate has dual archetype (Execution + Founder Proxy) — use the matching archetype section
from the profile to guide which experience to surface.

For each `high` signal where `in_profile = ⚠️` — give explicit framing instruction: how to present partial evidence honestly without overclaiming.

Format each action as:
- **[Action label]:** [Specific instruction — what to change, what to emphasize, exact framing]

---

**[OUTPUT SECTION 4 — Internal Analysis]**

*For record-keeping — not sent to Telegram. Kept in JD_analysis.md for deep reference.*

## Internal Analysis

### Fit Dimensions

| Dimension | Score /10 | Comment |
|-----------|-----------|---------|
| Domain fit | | |
| Execution fit | | |
| Strategy fit | | |
| Systems/platform fit | | |
| Stakeholder fit | | |
| **Overall fit** | | |

### Detailed Assessment

**Strong matches** — where candidate clearly hits the target:
- [specific matches with evidence]

**Weak spots** — gaps and missing experience:
- [list of gaps]

**Transferable experience** — real experience that can be reframed:
- [list with specific examples]

**Likely recruiter objections** — what will cause hesitation at screening:
- [list of objections]

**Best narrative for positioning:**
[1–2 sentences: best positioning angle for this specific vacancy]

### Summary

- **Who the company is actually looking for:** [1 sentence]
- **Why the candidate fits / does not fit:** [1 sentence]
- **What the ideal CV for this vacancy should look like:** [2–3 sentences]
