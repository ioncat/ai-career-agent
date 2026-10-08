# Roadmap Q4 2026: a working Flutter app on the shared engine

> Written 2026-10-07, updated the same evening. This is the map; the work items live in [BACKLOG.md](BACKLOG.md). Update the Status column when a step moves.

## Goal

A working **Flutter app where any candidate profile plugs into the same engine**.

**Done when:**
1. Flutter can use every backend tool (the app is not a weaker subset of the chat flow).
2. The generated CV is good: the user needs **2-3 edits at most** to reach the result they want. Measured by `p3.changes_count` plus a side-by-side check of chat, API and CLI output on the same vacancy.
3. **MCP:** the user can connect their own agent (today Claude Code) to the app and refine a CV through it. A local skill that helps work with the app through MCP may ship with it.

**Next threshold (after the above):** authorization and billing (EPIC-25, design first).

## Why this is not done yet (the root)

A good CV is produced in the chat today because quality is built there: the model sees the full skill rules, and the owner's corrections accumulate in memory and in `PROFILE.md`. The Flutter/API pipeline sees only the profile and one phase prompt, so it gives a weaker CV. The knowledge of what "good" means lives in dialogue and memory, not in the artifacts the pipeline reads. Sources: [conversational-refinement-gap.md](../discovery/conversational-refinement-gap.md), [per-phase-llm-routing.md](../discovery/per-phase-llm-routing.md), [profile-prompt-isolation-discovery-2026-10-04.md](../discovery/profile-prompt-isolation-discovery-2026-10-04.md).

## The map

| # | Goal | Why | Problem | Caused by | Action | Backlog | Status |
|---|---|---|---|---|---|---|---|
| 1 | Measure "good" | The 2-3 edits criterion needs a number | No metric; chat and Flutter output never compared on one vacancy | Quality judged by eye, only in the chat | Run 2-3 vacancies through chat, API and CLI; compare tone, barriers, positioning, language; count edits | Quality Parity (last item); **new: measurement** | first measurement done (#1693, 2026-10-07): the app output was far below chat because of a provider bug (fixed); after the fix fit and structure match, 2 em-dashes left. Repeat on 2 more vacancies and with the app's model at higher effort |
| 2 | Flutter quality = chat quality | The main gap | API and CLI see fewer quality rules | Rules live in `SKILL.md` and memory | Quality Parity: rules into system prompts and profile | LLM Quality Parity | partly: the root cause of the first gap found and fixed (the user-level rules leaked into `claude -p`); rules extraction (Quality Parity) not started; model and effort difference open |
| 3 | Flutter uses all backend tools | Criterion 1 | No Phase 2.5, 3.6, 3.7, Light mode, ATS keyword step in the app/API | These phases grew in the chat | Add to API and UI | Phase 2.5 in Flutter (4-C4), Phase 3.8 ATS Keyword Coverage, Worker-Critic | not started |
| 4 | Dialogue and edits inside Flutter | Quality is made in iterations | Flutter "Analyze" is a one-shot batch | No feedback loop in the app | Hybrid: Annotated CV Revision, targeted interactive points | conversational-refinement-gap, Annotated CV Revision | not started (design sketch: `docs/discovery/flutter-dialogue-points-2026-10-07.md`, local) |
| 5 | Profile as a structure | Any profile plugs in | Three partial representations; corrections stay in memory | Profile grew as Markdown | JSON schema with fact annotations; correction loop; structured constraints for the Critical Blocker checks and a JD-facts extraction ([jd-facts-and-profile-constraints-design-2026-10-08.md](../discovery/jd-facts-and-profile-constraints-design-2026-10-08.md)) | Profile isolation (P1), EPIC-24 keep-or-deprecate decision, Stage 1 hard-coded values | schema draft only; JD-facts design note written 2026-10-08, awaiting approval (very important, see the section above) |
| 6 | Reliable retrieval of profile facts | The CV uses the right facts | The right evidence block is not always found | No deterministic evidence lookup | Mandatory evidence scan per JD signal | **new** (north-star discovery section 4) | not started |
| 7 | Clear, clean prompts | Predictable output | Redundancy, order, no self-check in Phase 2 | Rules added as patches | Prompt clarity/structure pass | Prompt clarity/structure pass (P1) | directives-only cleanup done and merged (prompts, `SKILL.md`, `analyze.md`, guarded by a test); clarity pass not started |
| 8 | Role axes as an entity | Precise role analysis and ATS keywords | No Analytics axis; axes hard-wired; no drift watch | First set built from PM/PO only | Audit script on the database; axis set per profile with versions | [role-axes-design-2026-10-04.md](../discovery/role-axes-design-2026-10-04.md); **new** | design draft awaiting approval |
| 9 | Engine free of personal data | Multi-user | Leaks into prompts; name in Settings; chat ids in a public repo | Single-user start | Cleanup, per-user name, leak tests, history rewrite | done on branch `refactor/prompts-directives-only-2026-10-04` | done: merged to `master`, history cleaned on GitHub (2026-10-07) |
| 10 | MCP | Criterion 3 | Only a stub (`docs/discovery/mcp-server.md`, July) | Never designed | Design the MCP surface and the local skill | **new** | not started |
| 11 | Authorization and billing | A product for other people | Absent | Personal tool | Design, then build | EPIC-25 | design first |

## Critical design item: JD facts and profile constraints (owner: very important, do not lose)

The Stage 1 blocker checks in `tools/cv_prefilter.py` hard-code one candidate's values (English level, country, titles, mobile, remote format). That breaks the Q4 criterion "any candidate profile plugs into the same engine" and lets Stage 1 and the Stage 2 prompt disagree. Decision of 2026-10-08: no patches in the old style, solve it by design. A vacancy is turned into a JSON of facts (each with a verbatim quote), the profile carries structured constraints, and a plain comparison does the check. The same facts feed the role axes (step 8), ATS keywords (step 3), filters in the app and MCP (step 10).

Design note: [jd-facts-and-profile-constraints-design-2026-10-08.md](../discovery/jd-facts-and-profile-constraints-design-2026-10-08.md). Status: draft awaiting approval; the constraint fields need the profile schema (step 5). Until it is decided, the Stage 1 English item in BACKLOG stays parked (a draft bridge was written and reverted on 2026-10-08).

## Order

1 -> 2 and 3 -> 5 and 6 -> 4 -> 10 -> 11. Steps 7 and 8 run in parallel. Step 9 closes with the branch merge. The JD-facts and profile-constraints design (previous section) is decided together with step 5.

Reasoning: measure first so every later step has a number. Rules and missing phases (2, 3) before profile structure (5, 6), because they are cheaper and show how much of the gap remains. The dialogue loop (4) only if the gap persists. MCP (10) comes after quality, since an external agent would call the same unfinished tools. Auth and billing (11) last.

## Progress log

- **2026-10-08** — Rule 23 (cases stay out of the CV, Summary included) and the title-terms rule moved into the user's profile; three layers guard prompt edits (editing rules, a hook, an overlap test). Stage 2 prefilter compares CEFR levels; the fit score counts each piece of evidence once. Found that the Stage 1 checks in `tools/cv_prefilter.py` hard-code one candidate's values (English level, country, titles, mobile, remote); the owner proposed splitting the check into JD facts, profile constraints and a plain comparison; design note: [jd-facts-and-profile-constraints-design-2026-10-08.md](../discovery/jd-facts-and-profile-constraints-design-2026-10-08.md). The narrow English fix is parked until that is decided: a draft bridge was written and reverted the same day (patch kept locally), the owner chose to wait for the design.
- **2026-10-07** — The cleanup branch was merged into `master` and the rewritten history (chat ids replaced) was force-pushed; the old remote branch was deleted. Added the repeatable `PROMPT_REVIEW_CHECKLIST.md` and ran it with three independent reviewers; their findings were fixed. Examples taken from the candidate's own history were replaced with neutral ones; `prompts/generic/` was frozen. First chat-versus-app measurement on #1693: the app's Phase 3 returned a question instead of a CV because the user's own CLAUDE.md rules leaked into `claude -p`; fixed with an unattended-run guard (`ClaudeCodeProvider(interactive=False)`), after which the app output matches the chat flow in structure and decision.

## Decisions pending from the owner

- **Very important (owner):** decide the JD-facts / profile-constraints design (step 5): [jd-facts-and-profile-constraints-design-2026-10-08.md](../discovery/jd-facts-and-profile-constraints-design-2026-10-08.md). Until then the Stage 1 English item stays parked.
- Approve the role-axes design (step 8) and answer its four questions.
- Answer the six open questions of `profile-schema-v0-2026-10-04.md` (step 5).
- Choose the dialogue option for step 4 (structured cards in Flutter, chat, or hybrid); the sketch is in the local discovery note.
- Next measurement: the same vacancy with the app's model at higher effort, or automatic correction of mechanical violations in the app first.
- Read the two CVs of the #1693 measurement and say how many edits each would need (the 2-3 edits criterion).
