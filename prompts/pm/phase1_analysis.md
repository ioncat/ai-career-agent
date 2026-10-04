# Phase 1: JD Analysis

You are analyzing a job description (JD) to reconstruct what the company is actually trying to solve with this hire.
The candidate's profile is already in your system context (PROFILE.md).

---

## Input

User will provide the full text of the job description. If a `**Listed salary:** ...` line appears before the JD text, it comes from site/RSS metadata the JD body itself may not mention — treat it as known, real compensation data for the `compensation` dim in §1.7 (Step 4), not as "not stated." If that line is absent, compensation really is unknown — do not invent a number.

If a `**Known company:** ...` line appears before the JD text, it was extracted structurally from the page (URL/DOM), not from the JD body — some postings never name the employer in the ad copy itself. Use it verbatim as the `**Company:**` value in §1.0 below, even if the JD body itself never states it. Never write a placeholder like "[not disclosed in JD]" when this line is present. If the line is absent AND the JD body doesn't name the company either, write `Not stated`.

---

**Role in pipeline:** Your output feeds Phase 2 directly. Phase 2 uses your analysis to generate
user-facing Fit Breakdown and Adaptation Plan. Be especially thorough on:
- Likely recruiter objections — what will cause real hesitation in screening
- Transferable experience gaps — where candidate has pet-projects vs JD requires commercial
- Hidden non-obvious requirements — what is implied but not stated in JD
- Company archetype signal — Founder Proxy vs Executor (critical for Phase 2 adaptation advice)

Do NOT soften gaps. Realistic critique produces better Phase 2 output.

---

**Output rules:**
- Language: English. All content values in English.
- Tone: analytical and objective — state conclusions directly, avoid speculation and emotional language
- All sections listed below (1.0 through 1.7) are required. Do not skip. Do not add extra sections.

## Output Format

---

### 1.0 Vacancy Header

**Output this first — machine-readable, exact format:**

Detect the language of the JD body text (requirements and responsibilities sections). Ignore: URL, job board page title, company name, location fields. If the JD mixes languages, use the dominant language of the requirements/responsibilities sections. Output ISO 639-1 code (e.g. `en`, `uk`, `ru`, `es`, `de`). This value is consumed by Phase 3 as the default CV language — accuracy matters.

```
**Role:** [exact role title as written in JD]
**Company:** [known company from the **Known company:** line if present, else company name as written in JD, else "Not stated"]
**JD Language:** [ISO 639-1 code of JD body text]
```

Do not skip. Do not add extra text. One line per field.

---

### 1.0.5 North Star & Branches

**Two-stage, judgment-based process (confirmed 2026-09-21/23 — see `docs/discovery/north-star-signal-tree-discovery-2026-09-21.md` for the full reasoning). Complete Stage 1 fully before starting Stage 2 — don't interleave "what's the core pain" with listing individual requirements in the same breath.**

#### Stage 1 — North Star search

Read the whole JD once, holistically, before extracting individual requirements.

**Requirements & Qualifications outweighs Key Responsibilities (confirmed 2026-09-23, vacancy #1680).** Requirements are the gate to being hired at all — fail to meet one and the candidate is never considered. Responsibilities describe what the hire does only after clearing that gate. When weighing what the JD is *actually* buying, a Requirements/Qualifications line describing the *kind* of candidate needed (a domain, a complexity level, a working style) outweighs a longer list of Responsibilities bullets describing the day-to-day process — do not default to whichever section has more bullets or more words. Found live: a 4-bullet Key Responsibilities section (all describing a translation/delivery process) was initially weighted over a single Requirements bullet ("Proven experience working on Enterprise platforms or complex B2B systems") purely because it had more text — the Requirements bullet was the JD's real screening filter and the correct North Star anchor.

**Check the JD's own emphasis formatting.** If Requirements & Qualifications selectively bolds/emphasizes only some bullets or phrases (not a uniform per-bullet-label convention applied to every item — that's just formatting, not a signal), treat that selective emphasis as a first-party priority signal from the JD's own author, on top of explicit "core pain" language and repetition. Distinguish it from formatting conventions applied uniformly (e.g. every Key Responsibilities label bolded) which carry no signal.

1. Check whether the company states its core pain/problem/goal explicitly — an intro paragraph, a "why this role exists," a "what success looks like" section. Mature product companies often do this plainly; when they do, use it directly rather than re-deriving it. Cross-check it against Requirements & Qualifications (per the priority rule above) rather than accepting it at face value — an intro paragraph can read as an explicit purpose statement while still being generic boilerplate that doesn't reflect the JD's real screening filter.
2. If no explicit statement exists: strip the JD of tools, skills, qualifications, and requirements, then ask *"What result is this company actually buying?"* — check whether the responsibilities cluster around one recognizable underlying problem even though it's never stated outright. If they do, synthesize the North Star from that cluster.
3. **If they don't cluster around anything recognizable — conclude "not found" and stop.** This is a legitimate, expected outcome, not a search failure — common for outsourcing/staffing/agency-type postings where the work is process-shaped rather than pain-shaped. Do not force a synthetic North Star onto a JD that doesn't have one. Judge the actual text, not the company type alone — a product company usually has a real North Star, but not always, and an outsourcing/staffing posting doesn't always lack one either.

**Output:**
```
**North Star:** [role] must [action] so that [business outcome] — OR — not found: requirements only, no unifying pain identified
```

#### Stage 2 — Branches (only after Stage 1 has completed and produced its result)

Map every major JD requirement onto a **branch** — a meaningful cluster, not one branch per bullet point. **A branch naming several distinct JD asks (e.g. "coordinate with dev, design, marketing, compliance, and support") should split into separate branches per distinct function, not stay bundled as one** — a single bundled branch can't represent that some of its parts have real candidate evidence and others don't; this was the direct cause of a real false-positive bug (a narrow, non-matching fact got pulled in to answer an entire bundled branch on the strength of one word). Decompose here, don't defer it to Phase 2.

**If North Star found (Stage 1):** for EACH branch, make an explicit judgment call — not a text-position or frequency proxy — *is this branch part of the North Star's own core, unsolved responsibility, or a secondary/supporting requirement attached from elsewhere in the JD?* Mark it `central` or `secondary` directly.

**If North Star not found (Stage 1):** still build the branch list (every JD still has requirements to map), but mark every branch `no North Star` instead of central/secondary — there is no core pain for a branch to be central or secondary to. Phase 2 falls back to flat importance tiers only (see `phase2_fit.md`).

**Output:**
```
**Branches:**
├── [label] — [central | secondary | no North Star] — [requirements that serve it]
├── [label] — [central | secondary | no North Star] — [requirements that serve it]
└── [label] — [central | secondary | no North Star] — [requirements that serve it]
```

This drives everything downstream:
- Phase 2: the Signal Coverage Table is built as branch-tagged rows under this same tree, not regenerated independently — one row per distinct JD ask, tagged with its branch. Candidate-side distinctiveness is judged separately per branch there — a branch only becomes the CV's lead when it's BOTH central AND distinctive, not on centrality alone.
- Phase 3: CV leads with the branch that wins both judgments; other central branches get covered for completeness, not led with.
- Phase 4: cover opens by acknowledging the North Star outcome (or, when not found, the category-level ask instead).

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
- Where are the main friction points (business / product / engineering / delivery / clients)?
- What is missing in product ownership right now?
- Why are existing processes or people no longer sufficient?
- What type of person would reduce this pain fastest?
- What business risk exists if they hire the wrong candidate?

---

### 1.2 Company Maturity Signals

Treat the JD as a diagnostic signal of:
- Company and product culture maturity level
- Quality of product/business/engineering interaction
- Current operational bottlenecks
- Stage of product and organizational development

---

### 1.3 Role Archetype

Determine what kind of PM they are actually hiring:
- Delivery-oriented or discovery-oriented?
- Execution-heavy or strategy-heavy?
- Platform/system PM or feature PM?
- Founder proxy, coordinator, product lead, or backlog owner?
- Autonomy tolerance required: high / medium / low?

---

### 1.4 Role Balance

**Six-axis taxonomy (empirically derived 2026-09-06 — keyword frequency + TF-IDF clustering + LLM open-coding, triangulated across 628 real PM/PO job descriptions; full methodology: `docs/discovery/role-balance-taxonomy-discovery-2026-09-06.md`).** These are the canonical field names, used verbatim in `analysis_json.p1.role_balance`:

- **Strategy** (`strategy`) — deciding WHAT to build and why: vision, roadmap ownership, prioritization, OKRs, positioning
- **Discovery** (`discovery`) — customer/user research, market/competitive research, hypothesis validation, problem framing
- **Delivery** (`delivery`) — turning a decision into a shipped thing: backlog management, requirements/specs/user stories/acceptance criteria, sprint execution, release/launch coordination
- **Growth** (`growth`) — improving something ALREADY shipped through data: experiments, A/B testing, cohort/funnel/retention/conversion analysis, LTV/CAC, activation/monetization work
- **Stakeholder** (`stakeholder`) — cross-functional alignment and communication: engineering, design, business, leadership, external partners
- **Operational** (`operational`) — process design, automation, efficiency, risk/compliance, day-to-day operational ownership

**Definitional note (avoid the old "execution" ambiguity):** "Strategy" decides what and why. "Delivery" ships it. "Growth" improves it afterward using data — do not fold Growth into Delivery just because both involve "doing" something; a JD asking for experiments/cohorts/A-B-testing/retention work is Growth, not generic Delivery. If a JD's language genuinely spans two axes, split the percentage across them rather than forcing one pick.

Estimate percentage split (must sum to 100%):
- Strategy: __%
- Discovery: __%
- Delivery: __%
- Growth: __%
- Stakeholder: __%
- Operational: __%

**Primary archetype:** `[balance-intensity] [role-shape]`

**Two closed lists — exactly one term from each, nothing else** (tightened 2026-09-21 after a DB audit found 81 distinct, inconsistent free-text values across 131 vacancies — root cause: this field and §1.3's free discussion above bleed vocabulary into each other when generated in the same response):
- **balance-intensity** = the single highest-% axis from the split just estimated above, canonical name + `-heavy` — nothing else: `Strategy-heavy` · `Discovery-heavy` · `Delivery-heavy` · `Growth-heavy` · `Stakeholder-heavy` · `Operational-heavy`
- **role-shape** (from §1.3's judgment): `Platform/Systems PM` · `Feature PM` · `Founder proxy` · `Delivery-coordinator` · `Operations/BizOps` · `Technical PM` · `Growth PM`

**Do NOT invent modifiers outside these two lists** (e.g. "Execution-heavy" is invalid — the canonical term for that meaning is "Delivery-heavy"). **Do NOT combine more than one term per list.**

Example: `Delivery-heavy Platform/Systems PM`

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
- Which dominates: Speed / Ownership / Alignment / Process / Autonomy / Predictability / Innovation?
- Culture type: founder-led / engineering-led / process-driven?

---

### 1.7 Vacancy Score

Compute **vacancy attractiveness** — how good this opportunity is, independent of candidate fit.

**Step 1 — Read from the active user's PROFILE.md, Vacancy Preferences section:**
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

**Do not compute this by hand.** Once the 8 dims are scored, run it through the actual deterministic script and use that output verbatim — for both the `**VScore:** X.X/10` line below and the `vacancy_score` field in the DB write (`vacancy_track.py update-json`). Manual arithmetic on this formula has produced a wrong prose value while the DB got the right one, twice (vacancies #1268, #1192, 2026-08-25) — the two numbers must come from a single computation, not be derived twice from memory.

```bash
python -c "
from contracts.pipeline import VacScoreDims
from core.vacscore import compute_vacancy_score
print(compute_vacancy_score(VacScoreDims(company_tier=N, seniority=N, market_scope=N, company_type=N, company_stage_fit=N, domain_score=N, remote_policy=N, compensation=N)))
"
```
Substitute the 8 scored dims for `N`, run it, use the printed number everywhere below.

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
