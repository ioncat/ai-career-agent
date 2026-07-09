# Phase 3.5: CV Self-Review

Review the generated CV draft against the specific vacancy. Identify what doesn't fit, what's weak, and what's missing.
The candidate's full profile is in your system context (PROFILE.md).

**Output language: use the language specified in the active user's PROFILE.md → `## Settings` → `language` field. Default: Russian.**

This review is shown to the user BEFORE saving the CV. It is the first time the user sees the CV output.

---

## Input

User will provide:
1. JD text
2. JD_analysis.md content (Phase 1 + Phase 2)
3. The CV draft generated in Phase 3

---

## Questions to Answer for THIS Specific Vacancy

**What doesn't belong:**
- Which sections/paragraphs are NOT relevant to this role's actual requirements?
- What experience is included out of habit but adds no signal here?
- What might mislead the reader — implying skills or experience that don't match the role?

**What's weak:**
- Which JD requirements are addressed too vaguely in the CV?
- Where is the language too generic when the JD uses specific terminology?
- What key pain point from Phase 1 analysis is NOT reflected in the CV?

**What's missing:**
- What relevant experience exists in the profile but wasn't highlighted?
- What framing would make existing experience map more clearly to this role?

---

## Output Format

```
CV SELF-REVIEW
—————————————
❌ Remove / doesn't fit:
• [item] — reason

⚠️ Weaken / compress:
• [item] — reason

🔧 Strengthen / reframe:
• [item] — what to change

✅ Strong — keep as is:
• [item]
```

Then output the updated CV draft with all identified changes already applied.

**FULL OUTPUT ORDER — follow exactly, no deviations:**

1. Top-15 Word Frequency table (from § Top-15 Frequency Check below)
2. Tools & Technologies table (from § Tools & Technologies Check below)
3. CV SELF-REVIEW block (❌ / ⚠️ / 🔧 / ✅)
4. This exact line — as plain text, NOT inside a code block:

---CV---

5. Final updated CV (markdown, starting with `# [Candidate Name]`)

**The `---CV---` separator is MANDATORY. Rules:**
- Output it as a **plain text line** — NOT inside backticks or a code block
- Close all open code blocks before outputting `---CV---`
- If it is missing or wrapped in backticks, the entire output including the review tables will be saved as the CV — which is wrong

---

## Top-15 Frequency Check (internal only — output as table in review)

Compare word frequency between JD and CV draft. Identify signal mismatches.

**Output order (standard):**
1. Top-15 table — shown first, as a standalone visible block (pure data, no interpretation)
2. CV Self-Review sections (❌/⚠️/🔧/✅) — follow immediately after, incorporating Top-15 findings into the relevant flags

**Steps:**
1. Extract top-15 content words from JD (exclude stopwords: articles, prepositions, conjunctions, pronouns, auxiliary verbs, company name)
2. Extract top-15 content words from CV draft (same stoplist)
3. Output side-by-side table:

```
JD top-15                     CV top-15
──────────────────────────────────────────────────
N  word                   N   word     [flag]
...
```

Flag column:
- 👻 `missing` — word is top-5 in JD but rank >15 or absent in CV (signal ghosted)
- 📉 `weak` — word is top-10 in JD but rank >10 in CV (signal fading)
- 📣 `overloaded` — word is top-3 in CV but not in JD top-10 (shouting at nobody)

**Then — in the CV Self-Review sections below:**
- Words `← missing` from JD top-5 → add to 🔧 with specific placement suggestion
- Words `← overloaded` in CV → add to ⚠️ with suggestion to vary

**Default N = 15.** Can be adjusted to 20 for longer JDs (2000+ words).

---

## 🛠️ Tools & Technologies Check (output as table in review, after Top-15 table)

Scan JD and CV for named tools and technologies. Compare presence.

**Tool registry by category (expandable — add tools from new vacancies):**

| Category | Tools |
|---|---|
| Analytics / tracking | Mixpanel, Amplitude, PostHog, Google Analytics, GA4, Hotjar, Heap, FullStory, Pendo |
| Project / backlog | Jira, Linear, Asana, Confluence, Notion, Trello |
| Design / prototyping | Figma, Sketch, Miro, Whimsical, Marvel, InVision |
| CRM platforms | Salesforce, HubSpot, Pipedrive, Zoho CRM, Intercom, Freshdesk, Zendesk |
| A/B testing | Optimizely, VWO, LaunchDarkly, GrowthBook, Firebase A/B |
| Data / BI | SQL, Tableau, Looker, Metabase, Redash, PowerBI |
| AI / LLM | Claude, ChatGPT, OpenAI API, Anthropic API, Vertex AI, LangChain, n8n |
| Automation | Zapier, Make (Integromat), n8n, Workato |

**Steps:**
1. Scan JD for named tools from registry above (also catch unlisted tools)
2. Scan CV draft for named tools
3. Output 🛠️ table in review:

```
🛠️ Tools & Technologies
──────────────────────────────────────────────────
JD requires / mentions    CV has           Signal
[tool or category]        [tool or —]      [flag]
```

**Flags:**
- 👻 `missing` — tool named in JD, candidate has experience, absent from CV → add to 🔧
- ✅ `aligned` — tool in JD, present in CV
- 📣 `extra` — tool in CV, not in JD (neutral — shows working method, do not remove)
- ⚠️ `implied` — JD says "analytics" / "data-driven" / "A/B testing" generically — note category; if CV has a tool in that category → show it; if absent → add to 🔧

**If JD names zero tools:** output one line — `JD names no specific tools — generic categories only` — then list CV tools as `📣 extra (neutral)`.

---

## Primary Asset vs. Supporting Roles Check (internal only — do NOT output label)

Every tailored CV has 1–2 roles that carry the primary fit signal for this vacancy's main requirement. All other roles are structurally weaker in direct relevance — but must not be left generic or neutral.

**Steps (internal):**

1. Identify primary asset roles: which 1–2 roles most directly address the vacancy's core requirement?
2. For each remaining (supporting) role: scan for an underutilized signal that maps to a secondary JD requirement — even a small, honest strengthening compounds the overall CV effect.
3. Do NOT force the primary keyword into supporting roles where it doesn't belong.
4. If a supporting role has an unused signal → add to 🔧 with a specific suggestion.
5. If a supporting role is already contributing a distinct secondary signal → add to ✅.

The goal: each role has a job. Primary asset carries the main requirement. Supporting roles cover secondary requirements — coordination, discovery, process, stakeholder management, etc.

---

## Phase 2 Implementation Check (internal only — do NOT output)

Before generating the review, verify three things from `JD_analysis.md`. Use findings to populate ❌/⚠️/🔧/✅ sections. Do NOT output this check or its labels in the review.

1. **Adaptation Plan** — each action applied? If not → add to 🔧
2. **Fit Breakdown ⚠️ items** — addressed or reframed in CV? If not → add to 🔧
3. **Fit Breakdown ❌ items** — absent and not implied? If one appears → add to ❌

---

## Rules

- If no issues in a category, write `• нет замечаний` — do not skip the category header
- Apply changes to the CV draft directly — do not output a separate diff
- The self-review block will be appended to JD_analysis.md after user approval
