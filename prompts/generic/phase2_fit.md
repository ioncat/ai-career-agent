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
- Language: use the language specified in the active user's PROFILE.md → `## Settings` → `language` field. Default: Russian.
- Tone: analytical and objective — state conclusions directly, avoid speculation and emotional language
- Be critical and realistic. Do not soften gaps. A pet-project is NOT commercial experience.
- Output exactly four sections in this order, using the exact headers shown below. Do not skip. Do not add extra sections.
- **Jargon rule: never translate English HR/professional jargon.** Use the borrowed form as it exists in Russian-speaking professional community. Examples: "скрин" (not "экран"), "оффер" (not "предложение"), "онбординг" (not "введение в должность"), "фидбэк" (not "обратная связь"), "хайринг-менеджер" (not "нанимающий менеджер"). When in doubt — keep English jargon as-is or use the Russified transliteration, never a literal translation.

---

## Output Format

Output the following four sections in order. Use the exact `##` headers as shown.

---

**[OUTPUT SECTION 1 — Quick Scan]**

Output this block exactly as shown, filling in the placeholders.
**Display rule: Quick Scan is the ONLY section shown in chat. All other sections (Fit Breakdown, Adaptation Plan, Internal Analysis) go to JD_analysis.md only — never shown in chat.**

## Quick Scan
**Fit score:** X/10
**Recommendation:** apply / take a chance / decline
**Category:** [Primary role type from Phase 1 section 1.4] · [Remote / On-site / Hybrid]
**Who they want:** [1 sentence — the ideal candidate this vacancy targets]

**Key Barriers:** нет / [hard gaps between JD requirements and candidate — name the gap and the evidence]
**Hidden Risks:** нет / [contextual risks from role/company — NOT candidate gaps]
**Warnings:** нет / [application process risks only — see rules below]

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
- -1.0 for significant experience level mismatch (seniority, domain depth)
- Cap at 9.5 — no perfect scores

**Key Barriers** — candidate-side hard gaps (be specific, name the evidence):
- Missing commercial experience where JD explicitly requires it (pet-projects don't qualify)
- Below minimum experience threshold by a significant margin
- Missing core domain or hard skill where JD states it as mandatory
- Significant seniority mismatch (JD requires senior, candidate is junior — or reverse)

**Hidden Risks** — role/company context signals (NOT candidate gaps):
- Company maturity: early-stage, no confirmed funding, agency structure, high turnover signals
- Role environment: high autonomy + no process = chaos risk
- Role scope may expand rapidly beyond stated description
- Domain or industry the company is entering (unfamiliar territory for everyone)

**Blockers** (hard knockout — automatically sets Recommendation to "decline"):
- Mandatory relocation without remote option
- Hard domain or certification requirement the candidate lacks
- Mandatory language threshold with verification (C1+ test)
- Specific license / clearance / permit
- Minimum experience significantly above candidate's
- Mandatory hard skill the candidate lacks (e.g. "must have X certification", "must speak X language")

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
- No salary mentioned
- No public info about company

If career track diverges significantly from candidate's target role type:
add: `**Track note:** роль отличается от целевого трека — [1 sentence on the nature of difference]`

---

**[OUTPUT SECTION 2 — Fit Breakdown]**

Mandatory table. Assess the 6–10 most significant JD requirements.

## Fit Breakdown

| Требование из JD | Статус | Опыт кандидата |
|-----------------|--------|----------------|
| [requirement] | ✅ / ⚠️ / ❌ | [specific evidence from profile, or "нет данных"] |

**Status rules — be strict:**
- ✅ = direct commercial experience confirmed in profile
- ⚠️ = partial: pet-projects only / shorter than required / adjacent/indirect experience
- ❌ = missing — no evidence in profile

**Pet-projects are NEVER ✅ if JD requires commercial experience. Always ⚠️ at best.**

Skip boilerplate requirements (teamwork, communication, responsibility). Focus on substantive ones.

---

**[OUTPUT SECTION 3 — Adaptation Plan]**

## Adaptation Plan

**If Recommendation is "decline":**

List 2–3 structural reasons why this vacancy is not worth the time investment.
Focus on gaps that cannot be bridged with reframing alone.

**If Recommendation is "apply" or "take a chance":**

Provide 3–5 concrete reframing actions. Each action = specific and actionable.

Lead with the most critical gap or mismatch — what to address first.
Use candidate's actual experience from profile to guide what to surface and how.

Format each action as:
- **[Action label]:** [Specific instruction — what to change, what to emphasize, exact framing]

---

**[OUTPUT SECTION 4 — Internal Analysis]**

*For record-keeping. Kept in JD_analysis.md for deep reference.*

## Internal Analysis

### Fit Dimensions

| Измерение | Оценка /10 | Комментарий |
|-----------|-----------|---------|
| Domain fit | | |
| Execution fit | | |
| Communication/coordination fit | | |
| Hard skills fit | | |
| Seniority fit | | |
| **Overall fit** | | |

### Detailed Assessment

**Сильные совпадения** — где кандидат чётко попадает в цель:
- [конкретные совпадения с доказательствами]

**Слабые места** — пробелы и недостающий опыт:
- [список пробелов]

**Transferable experience** — реальный опыт, который можно переформатировать:
- [список с конкретными примерами]

**Likely recruiter objections** — что вызовет сомнение на скрине:
- [список возражений]

**Best narrative for positioning:**
[1–2 предложения: лучший угол позиционирования для этой конкретной вакансии]

### Summary

- **Кого реально ищет компания:** [1 предложение]
- **Почему кандидат подходит / не подходит:** [1 предложение]
- **Как должно выглядеть идеальное CV для этой вакансии:** [2–3 предложения]
