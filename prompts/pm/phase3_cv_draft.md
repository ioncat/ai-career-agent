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
4. **NEVER remove a work experience entry** — every job in PROFILE.md stays in CV. Early career entries (before the cutoff year in PROFILE.md) omitted by default unless directly relevant.
5. **CV language = input language** — English input → English CV; Ukrainian input → Ukrainian CV
6. **Do not self-apply "Senior"** unless officially held
7. **Avoid AI clichés** — "AI-Native", "AI-Driven mindset" etc.
8. **Avoid first-person pronouns** — standard CV convention
9. **"Built" implies coding** — use "Led design and delivery", "Owned", "Coordinated" for PM work
10. **Metrics belong in Key Results only** — do not duplicate in prose
11. **NO Skills section**
12. **NO Education section**
13. **NO Location**
14. **GitHub link — never include in contacts.** Portfolio site (from PROFILE.md contacts) already covers it. GitHub URL is redundant and creates noise.
15. **Summary section header — language rule:** English CV → use `SUMMARY` header. Ukrainian CV → NO header, summary text flows directly after headline/contacts. "РЕЗЮМЕ" as a section label is redundant inside a CV.
16. **Domain context (e.g. iGaming, fintech, e-commerce) — include only if JD is from that domain.** Never volunteer domain in a generic or unrelated vacancy.
17. **Add `---` separator between each job entry** for visual spacing in PDF output.
18. **NEVER use plural forms for things built or owned: no "systems", "portals", "platforms".** Name individual items specifically (singular each), or use "product" / "product suite" as a collective. Exception: "products" is allowed only when referring to multiple distinct products in context.
19. **NEVER use third-person verbs anywhere in the CV** — no "Understands", "Knows", "Applies", "Works", "Brings", "Has". CV language = headline-style (no subject) or past-tense action verbs. Applies to Summary, bullets, and all prose.
20. **CERTIFICATIONS: include only "Certified AI-Empowered SAFe® Product Owner/Product Manager" by default.** Add others only when directly relevant to the specific vacancy.

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

```
[Selected Name]
[Headline]
[contacts line from PROFILE.md → ## Contacts — copy verbatim]

> **Contacts line: copy verbatim from PROFILE.md → ## Contacts.** Never add GitHub here (see rule 14). Same line for English and Ukrainian CVs.

SUMMARY
[2 paragraphs max. Full-arc positioning tailored to this vacancy.]
[AI tooling paragraph — include when vacancy has AI/product/digital signal; omit if vacancy is for AI product owner]

EXPERIENCE

[Role Title — exact as in employment records]
[Company | Dates]
[1–2 paragraphs: what was done, key decisions, context — tailored to this vacancy's pain]
Key results:
• [Metric/outcome]
• [Metric/outcome]

[...repeat for all roles, reverse chronological, default cutoff 2017...]

CERTIFICATIONS
Certified AI-Empowered SAFe® Product Owner/Product Manager
[Add AI certs only if vacancy explicitly focuses on AI product ownership]
```

**Headline options:**
- Default: `Product Owner / Product Manager`
- Adjust only if role archetype strongly differs (e.g. `Technical Program Manager`)

**AI Tooling Paragraph (standard text when applicable):**
> Applies AI tooling in practice (Claude, ChatGPT) — requirements refinement, research synthesis, and workflow validation.

> **AI-focused vacancy only** (JD has strong AI signal — e.g. AI PM, LLM product, AI platform): add portfolio link after the sentence:
> `...workflow validation. Hands-on prototyping examples at [portfolio link from PROFILE.md contacts].`

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
