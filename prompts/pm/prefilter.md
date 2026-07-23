# Pre-filter: Critical Blocker Check

Compare the JD below against `## Critical Blockers` above. Flag only explicit
conflicts — not a fit assessment.

Rules:
- Only bullets under a REQUIREMENTS-type heading ("Requirements", "What
  we're looking for", "Must have", "Qualifications", "Що важливо") count as
  something the candidate must already possess. A plain bullet there is a
  hard requirement by default — no need for the word "required".
- Bullets under a RESPONSIBILITIES-type heading ("Responsibilities", "What
  you'll do", "You will", "Обов'язки") describe day-to-day duties, NOT prior
  experience — do NOT flag based on these alone, even if they mention a
  blocked skill. "Design and run A/B tests" as a listed duty is not the same
  as "hands-on A/B testing experience required" — only flag if the
  Requirements section itself demands that experience.
- Skip a bullet only if the JD marks it optional ("nice to have", "a plus",
  "bonus", "preferred").
- Never invent a requirement the JD doesn't state.
- Unsure → don't flag.
- Max 5 reasons.
- If `## Critical Blockers` says "(none)": output `BLOCKED: no`.

Output — EXACTLY this, nothing else:

```
BLOCKED: yes
REASONS:
- [blocker category]: "[direct quote from the JD — nothing else]"
```

The quote must come from the JD itself, verbatim (the specific line) — never
the blocker rule text, never an explanation of why it conflicts. No trailing
commentary after the quote. Wrong: `domain: "requires B2C SaaS experience as
specified in the blocker criteria"` (that's an explanation, not a quote).
Right: `domain: "5+ years hands-on B2C subscription product experience"`.

Note: the vacancy title itself is checked separately, before you ever see
this JD — you will never be asked to judge it. `## Critical Blockers` above
never contains a `title:` line.

or:

```
BLOCKED: no
```

Never output `REASONS:` when `BLOCKED: no`.
