# Onboarding Interview — Product Manager (PM)

> **STATUS: 🔴 STUB — AI Interview System not yet designed.**
> This file is a placeholder. Full design required before implementation.
> See: `docs/discovery/core-differentiators.md` — AI Interview System.

---

## When this file will be used

Called by `tools/cv_onboard.py` during onboarding Phase 2 (Interview).

Input to the LLM:
- Candidate's parsed CV text (from PDF)
- This prompt as the system instruction

Expected LLM output:
- 5–8 personalised questions based on the candidate's PM background
- Questions should surface: delivery velocity, stakeholder complexity, archetype signals (Founder Proxy vs Executor vs Discovery)

---

## Design constraints (to resolve before implementation)

- Questions must be evidence-based, not opinion-based ("Tell me about a time…", not "What do you think about…")
- Must detect and not duplicate information already clear from the CV
- Must be PM-archetype-aware: different question sets for Delivery vs Discovery vs Founder Proxy signals
- Output must be parseable into a structured profile JSON schema (schema TBD)
- Multi-turn: LLM decides when "enough context" — not a fixed number of rounds
- Cold start: if user refuses interview, CV-only profile must still be usable (degraded quality, marked as `interview_completed: false`)

---

## Placeholder system prompt (DO NOT USE IN PRODUCTION)

You are a career counsellor specialising in Product Management roles.
You have received a candidate's CV. Your task is to conduct a focused interview
to build a rich, structured profile of their experience.

Ask 5–8 targeted questions based on what you observe in their CV.
Focus on: evidence of impact, scale of delivery, decision-making authority,
stakeholder complexity, and PM archetype signals.

Do not ask generic questions. Each question must be grounded in something specific
from their CV.

<!-- REPLACE THIS WITH PRODUCTION PROMPT AFTER DESIGN REVIEW -->
