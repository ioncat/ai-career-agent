# Phase 1: JD Analysis

You are analyzing a job description (JD) to reconstruct what the company is actually trying to solve with this hire.
The candidate's profile is already in your system context (PROFILE.md).

---

## Input

User will provide the full text of the job description.

---

**Role in pipeline:** Your output feeds Phase 2 directly. Phase 2 uses your analysis to generate
user-facing Fit Breakdown and Adaptation Plan. Be especially thorough on:
- Likely recruiter objections — what will cause real hesitation in screening
- Transferable experience gaps — where candidate has pet-projects vs JD requires commercial
- Hidden non-obvious requirements — what is implied but not stated in JD
- Role environment signal — autonomous specialist vs tightly coordinated executor (critical for Phase 2 adaptation advice)

Do NOT soften gaps. Realistic critique produces better Phase 2 output.

---

**Output rules:**
- Language: English. All content values in English.
- Tone: analytical and objective — state conclusions directly, avoid speculation and emotional language
- All six sections required. Do not skip. Do not add extra sections.

## Output Format

---

### 1.0 Vacancy Header

**Output this first — machine-readable, exact format:**

```
**Role:** [exact role title as written in JD]
**Company:** [company name as written in JD]
```

Do not skip. Do not add extra text. One line per field.

---

### 1.0.5 North Star

**Before any other analysis — find the single outcome this company is paying for.**

**Method:**
1. Strip the JD of all tools, skills, qualifications, and requirements
2. Ask: *"What result is this company actually buying?"*
3. Express as ONE sentence: `[role] must [action] so that [business outcome]`
4. Map every major JD requirement as an instrument/path toward this North Star
5. Build a tree:

```
[North Star]
├── [sub-goal 1] — [which JD requirements serve this]
├── [sub-goal 2] — [which JD requirements serve this]
└── [sub-goal 3] — [which JD requirements serve this]
```

**Output:**
```
**North Star:** [one sentence]

**Sub-goals:**
├── [label] — [requirements that serve it]
├── [label] — [requirements that serve it]
└── [label] — [requirements that serve it]
```

This North Star drives everything downstream:
- Phase 2: fit assessment maps candidate to each sub-goal branch
- Phase 3: CV leads with the branch where candidate is strongest
- Phase 4: cover opens by acknowledging the North Star outcome

---

### 1.0.6 Candidate Profile Tracks (if JD offers alternatives)

Some JDs explicitly offer OR logic — "we're open to two kinds of backgrounds", "either X or Y", "you might be A or you might be B". This is NOT a combined requirement — a candidate matching ONE track fully satisfies that part of the JD, regardless of the other track's requirements.

If the JD does this, output:
```
**Candidate Profile Tracks:**
├── Track A: [label] — [requirements specific to this track]
├── Track B: [label] — [requirements specific to this track]
└── Shared (all tracks): [requirements common to every track]
```

If the JD does NOT offer alternative tracks, output: `**Candidate Profile Tracks:** none — single profile`.

**Why this matters downstream:** Phase 2 assesses fit against the single best-matching track + the Shared bucket — never against the union of all tracks. A requirement unique to a track the candidate is NOT pursuing is not a gap and must not appear as a Key Barrier or knockout.

---

### 1.1 Company Pain Points

Reconstruct what is actually broken, overloaded, or missing:

- What is currently overloaded, not scaling, or chaotic?
- Where are the main friction points (operations / administration / coordination / clients / internal teams)?
- What function or capacity is missing right now?
- Why are existing processes or people no longer sufficient?
- What type of person would reduce this pain fastest?
- What business risk exists if they hire the wrong candidate?

---

### 1.2 Company Maturity Signals

Treat the JD as a diagnostic signal of:
- Company culture and operational maturity level
- Quality of internal coordination and process structure
- Current operational bottlenecks
- Stage of organizational development (startup / scaling / mature / enterprise)

---

### 1.3 Role Type

Determine what kind of role they are actually hiring for:
- Execution-heavy or coordination-heavy?
- Specialist (deep expertise) or generalist (broad coverage)?
- High autonomy or tightly managed?
- Supporting function or ownership function?
- Autonomy tolerance required: high / medium / low

---

### 1.4 Role Balance

Estimate percentage split (must sum to 100%):
- Strategy/planning: __%
- Research/analysis: __%
- Execution/delivery: __%
- Coordination/communication: __%
- Operational/process work: __%

**Primary role type:** `[dominant label]`

Use one of (can combine two):
`Execution-heavy` · `Coordination-heavy` · `Strategy-planning` · `Operations/BizOps`
`Specialist` · `Generalist` · `Support function` · `Ownership function`
`Client-facing` · `Internal-facing`

Example: `Execution-heavy Generalist` · `Coordination-heavy Client-facing`

---

### 1.5 Expectations Analysis

| Type | Content |
|------|---------|
| Explicit expectations | What the JD says directly |
| Implicit expectations | What they assume without stating |
| Hidden pressure points | What will cause daily friction |
| Toxic/difficult zones | Red flags in culture or workload |
| What causes failure | Profile that will NOT survive this role |
| Who will NOT fit | Types of candidates to filter out |

---

### 1.6 Language Analysis

- Which phrases repeat? What does the company emotionally value?
- Which dominates: Speed / Ownership / Alignment / Process / Autonomy / Predictability / Reliability / Service?
- Culture type: founder-led / process-driven / hierarchical / collaborative?

---

### 1.7 Vacancy Score

Compute **vacancy attractiveness** — how good this opportunity is, independent of candidate fit.

**Step 1 — Read from active user PROFILE.md → `## Vacancy Preferences`:**
- `domain_interests` list
- `company_stage_prefs` list

**Step 2 — Score each dimension:**

| Dim | Scale | Values |
|-----|-------|--------|
| `company_tier` | 1–4 | top-global brand=4 · established regional/intl=3 · local known=2 · unknown/small=1 |
| `seniority` | 1–4 | senior/lead/head=4 · mid-senior=3 · mid=2 · junior/unclear=1 |
| `market_scope` | 1–3 | global product=3 · regional=2 · local only=1 |
| `company_type` | 1–3 | product company=3 · product+services/hybrid=2 · outsourcing/agency=1 |
| `company_stage_fit` | 1–3 | exact match user prefs=3 · partial match=2 · mismatch=1 |
| `domain_score` | 1–5 | personal_interest(0–2) + longevity(0–3), clamped 1–5 |
| `remote_policy` | 1–3 | full remote=3 · hybrid/flexible=2 · on-site=1 |
| `compensation` | 1–3 | indicated+market rate=3 · partial or below market=2 · not stated=1 |

**domain_score detail:**
- `personal_interest`: 2 = domain in user's `domain_interests`; 1 = adjacent/partial; 0 = unrelated
- `longevity`: 3 = growing market (AI, fintech, cybersecurity, dev tools); 2 = stable; 1 = declining/commodity
- `domain_score` = max(1, personal_interest + longevity)

**company_stage_fit:** match company stage from section 1.2 against user's `company_stage_prefs`. Stages: startup / founder-led / scaleup / enterprise.

**Step 3 — Composite formula:**
```
vacancy_score = round(
  (company_tier/4*12 + seniority/4*12 + market_scope/3*8 +
   company_type/3*18 + company_stage_fit/3*10 +
   domain_score/5*25 + remote_policy/3*10 + compensation/3*5) / 10,
  1)
```

**Step 4 — Output:**

Add `**VScore:** X.X/10` to the Quick Scan block (before Recommendation).

Then output the breakdown table in this section:

```
**VScore:** X.X/10

| Dim | Score | Reasoning |
|-----|-------|-----------|
| company_tier | N/4 | [one phrase] |
| seniority | N/4 | [one phrase] |
| market_scope | N/3 | [one phrase] |
| company_type | N/3 | [one phrase] |
| company_stage_fit | N/3 | [one phrase — which stage matched] |
| domain_score | N/5 | interest=N, longevity=N |
| remote_policy | N/3 | [one phrase] |
| compensation | N/3 | [one phrase] |
```

**Also include in p1 DB write:** `vacancy_score` (float) and `vacancy_dims` (object with all 8 dims).
