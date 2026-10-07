# Prompt review checklist

> A repeatable, read-only review of prompt changes. Run it before merging any branch that changes `prompts/`, `skill/SKILL.md` or `.claude/commands/`. Give this file to a review agent (or follow it yourself). First use: branch `refactor/prompts-directives-only-2026-10-04` against `master`.

**Mode:** read-only. Do not edit, commit or push.

## Goal

Confirm that the prompt changes broke nothing and the branch can be merged: the rules are intact, the prompts fit **any** candidate profile (not one person), and the pipeline's prompt chain is consistent.

## Scope

`prompts/generic/` is frozen and **out of scope**: it is a placeholder for future roles, not maintained and not reviewed. Ignore it wherever an item below mentions `generic` or a `pm` and `generic` comparison; report a finding only if a change would break the code that routes to it.

## Definitions

- **blocker:** a rule lost, personal data in a prompt, a broken reference, a break in the phase chain, or a contradiction or collision with no written priority.
- **remark:** an ambiguity, or a difference between `pm` and `generic` that breaks nothing.
- **minor:** style.
- **chain break:** a phase step that needs an input no earlier step produces, or a reference that points at a missing or different item.
- **contradiction:** two statements that demand opposite things.
- **collision:** two mechanisms (or identifiers) acting on the same fragment with incompatible effects, with no priority between them.
- `-lite`: the light CV mode of `/analyze` (see `.claude/commands/analyze.md`).

## Verdict (choose by this rule)

First split every finding into two lists:

- **introduced:** the line is in the diff, or the diff changed what a reference points to, or the diff made an existing problem worse (for example copied a known problem into other files).
- **baseline:** the same check already fails on `git show <base>:<file>`. Cite the file and line **at the base**; a finding without that evidence counts as introduced. Name the base explicitly (a commit hash, not just "master"), because it can move.

The verdict and N use **introduced** findings only:

- **do not merge:** at least one blocker, or a rule was lost, or `pytest` fails because of this branch.
- **can merge after fixing N:** no blocker, at least one remark (N = all introduced remarks, listed or not).
- **can merge:** only minor findings, or none.

Baseline findings go in a separate list: not capped at 15, summarized on one verdict line ("baseline: N blockers, M remarks; not blocking this merge"), and every baseline blocker gets a BACKLOG entry with a review date. Border case: a branch that only moves a line that carries an old error (for example a stale "rule 25" reference relocated inside `SKILL.md`) leaves it baseline; a branch that copies the error into another file makes it introduced.

A known open item (below) does not block the merge while it has not grown. If a check cannot be done (profile missing, tests cannot be separated from other people's failures), list it under "not checked"; the verdict is then at best "can merge after fixing".

## What to read

- The diff: `git diff <base>..<head> -- prompts skill .claude/commands` (default `master..HEAD`).
- **Whole files** for the passes that need context (items 5 and 9): the changed prompts in full, `skill/SKILL.md`, `.claude/commands/analyze.md`, `GLOSSARY.md`.
- The candidate profile: `skill/users/<id>/PROFILE.md` (local, not in git). Items 3 and 9 cannot be done without it; if absent, report them as not checked.

## Tests

Run the tests on a **clean export of the head**, not in the shared working tree (it may hold other people's uncommitted edits): `git archive HEAD | tar -x -C <scratch>`, copy the local profile in, and run `PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider` there (`git worktree add` is not read-only: it writes into `.git`). If you had to run in the shared tree, say so under "not checked". A failure you cannot attribute to something outside the branch counts as caused by the branch.

## Pass 0: fast pass

Finish it. Skip a later pass only if it depends on the broken item, and say so under "not checked".

1. **Meaning kept, directive clear.** Run `git diff --word-diff=color <base>..<head>` (a sentence cut from inside a long line must be visible). For every removed line, list each directive in it (sentences with never, must, only, always, banned, exception, not) and quote where the new text states it (file:line), or mark it LOST. A rule that lived inside a story must now read as a plain directive. A directive now carried by the profile counts as kept only if the prompt points to that profile section by name and the section is in `tests/test_profile_contract.py`. Optional last step: for each `.claude/memory/feedback_*.md` that names a prompt file, check its banned or required phrase still appears in that prompt; a missing one is LOST. Report the ledger size and the number LOST, and report a lost rule as: removed line (file:line in the old version) and where it should now be.
2. **No candidate data** in the prompts. Run `python -m pytest -q -p no:cacheprovider tests/test_prompt_isolation.py` (a skip means NOT CHECKED). Then search **all** of `prompts/`, `skill/SKILL.md` and `.claude/commands/` (not only the diff), case-insensitively, for every name variant, employer and project name (including multi-word headings), certificate name, the years-of-experience figure, city or country, and gendered forms taken from each profile in `skill/users/`. The lint skips multi-word employer headings and is case-sensitive, so an upper-case heading or a profile with no detected employers is invisible to it. Everything personal is read from the profile by section name.
3. **Profile sections exist.** (a) Run `python -m pytest -q -p no:cacheprovider tests/test_profile_contract.py`: it checks that every `skill_type: pm` profile in `skill/users/*/PROFILE.md` has the sections the engine reads (Name variants, Languages, Generation Rules, CV cutoff year, AI Tooling Paragraph, Vacancy Preferences) and that the engine still names each one. It skips when no such profile exists: a skip means NOT CHECKED, not passed. (b) Reverse check: every section a prompt tells the model to read or write (`grep -rnE 'PROFILE\.md|profile.s' prompts/pm`) must exist in the profile. A reference to a section that no longer exists is a blocker.
4. **Key mechanisms kept:** Requirements outweigh Responsibilities, the Unlock-condition check, the voice rule (third person banned; allowed inside a relative clause with its own subject), the language-level rule, North Star and the lead-signal rule.

## Pass A: chains and references (can run in parallel with B and C)

5. **Logic, chains and identifiers.** Walk the pipeline and check each step receives what the previous one produces: Phase 1 (North Star, branches, role balance) -> Phase 2 (Signal Coverage Table with Branch and Distinctive, lead-signal, Adaptation Plan) -> Phase 3 (Golden Rule, Tailoring Logic, Adaptation Plan) -> 3.5 -> 3.6 -> 3.7 -> Phase 4. Then check references:
   - List every numeric reference (`grep -rnE 'rule #?[0-9]+[a-c]?|Rule [0-9]+|§[0-9]'`) over `prompts/`, `skill/`, `.claude/commands/` **and** `core/`, `scripts/`, `tools/` (docstrings carry rule numbers) and resolve each against the numbering of **each** skill type. A number in a file shared by both skill types is a finding unless both use the same number; prefer naming the rule.
   - No rule number or section title is duplicated or shifted.
   - For each skill type, `ls prompts/<type>/` contains every file named in the `SKILL.md` Phase table. Every quoted heading, table column and JSON key that one phase names for another (for example "Lead-signal rule for Phase 3", `role_balance`, `p1.north_star`) appears verbatim in the producing file and, for JSON keys, in `contracts/pipeline.py` and the `SKILL.md` update-json blocks.
   - Trigger conditions agree with the `SKILL.md` Pipeline Flow (Phase 3.7, Phase 4, `-lite`), and each trigger is attached to the phase it names.
   - Rule priority is unambiguous (Golden Rule, lead-signal, Tailoring Logic, Unlock-condition); no condition can never fire; no step lacks an input.
   Output: a 5-7 line chain diagram and the list of breaks.

## Pass B: conflicts (items 6-8 together)

6. **Contradictions.** Rules that demand opposite things between: prompts and `skill/SKILL.md` / `.claude/commands/analyze.md`; prompts and the profile; different phases; the full CV and `-lite`; the project's Critical Rules in `CLAUDE.md`; and **prompts and the code that enforces them** (a lint, validator or schema in `core/`, `scripts/`, `contracts/`: if code enforces a rule that a prompt contradicts or omits, the prompt is wrong, a blocker). Also compare rules **inside one file**. For `-lite`, list every Phase 3 rule it changes and check the template line it overrides, and state which wins (for example when `-lite` runs only mechanical checks while the Critical Rules make the Phase 3.5 self-review mandatory). For each: both places (file:line), the conflict, which rule should win and why.
7. **Collisions of mechanisms.** One mechanism inserts or removes what another needs: the JD-echo check against the need for ATS keywords; Phase 3.6 removing sentences against the Key-results rule and canonical profile phrases; canonical verbatim phrases against the repetition and echo lints; the separator rule between roles against a compact layout; Phase 3.7 against the Adaptation Plan. Each collision needs a written priority.
8. **Exceptions.** For every rule with an exception: the exception is written next to the rule, narrow and testable; every file that applies or checks the rule knows it; it does not conflict with another rule or a profile line; no unwritten exceptions (places where the rule is bypassed in practice). Examples to check: the voice rule exception; first-person verbs in Ukrainian are not a violation; the Unlock-condition ("a flagged ambiguity is not a license to include"); language (English by default, Ukrainian on request); "never edit an applied document" against creating a `_v2` file.

## Pass C: personalization (item 9)

9. **Prompts must suit any profile.** The engine and the skill type say how to work; a person's facts, preferences, style and bans live only in the profile.
   - Classify each rule: universal / universal for the skill type / personal (belongs in the profile).
   - **Profile-swap check:** keep the skill type (a Product Manager or Product Owner) and swap only the person: other experience, country, language level, gender; no certificates; no personal projects. A rule that then becomes inapplicable, false or meaningless is a finding (a rule that only needs the profile to supply a different value is fine).
   - Look for hard-wiring in logic, not only data: assumptions about country, languages, English level, an AI project, a certificate; examples taken from one person's experience; bans that grew out of one person's corrections; rule order and weight tuned to one person's strengths and gaps.
   - For each finding: keep as universal, generalize, or move to the profile (name the section).

## Report format

A one-line verdict, then the findings, blockers first:

`file:line | what is wrong | severity (blocker / remark / minor)`

Report all blockers and at most 15 remarks and minors (state how many more there are). End with: what was checked and what was **not** checked.

## Known open item (not a new finding)

`prompts/pm/phase4_cover.md`: the Ukrainian example with a third-person relative clause conflicts with the cover rule (deferred, low priority; see BACKLOG "Ukrainian-output polish"). It does not block a merge while its baseline count stays at 1: `grep -rnE 'який працює|яка працює' prompts | wc -l` gave 1 on 2026-10-07. A higher count means it spread and is an introduced finding.
