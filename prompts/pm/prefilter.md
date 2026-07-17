# Pre-filter: Critical Blocker Check

Compare the JD below against `## Critical Blockers` above. Flag only explicit
conflicts — not a fit assessment.

Rules:
- A plain JD bullet is a hard requirement by default — no need for the word
  "required".
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
- [blocker category]: [short quote or paraphrase of the conflicting JD line]
```

or:

```
BLOCKED: no
```

Never output `REASONS:` when `BLOCKED: no`.
