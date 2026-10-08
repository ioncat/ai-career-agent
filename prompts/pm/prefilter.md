# Pre-filter: Critical Blocker Check

Compare the JD below against `## Critical Blockers` above. Flag only explicit
conflicts — not a fit assessment.

Rules:
- If a `## Vacancy Requirements` section is present, it's Djinni's own
  structured requirements sidebar (poster-set, not JD-body prose) — treat
  every line there as an authoritative hard requirement, not a casual
  mention. English level, country/remote-format, and years-of-experience
  are already checked deterministically before this prompt ever runs (see
  `tools/cv_prefilter.py`'s `_check_english_level`/`_check_country`/
  `_check_remote_format`) — you won't be asked to re-derive those. This
  covers the sidebar lines; a language level written in the JD text itself
  is judged by the language-level rule below. Still
  read the section carefully for anything the deterministic checks don't
  cover (e.g. domain, seniority) rather than skimming past it as a benefits
  list. A benefits-style section can carry a hard restriction: "Remote, but only from within one named region" is a geographic restriction, not a perk, and this section is where it is authoritative.
- Only bullets under a REQUIREMENTS-type heading ("Requirements", "What
  we're looking for", "Must have", "Qualifications", "Що важливо") count as
  something the candidate must already possess. A plain bullet there is a
  hard requirement by default — no need for the word "required".
- Bullets under a RESPONSIBILITIES-type heading ("Responsibilities", "What
  you'll do", "You will", "Обов'язки") describe day-to-day duties, NOT prior
  experience — do NOT flag based on these alone, even if they mention a
  blocked skill. "Design and run experiments" as a listed duty is not the same
  as "hands-on experimentation experience required" — only flag if the
  Requirements section itself demands that experience.
- Skip a bullet only if the JD marks it optional ("nice to have", "a plus",
  "bonus", "preferred").
- Language level: compare levels, do not react to a mention of a language.
  CEFR order, low to high: A1, A2, B1, B2, C1, C2. Descriptive labels map to
  it: Intermediate = B1, Upper-Intermediate = B2, Advanced = C1,
  Fluent = C1 to C2, Native = C2. The bare word "proficiency" is not a level
  label ("working proficiency", "proficiency at Intermediate" describe lower
  levels). Take the candidate's level from the language line in the profile's
  Critical Blockers. Flag a language requirement only when the level the JD
  requires is strictly higher than the candidate's and the blocker rule asks for a block at that level.
  A required level equal to or below the candidate's is never a blocker, and
  neither is "X or higher" when X is at or below the candidate's level. If
  the JD gives no level, or you cannot map it to CEFR, don't flag.
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
commentary after the quote. Wrong: `domain: "requires logistics experience as
specified in the blocker criteria"` (that's an explanation, not a quote).
Right: `domain: "3+ years hands-on warehouse logistics experience"`.

Note: the vacancy title itself is checked separately, before you ever see
this JD — you will never be asked to judge it. `## Critical Blockers` above
never contains a `title:` line.

or:

```
BLOCKED: no
```

Never output `REASONS:` when `BLOCKED: no`.
