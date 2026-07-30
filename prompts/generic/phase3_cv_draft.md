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
4. **NEVER remove a work experience entry** — every job in PROFILE.md stays in CV. This includes the current/most recent role — never drop it even if it looks less relevant to the JD than an older role.
4b. **EXPERIENCE order is ALWAYS strict reverse-chronological — most recent role first.** Never reorder by relevance or "lead with the strongest match." If the Adaptation Plan says "lead with X," that means strengthen X's framing/word choice within its own chronological slot, not move it to the top of the list.
5. **CV language = input language** — English JD → English CV; Ukrainian JD → Ukrainian CV
6. **Avoid AI clichés** — "AI-Native", "AI-Driven mindset" etc.
7. **Avoid first-person pronouns** — standard CV convention
8. **Metrics belong in Key Results only** — do not duplicate in prose
9. **NO Location**
10. **Certifications** — include only if directly relevant to this vacancy; omit otherwise
11. **NEVER use plural forms for things built or owned: no "systems", "portals", "platforms".** Name individual items specifically (singular each), or use "product" / "product suite" as a collective. Exception: "products" is allowed only when referring to multiple distinct products in context.
12. **NEVER use third-person verbs anywhere in the CV** — no "Understands", "Knows", "Applies", "Works", "Brings", "Has". CV language = headline-style (no subject) or past-tense action verbs. Applies to Summary, bullets, and all prose.
13. **GitHub link — include only if vacancy has explicit engineering/code signal.** If candidate has a portfolio site, it covers GitHub; GitHub URL in header is redundant.
14. **NEVER use em-dashes (—).** Use a period, comma, colon, or parentheses instead. A chained em-dash pair inside one sentence (a mid-sentence parenthetical insert) is a strong, well-known AI-writing tell — rewrite as two sentences or a parenthetical instead of reaching for a dash.

---

## CV Structure

Output valid markdown exactly as shown below. Do NOT substitute `•` for `-`. Do NOT omit `#`/`##`/`###` prefixes. Do NOT skip blank lines before lists.

```markdown
# [Selected Name]
[Professional headline — candidate's actual role, from PROFILE.md]  
[contacts — read from PROFILE.md → contact section]

---

## SUMMARY

[2 paragraphs max. Tailored to this vacancy's pain and requirements.]

---

## EXPERIENCE

### [Role Title — exact as in employment records]
[Company | Dates]

[1–2 paragraphs: what was done, key context — tailored to this vacancy]

Key results:

- [Concrete outcome or metric]
- [Concrete outcome or metric]

---

[...repeat for all roles, reverse chronological...]

## SKILLS

[Grouped list of relevant hard and soft skills from PROFILE.md — include if relevant to this role type]

## CERTIFICATIONS

[Only real, verifiable — read from PROFILE.md. Include only if directly relevant; omit otherwise]
```

**Formatting rules (mandatory):**
- `# Name` — H1 for candidate name (one per CV)
- `[Headline]  ` — **two trailing spaces** after headline → line break before contacts
- `## SECTION` — H2 for SUMMARY / EXPERIENCE / SKILLS / CERTIFICATIONS
- `### Role Title` — H3 for each job role title
- `Key results:` followed by **blank line**, then `- item` list (NOT `•`)
- `---` between each job entry

**Headline:** use candidate's professional title as stated in PROFILE.md. Adjust only if role clearly targets a different function (e.g. candidate is EA/PA applying to Operations role → "Operations & Administrative Professional").

**Contact:** read from PROFILE.md → contact section. Include email. Include LinkedIn if present. No phone. No location.

---

## Skills Section Rules

- Include if vacancy requires specific tools, systems, or competencies worth listing
- Group by category (e.g. Tools / Languages / Competencies)
- Only include skills with evidence in PROFILE.md — no invented skills
- Keep concise — max 4–6 lines

---

## Primary Asset vs. Supporting Roles

Before drafting, identify which 1–2 roles are the **primary asset** for this vacancy — the roles most directly matching the core JD requirement.

For the primary asset role(s): lead with vocabulary, metrics, and framing that directly match the JD's main requirement.

For all other (supporting) roles: do NOT force the primary keyword where it doesn't belong. Instead, find what secondary JD requirement each supporting role can address — even a small, honest signal compounds the overall CV effect. Every role has a job.

---

## Tailoring Logic

Based on role type from Phase 1 (section 1.3–1.4):
- Execution-heavy → lead with delivery track record, operational discipline, concrete results
- Coordination-heavy → lead with stakeholder management, cross-functional communication
- Specialist → lead with domain expertise depth
- Generalist → lead with breadth + adaptability + multi-priority management

Emphasis = adjust language and which Key Results to surface first. Never delete entries.

---

## Adaptation Plan Implementation

`JD_analysis.md` contains `## Adaptation Plan` from Phase 2. Implement ALL listed actions in this draft.

**Fit Breakdown ⚠️ items** (from Phase 2): where candidate has partial/indirect evidence —
address by reframing existing experience. Do NOT fabricate. Do NOT claim ✅ if profile shows ⚠️.

**Fit Breakdown ❌ items**: do not mention, do not fabricate, do not imply.
