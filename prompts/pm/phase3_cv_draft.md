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
21. **NPS/CSAT — context-dependent.**
22. **Every sentence must earn its place.** After drafting each role paragraph, check every sentence against the Signal Coverage Table. Ask: does this deliver value in the context of this JD's requirements, or lead the recruiter in the wrong direction? If a sentence maps to no JD signal (high/medium/low) — cut it. Factual ≠ relevant. (Phase 3.6 will audit the saved CV — but the draft should already pass this check.) For technical/platform/AI roles: NPS and CSAT are CX/support metrics — deprioritize or remove; use error reduction %, automation %, delivery velocity instead. Keep for: CX-focused PM, growth PM, customer-success-adjacent roles.
23. **CV describes practice, NOT cases.** Role descriptions state what the candidate did as a pattern (approach, method, ongoing responsibility). Specific examples, named projects, and case-study evidence belong in the interview, not the CV. Wrong: "identified an off-hours revenue gap and built an automated flow". Right: "applied gap analysis to identify process discrepancies and defined requirements to close them." The CV proves breadth of practice; the interview proves depth with specifics.
24. **Years of experience — count ONLY "Product Owner"-titled roles.** Default summary = "Product Owner with 6+ years…". PO-titled roles as of 2026-07: Independent/Project-based PO (Aug 2025–Present, ~11m) + InsulaLabs (5m) + Marketplace PO (14m) + HostiServer PO (46m) = ~76m ≈ 6+ years. Project Manager title ≠ product years — never fold it in. Recompute only if a new PO-titled role is added.
25. **NEVER use em-dashes (—).** Use a period, comma, colon, or parentheses instead. A chained em-dash pair inside one sentence (a mid-sentence parenthetical insert) is a strong, well-known AI-writing tell — rewrite as two sentences or a parenthetical instead of reaching for a dash.

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
- Default: `Product Owner / Product Manager`
- Adjust only if role archetype strongly differs (e.g. `Technical Program Manager`)

**AI Tooling Paragraph — mandatory for all roles with any AI/product/digital signal:**

1-component (most roles — daily practice only):
> `AI tooling in daily practice (Claude, ChatGPT, Gemini) — requirements refinement, research synthesis, workflow validation. Personal portfolio at [ioncat.github.io](https://ioncat.github.io/).`

2-component (AI/technical depth roles — explicit AI product ownership, LLM/technical PM, hands-on AI signal required):
> `Built LLM pipelines hands-on — prompt architecture, context window management, response quality assessment — and applied that implementation depth to writing AI requirement specs complete enough for engineers to ship from. Active daily practice, not a side project. Personal portfolio at [ioncat.github.io](https://ioncat.github.io/).`
> `AI tooling across PM workflows (Claude, ChatGPT, Gemini) — requirements refinement, research synthesis, workflow validation.`

**⚠️ Portfolio link is MANDATORY in the AI paragraph — always include `[ioncat.github.io](https://ioncat.github.io/)` at end of last AI sentence.**

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

Based on role archetype from Phase 1:
- Full PM (discovery + strategy + delivery) → lead with discovery + platform ownership
- Pure execution/delivery coordinator → lead with delivery track record
- Technical program management → lead with system complexity + cross-team coordination
- Operations/BizOps → lead with automation, process ownership, operational metrics

Emphasis = adjust language and which Key Results to surface first. Not deleting entries.

---

## Adaptation Plan Implementation

`JD_analysis.md` contains `## Adaptation Plan` from Phase 2. Implement ALL listed actions in this draft.

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
