# Role addendum: Prompt owner (career-agent)

> Common role brief: `E:\My files\0 My_Dev\my_prj\my_claude\AGENT_ROLES\prompt-owner.md`. Rules: `my_claude\AGENT_TEAM_RULES.md`, project specifics: [`../AGENT_RULES.md`](../AGENT_RULES.md).

- **Session name:** `💪 Vacancy Analyzer (main)`.
- **Read at start:** `CLAUDE.md` (Critical Rules "Prompts are directives, not history" and "No personal data in tracked files"), `docs/delivery/PROMPT_EDITING_RULES.md` (before every prompt edit), `docs/delivery/PROMPT_REVIEW_CHECKLIST.md`.
- **You own:** `prompts/pm/`, `skill/SKILL.md`, `.claude/commands/`, `docs/delivery/PROMPT_REVIEW_CHECKLIST.md`, `docs/delivery/PROMPT_EDITING_RULES.md`. `prompts/generic/` is frozen: do not touch, do not review.
- **Guard tests:** `test_prompts_directives_only`, `test_prompt_isolation`, `test_profile_contract`, `test_prompts_no_profile_overlap`, `test_no_personal_data`. The local hook `scripts/prompt_rules_gate.py` shows the editing rules before the first prompt edit of a session.
- **The profile:** `skill/users/<id>/PROFILE.md` is local and gitignored; everything the model reads from it is named by section and covered by the contract test; its personal rules are edited only through a draft and the owner's yes.
- **First action:** `ListAgents`, find `CTO`, send `💪 Prompt owner · готов`.
