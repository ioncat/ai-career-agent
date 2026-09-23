# Phase 3: CV Generation (Draft)

Generate a tailored CV for the candidate based on the JD analysis.
The candidate's full profile and experience are in your system context (PROFILE.md).

**This is a DRAFT — it will NOT be shown to the user. Phase 3.5 self-review runs next.**

---

## Input

User will provide:
1. JD text
2. JD_analysis.md content (Phase 1 + Phase 2 output)
3. Target language (English / Ukrainian / both)
4. Selected candidate name variant

---

## NON-NEGOTIABLE Rules

1. **NEVER copy-paste JD phrases verbatim** — absorb meaning, rewrite in natural language
2. **NEVER change actual job titles** — dishonest and verifiable
3. **NEVER fabricate experience** — if it doesn't exist, don't claim it
4. **NEVER remove a work experience entry** — every job in PROFILE.md stays in CV. Early career entries (before the cutoff year in PROFILE.md) omitted by default unless directly relevant. This includes the current/most recent role — never drop it even if it looks less relevant to the JD than an older role.
4b. **EXPERIENCE order is ALWAYS strict reverse-chronological — most recent role first.** Never reorder by relevance or "lead with the strongest match." If the Adaptation Plan says "lead with X," that means strengthen X's framing/word choice within its own chronological slot, not move it to the top of the list. Found live on vacancy #922: HostiServer PO (2018–2021) was moved to the top over InsulaLabs/Marketplace (2022–2025), breaking chronology candidates and recruiters both expect by default.
5. **CV language = input language** — English input → English CV; Ukrainian input → Ukrainian CV
6. **Do not self-apply "Senior"** unless officially held
7. **Avoid AI clichés** — "AI-Native", "AI-Driven mindset" etc.
8. **Avoid first-person pronouns** — standard CV convention
9. **NEVER use third-person verbs anywhere in the CV** — no "Understands", "Knows", "Applies", "Works", "Brings", "Has", "Reads", "Holds", "Designs" (present-tense, implied-subject form). CV language = headline-style (no subject) or past-tense action verbs. Applies to Summary, bullets, and all prose. Companion rule to #8 — both are voice rules, check them together on every pass, especially the Summary section where they're most often missed.
   - **Non-English output (Ukrainian, Russian, etc.):** the same rule applies, but the surface pattern looks different — watch for **third-person** "Має [experience]" / "Є [adjective]" (= "Has"/"Is", implied-subject present tense) and bare adjective-as-headline claims like "Технічно грамотний:" / "Досвідчений:" standing alone as a self-description. Both read as third-person self-praise in Ukrainian, same violation as the English list above. Convert to parallel past-tense action verbs instead (e.g. "Керував", "Координував", "Читав і проєктував" — matches the already-correct "Поєднував" pattern). Found live on vacancy #937.
     - **"Маю [experience]" (first-person "I have") is NOT the same violation — do not flag it.** The banned pattern is specifically third-person implied-subject ("Має" = he/she/it has). First-person "Маю"/"Я маю" is a normal, allowed CV construction in Ukrainian. Clarified 2026-08-10 (vacancy #1090) after this distinction was missed on first pass.
9c. **Avoid bare capability framing ("Able to X", "Can X").** These assert raw capability, not demonstrated practice. Prefer a past-tense action verb ("Translated..."), a headline-style noun phrase ("Experience translating..."), or "Experienced in X-ing" (needs the preposition — "Experienced translating" without "in" is ungrammatical). Found on vacancy #1511: "Able to translate business needs..." read as a bare skill claim instead of proven experience.
10. **"Built" implies coding** — use "Led design and delivery", "Owned", "Coordinated" for PM work
11. **Metrics belong in Key Results only** — do not duplicate in prose
12. **NO Skills section**
13. **NO Education section**
14. **NO Location**
15. **GitHub link — never include in contacts.** Portfolio site (from PROFILE.md contacts) already covers it. GitHub URL is redundant and creates noise.
16. **Summary section header — language rule:** English CV → use `SUMMARY` header. Ukrainian CV → NO header, summary text flows directly after headline/contacts. "РЕЗЮМЕ" as a section label is redundant inside a CV.
17. **Domain context (e.g. iGaming, fintech, e-commerce) — include only if JD is from that domain.** Never volunteer domain in a generic or unrelated vacancy.
18. **Add `---` separator between each job entry** for visual spacing in PDF output.
19. **NEVER use plural forms for things built or owned: no "systems", "portals", "platforms".** Name individual items specifically (singular each), or use "product" / "product suite" as a collective. Exception: "products" is allowed only when referring to multiple distinct products in context.
20. **CERTIFICATIONS: include only "Certified AI-Empowered SAFe® Product Owner/Product Manager" by default.** Add others only when directly relevant to the specific vacancy.
20b. **Key results block is mandatory for EVERY role in EXPERIENCE, including the most recent/current one.** Do not skip it for roles that read as execution-only or too short/new to have metrics. Check PROFILE.md's main entry for that company AND every "Additional Evidence" section for that company before concluding there is genuinely no outcome evidence — that is the only valid reason to omit it for a given role. Found missing live on two roles in one CV (vacancy #1494, 2026-09-07): the current role and a 5-month execution role that had a KPI figure sitting directly in PROFILE.md's Experience section, unused.
21. **NPS/CSAT — always include in Key Results by default when the evidence exists.** Product metrics are asked for in most JDs (explicitly or implicitly) — default to keeping NPS/CSAT alongside other Key Results; removing later is easy if a specific vacancy truly has no use for them.
22. **Every sentence must earn its place.** After drafting each role paragraph, check every sentence against the Signal Coverage Table. Ask: does this deliver value in the context of this JD's requirements, or lead the recruiter in the wrong direction? If a sentence maps to no JD signal (high/medium/low) — cut it. Factual ≠ relevant. (Phase 3.6 will audit the saved CV — but the draft should already pass this check.) NPS/CSAT are valid product-metrics evidence regardless of role type (per rule 21, default = keep) — combine with error reduction %, automation %, delivery velocity rather than replacing them, especially when the JD explicitly asks for "experience with product metrics and analytics."
23. **CV describes practice, NOT cases.** Role descriptions state what the candidate did as a pattern (approach, method, ongoing responsibility). Specific examples, named projects, and case-study evidence belong in the interview, not the CV. Wrong: "identified an off-hours revenue gap and built an automated flow". Right: "applied gap analysis to identify process discrepancies and defined requirements to close them." The CV proves breadth of practice; the interview proves depth with specifics.
24. **Years of experience — count ONLY "Product Manager"/"Product Owner"-titled roles (both count equally, per 2026-08-13 decision — see profile note below rule 24b).** Default summary = "Product Manager with 6+ years…" (or "Product Owner", matched to whichever title this specific CV uses — see rule 24b). PM/PO-titled roles as of 2026-08: Independent/Project-based (Aug 2025–Present, ~11m) + InsulaLabs (5m) + Marketplace (14m) + HostiServer (46m) = ~76m ≈ 6+ years. "Project Manager" title (HostiServer 2015–2017) ≠ product years — never fold it in. Recompute only if a new PM/PO-titled role is added.

24b. **Title choice (Product Manager vs Product Owner) is JD-driven, not fixed.** As of 2026-08-13, all profile role titles use "Product Manager" except InsulaLabs (stays "Product Owner" — literal title held there). Treat the two terms as interchangeable in principle: some companies/recruiters/ATS filters screen strictly on one term over the other. Default to whichever term the target JD's own role title uses (JD says "Product Manager" → CV role titles say "Product Manager"; JD says "Product Owner" → CV role titles say "Product Owner"), keeping InsulaLabs as "Product Owner" regardless (that one is fixed, not JD-driven). If the JD uses a different or ambiguous term, default to "Product Manager" (the current profile default). This does not change what work was actually done — only the title label applied to it.
25. **NEVER use em-dashes (—).** Use a period, comma, colon, or parentheses instead. A chained em-dash pair inside one sentence (a mid-sentence parenthetical insert) is a strong, well-known AI-writing tell — rewrite as two sentences or a parenthetical instead of reaching for a dash.
26. **Write at B2 English level — plain, direct vocabulary and sentence structure, no idiom.** Candidate's actual English level is B2 (per PROFILE.md → Settings). Avoid idiomatic/literary phrasing that signals native-level fluency — "safety net", "closing the loop", "ends up owning", "no stone unturned", chained metaphors, or any turn of phrase a B2 speaker wouldn't naturally produce or confidently defend if asked about it in an interview. Prefer short, direct sentences over subordinate-clause-heavy constructions. This is a per-sentence check, not a pass over only the "fancy-sounding" lines — the flagged phrasing is often introduced unconsciously mid-sentence (found recurring across multiple CVs/covers, e.g. vacancy #1169).

---

## Language Precision

| Verb | When to use |
|------|------------|
| Owned | Responsible for product/outcome as PM |
| Led design and delivery | Drove product decisions, team executed |
| Coordinated | PM/coordinator role without full ownership |
| Built | Only if actually wrote code |
| Participated in | Contributed but didn't lead |

---

## Golden Rule — North Star Mirroring (SUMMARY, primary rule)

Before writing SUMMARY, re-read the Phase 1 North Star sentence (§1.0.5 in JD_analysis.md). The SUMMARY must read as a direct, paraphrased answer to it, not a generic positioning statement and never JD-verbatim (see rule 25 / Phase 3.7 JD-Echo Risk) — the same image the employer has in mind, reflected back in the candidate's own words. This always wins over every other emphasis mechanism below — see Emphasis Precedence.

## CV Structure

Output valid markdown exactly as shown below. Do NOT substitute `•` for `-`. Do NOT omit `#`/`##`/`###` prefixes. Do NOT skip blank lines before lists.

```markdown
# [Selected Name]
[Headline]  
[contacts line — copy verbatim from PROFILE.md → ## Contacts]

---

## SUMMARY

[2 paragraphs max. Full-arc positioning tailored to this vacancy.]
[AI tooling paragraph — include when vacancy has AI/product/digital signal; omit if vacancy is for AI product owner]

---

## EXPERIENCE

### [Role Title — exact as in employment records]
[Company | Dates]

[1–2 paragraphs: what was done, key decisions, context — tailored to this vacancy's pain]

Key results:

- [Metric/outcome]
- [Metric/outcome]

**Multi-role at same company (e.g. HostiServer PO + PM):** each role gets its own `### Role Title` + `Company | Dates` line independently. NEVER create a parent company block (e.g. `### HostiServer · 6 years`) above two roles — it breaks PDF layout. Both roles follow the same flat pattern.

---

[...repeat for all roles, reverse chronological, default cutoff 2017...]

---

## CERTIFICATIONS

Certified AI-Empowered SAFe® Product Owner/Product Manager
[Add AI certs only if vacancy explicitly focuses on AI product ownership]
```

**Formatting rules (mandatory):**
- `# Name` — H1 for candidate name (one per CV)
- `[Headline]  ` — **two trailing spaces** after headline → line break before contacts. Example: `Product Owner / Product Manager  ` (note the two spaces at end)
- `## SECTION` — H2 for SUMMARY / EXPERIENCE / CERTIFICATIONS
- `### Role Title` — H3 for each job role title
- `Key results:` followed by **blank line**, then `- item` list (NOT `•`)
- `---` between each job entry (rule 17)
- Contacts: **copy verbatim** from PROFILE.md → `## Contacts` — markdown links, exact separators, all four items including portfolio. **NEVER use plain-text URLs. NEVER omit portfolio link.** Never add GitHub (rule 14).

**Headline options:**
- **Never append a narrow specialization qualifier like "(UX)" to the headline or Summary opening, even when the JD's own title uses it (confirmed 2026-08-30, vacancy #1333).** Candidate is explicit: he is not a UX specialist — UX is one part of Product work, not a separate title/discipline he claims. Headline stays plain "Product Manager" / "Product Owner"; UX signal goes into Summary/EXPERIENCE content, never into the title.
- **Headline always tracks the JD's own term.** JD says "Product Manager" → headline is `Product Manager`. JD says "Product Owner" → headline is `Product Owner`. This applies regardless of what any individual role's title in EXPERIENCE says (e.g. InsulaLabs is contractually fixed as "Product Owner" per rule 24b — that does NOT pull the headline toward a combined "Product Manager / Product Owner"). Confirmed 2026-08-25 (vacancy #1235).
- If the JD itself uses both terms interchangeably or is ambiguous → combined `Product Manager / Product Owner` is the fallback default.
- Adjust only if role archetype strongly differs (e.g. `Technical Program Manager`)

**Summary opening term — asymmetric, JD-driven (confirmed 2026-09-07, vacancy #1491) — does NOT apply to the headline above, only to the Summary's opening sentence:**
- JD title = "Product Owner" → Summary opens with the combined `Product Owner / Product Manager` (e.g. "Product Owner / Product Manager with 6+ years..."). Most of the candidate's role titles default to "Product Manager" (rule 24b), so "Product Owner" alone in Summary can read as narrower/inconsistent to a reader cross-referencing LinkedIn or other applications.
- JD title = "Product Manager" → Summary opens with `Product Manager` alone, no combined form — that's already the default term, nothing to hedge.

**AI Tooling Paragraph — mandatory for all roles with any AI/product/digital signal:**

**Before defaulting to the 1-/2-component templates below — check PROFILE.md's `Additional Evidence` sections for a more specific block matching the JD's exact wording (named tool, specific use case).** The templates are a fallback for a generic AI signal, not the first move. Do not pattern-match "AI signal present → use 2-component form" without checking whether PROFILE.md already has a more precise evidence block for that specific signal — using the generic template when a specific one exists produces a claim the JD didn't ask for and skips the evidence the JD actually asked for. Example: a JD naming Claude Code by name is answered by the "Claude Code / AI-agent-tooling practice" evidence block, not by the generic "LLM pipelines" 2-component paragraph (that one answers a different claim — building AI systems, not using one as a daily tool). Found live 2026-09-09, vacancy #1515.

**GOLDEN STANDARD (locked, confirmed 2026-09-07, vacancy #1494) — the "AI tooling across PM workflows" line is fixed text, used verbatim every time, never trimmed or reworded per vacancy:**
> `AI tooling across PM workflows (Claude, ChatGPT, Gemini): research synthesis, user feedback analysis, requirements refinement, technical/API spec review, workflow validation, prototype creation.`

1-component (most roles — daily practice only) — the golden line above, plus the portfolio link appended to it:
> `AI tooling across PM workflows (Claude, ChatGPT, Gemini): research synthesis, user feedback analysis, requirements refinement, technical/API spec review, workflow validation, prototype creation. Personal projects: [ioncat.github.io](https://ioncat.github.io/).`

2-component (AI/technical depth roles — explicit AI product ownership, LLM/technical PM, hands-on AI signal required):
> `Built LLM pipelines hands-on in personal projects: prompt architecture, context window management, response quality assessment. That hands-on depth carries into writing AI-related requirements and specs detailed enough for an engineering team to build from. Personal projects: [ioncat.github.io](https://ioncat.github.io/).`
> `AI tooling across PM workflows (Claude, ChatGPT, Gemini): research synthesis, user feedback analysis, requirements refinement, technical/API spec review, workflow validation, prototype creation.` *(the golden line, standalone — no portfolio link here, it already appeared in the paragraph above)*

**Banned wording — never use, even though it appears in older CVs:**
- "...for engineers to ship from" (or equivalent literal handoff phrasing) about the personal projects — these are solo projects, no engineers were involved; a literal handoff claim is a logical contradiction. Use "that hands-on depth carries into writing AI-related requirements and specs detailed enough for an engineering team to build from" instead.
- "Active daily practice, not a side project" (or equivalent) — implies commercial/professional context that doesn't exist; delete permanently.
- "portfolio" for the GitHub examples — use "personal projects" instead.

**⚠️ Portfolio link is MANDATORY in the AI paragraph — always include `[ioncat.github.io](https://ioncat.github.io/)` at the end, exactly once (1-component: appended to the golden line; 2-component: appended to the LLM-pipelines paragraph, not repeated on the golden line).**

---

## Emphasis Precedence

Three separate mechanisms below all decide "what to lead with." Found live on vacancy #1646 (2026-09-21): with no stated order between them, the draft led with a business-feature list instead of the technical-complexity framing its own `role_balance` numbers implied. Resolve in this order when they'd pull in different directions:

1. **Golden Rule (North Star Mirroring, above)** — always wins.
2. **Archetype mismatch handling** (under Adaptation Plan Implementation, below) — only when Phase 2 explicitly flagged one.
3. **Tailoring Logic (Role Balance Shape, below)** — the default emphasis driver when no mismatch was flagged.
4. **Primary Asset vs. Supporting Roles** — decides which role carries the emphasis chosen above; it does not choose the emphasis itself.

---

## Primary Asset vs. Supporting Roles

Before drafting, identify which 1–2 roles are the **primary asset** for this vacancy — the roles most directly matching the core JD requirement (e.g., for a CRM PM role → HostiServer; for a marketplace discovery role → Marketplace).

For the primary asset role(s): lead with the vocabulary, metrics, and framing that directly match the JD's main requirement.

For all other (supporting) roles: do NOT force the primary keyword where it doesn't belong. Instead, identify what secondary JD requirement each supporting role can address:
- A discovery methodology → maps to "product discovery, user needs" requirement
- A coordination or process rollout → maps to "coordinate changes across teams"
- A delivery execution role → maps to "ensure smooth implementation of new features"

Even a small, honest signal from a supporting role compounds the overall CV effect. Every role has a job.

---

## Tailoring Logic

**Role Balance Shape — compute deterministically from Phase 1 §1.4's percentages (same margin-based logic Flutter uses under the radar chart — this is arithmetic on numbers already in front of you, not a separate judgment call):**
1. Sort the 6 axes by percentage, descending (ties broken by axis order: strategy, discovery, delivery, growth, stakeholder, operational).
2. If (#1 − #2) ≥ 10 points → **Sharp — [axis #1]**.
3. Else if (#2 − #3) ≥ 10 points → **Dual — [axis #1 + axis #2]**.
4. Else → **Diffuse — [axis #1 + axis #2]** (leaning, no clean single lead).

**Lead with, based on the Shape just computed:**
- **Sharp** → lead with the single strongest matching experience for that one axis: Strategy → vision/roadmap ownership; Discovery → research/validation; Delivery → shipped-thing track record; Growth → experiment/data-driven improvement; Stakeholder → cross-functional alignment; Operational → process/automation ownership.
- **Dual** → weave both axes together explicitly in SUMMARY and at least one shared EXPERIENCE paragraph — do not pick one and drop the other.
- **Diffuse** → lean on the top 2 axes without overclaiming a single sharp focus. Broader positioning is honest here, not a weakness to hide.

Emphasis = adjust language and which Key Results to surface first. Not deleting entries.

---

## Adaptation Plan Implementation

`JD_analysis.md` contains `## Adaptation Plan` from Phase 2. Implement ALL listed actions in this draft.

**Elaboration-depth check (added 2026-09-21, vacancy #1577) — "implement the action" means giving it the same level of process detail as comparable signals elsewhere in the same CV, not a passing one-line mention.** If an Adaptation Plan action names a specific piece of evidence (a named system, a named process, a specific case) as the answer to a signal, and a comparable signal elsewhere in the same draft gets a full paragraph (what was owned, how it worked, what the candidate's role in it was) — the flagged evidence needs the same treatment, not a generic single clause tacked onto an unrelated sentence. A one-line mention that doesn't actually explain what the candidate did with that evidence does not satisfy "implement the action," even though it technically name-drops the right words. Found live 2026-09-21 on vacancy #1577: the Adaptation Plan named HostiServer's self-built-CMS/multilingual-content case as real evidence for the JD's localization signal, but the first Phase 3 draft reduced it to one generic clause while a directly comparable signal (Marketplace's own localization ownership) got a full, detailed paragraph in the same draft — the user caught the imbalance immediately ("почему ты отработал его в Marketplace, а самый главный asset... пропускаешь?").

**Archetype mismatch handling** (if flagged in Phase 2 Key Barriers or Adaptation Plan):
- JD wants Founder Proxy → lead with strongest 0→1 ownership evidence from PROFILE.md (co-founder story, product built from scratch); reframe execution roles with "built from scratch" narrative; downplay coordinator/delivery framing
- JD wants Executor → lead with strongest delivery metrics track record from PROFILE.md; keep execution/delivery roles prominent; de-emphasize founding/ownership angle
- If not flagged → use default Tailoring Logic above

**Fit Breakdown ⚠️ items** (from Phase 2): where candidate has partial/pet-project evidence —
address by reframing existing experience. Do NOT fabricate. Do NOT claim ✅ if profile shows ⚠️.

**Fit Breakdown ❌ items**: do not mention, do not fabricate, do not imply.

---

## Signal Coverage Mandate

`JD_analysis.md` contains `## Signal Coverage Table` from Phase 2.

**Before writing any EXPERIENCE content:**
1. Read the Signal Coverage Table.
2. Identify all rows where `importance = high|medium` AND `in_profile = ✅ or ⚠️`.
3. For each such signal — verify it is explicitly reflected in at least one role entry in the EXPERIENCE section.
4. If a signal is missing from EXPERIENCE: add it to the appropriate role using honest framing from PROFILE.md.
5. Signals where `in_profile = ❌`: do not mention, do not fabricate.

**This check is mandatory. Skipping it means the CV is incomplete.**
