# Prompt editing rules

> Read this before touching anything in `prompts/`, `skill/SKILL.md` or `.claude/commands/`.
> A hook (`scripts/prompt_rules_gate.py`) shows these rules before the first such edit of a session; tests enforce them after.

## The rule

A prompt is an instruction to the model. Nothing else.

1. **No candidate content, ever.** A prompt never holds any user's experience, facts, numbers, employers, stories, wording or style taken from a profile. Not copied, not paraphrased, not "with the words swapped". The profile supplies the content; the prompt says what to do with it.
2. **Examples are neutral or absent.** If an example is needed, invent it in a domain that belongs to nobody (delivery routes, a library, a bakery). Never write an example by looking at a profile. Prefer a test or a criterion to an example: models repeat examples literally.
3. **No history.** No vacancy ids, dates, "found live", conversation quotes, discovery-doc pointers. That goes to `docs/delivery/CHANGELOG.md`. A short reason that helps an edge case is fine.
4. **Personal preferences are not engine rules.** A rule that holds for one candidate only (a title policy, a paragraph form, a banned phrase of one person) belongs in that user's profile or personal rules file, not in the prompt.
5. **Say it once.** Before adding a rule, search the prompt for an existing one on the same topic and extend it. A near-duplicate rule is how two rules end up disagreeing.

## Before and after the edit

- Before: read this file. Check the planned wording against rules 1, 2 and 4 (would a second user get the first user's life?).
- After: run `python -m pytest tests/test_prompts_directives_only.py tests/test_prompt_isolation.py tests/test_prompts_no_profile_overlap.py tests/test_no_personal_data.py`.
- Before merging a prompt change: the review in [`PROMPT_REVIEW_CHECKLIST.md`](PROMPT_REVIEW_CHECKLIST.md).
- `prompts/generic/` is frozen; do not edit it.

## What enforces this

| Layer | What it does | What it cannot do |
|---|---|---|
| `scripts/prompt_rules_gate.py` (Claude Code hook, local) | Blocks the first edit of a prompt file in each session and prints these rules; the retry passes. Also fires for shell and Python commands that write to those paths. | Works only where the hook is enabled (it lives in the local settings file). |
| `tests/test_prompts_directives_only.py` | Fails on history markers (ids, dates, "found live"). | Does not see paraphrased profile content. |
| `tests/test_prompt_isolation.py` | Fails on a candidate's name, employers, personal URLs. | Same. |
| `tests/test_prompts_no_profile_overlap.py` | Fails when a run of words in a prompt also appears in a local user file (profile content sections, interview prep). | Skipped on a clean clone, where user files do not exist. |
