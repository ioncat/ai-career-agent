# Agent rules: career-agent addendum

> The common rules for every agent session live **outside the repo**, in `E:\My files\0 My_Dev\my_prj\my_claude\AGENT_TEAM_RULES.md` (cross-project, personal; the role briefs are in `my_claude\AGENT_ROLES\`). Read that file first. This page holds only what is specific to `career-agent`; rule numbers are the same as in the common file, so "rule 5" means the same thing in both. Role addenda for this project: [`roles/`](roles/).

## Project specifics, by rule

| Rule | In this project |
|---|---|
| 1-3 Reports | The dispatcher session is named **CTO**. The owner's panel is a private Artifact page (decisions, his queue, one row per agent) kept by the dispatcher |
| 4-5 Talking to the owner | Chat language is Russian; the table headings are in Russian: Вопрос / Задача, Суть проблемы, Контекст, Сам вопрос, Варианты, Срочность, Подробности. Icons ⚠️ 🔴 ✅ ➡️ ⏳ are between the dispatcher and the owner only |
| 6-7 Commits | The working tree is shared by all sessions. Use a temporary index (`GIT_INDEX_FILE`) when the shared index holds other people's staged changes |
| 9 File ownership | See the table below |
| 10 Database | The live DB is `db/agent.db`; backups go to `db/backups/` (or a dated copy next to it); a migration is an idempotent startup step in `db/database.py`; a live write waits for the owner's word and the backend restart is his |
| 11 Services | The backend, parser, PDF service and job monitor run through `launcher.py`; the owner restarts them. Docker is not used on the owner's machine |
| 12 Personal data | The repo is public: no names, e-mails, chat ids, tokens, employers or stories of the candidate in tracked files. The profile `skill/users/<id>/PROFILE.md` is local and gitignored; guard tests: `test_no_personal_data.py`, `test_prompt_isolation.py` |
| 14 Quality gates | Tests: `python -m pytest`; Flutter: `flutter test` and `flutter analyze`. Changes to `prompts/`, `skill/SKILL.md`, `.claude/commands/` also need the review checklist (`PROMPT_REVIEW_CHECKLIST.md`) and the guard tests (`test_prompts_directives_only`, `test_profile_contract`, `test_prompts_no_profile_overlap`) |
| 15 Docs | `docs/delivery/CHANGELOG.md` and `BACKLOG.md`, following `documentation-conventions.md`. When you notice a place that assumes one user (a shared cap, a global setting, a default `user_id=1`), add a row to `docs/delivery/MULTIUSER_WATCHLIST.md` (append only) |
| 16 UI | The Flutter desktop app; there is no browser preview, the owner confirms in the running app. Read the CLAUDE.md section "Vacancy Detail Header/Action-Bar" before touching the vacancy detail screen |
| 18 Session log | `.claude/sessions/YYYY-MM-DD-short-description.md` (gitignored) |
| 19 Tests and the live DB | `tests/conftest.py` has an autouse fixture that sets `DB_PATH` to a throwaway file for every test; a test that starts the app (TestClient) therefore cannot open `db/agent.db` |

## File ownership (rule 9)

| Owner | Files |
|---|---|
| Backend session | `core/`, `db/`, `web/`, `tools/`, `scripts/`, `services/`, `adapters/`, `contracts/`, and their tests |
| Flutter agent | `flutter/` and its tests |
| Prompt owner | `prompts/pm/`, `skill/SKILL.md`, `.claude/commands/`, `docs/delivery/PROMPT_REVIEW_CHECKLIST.md`, `docs/delivery/PROMPT_EDITING_RULES.md`. `prompts/generic/` is frozen: nobody touches or reviews it |
| Dispatcher | `docs/delivery/AGENT_RULES.md`, `docs/delivery/roles/`, the owner's panel |
| Reviewer | `docs/delivery/REVIEW_FINDINGS.md` (the findings register), nothing else (read-only otherwise) |
| Shared, each for its own entries | `docs/delivery/CHANGELOG.md`, `docs/delivery/BACKLOG.md`, `docs/delivery/ROADMAP_Q4.md` (status column) |

## Role addenda

[dispatcher](roles/dispatcher.md) · [backend](roles/backend.md) · [flutter](roles/flutter.md) · [prompt-owner](roles/prompt-owner.md) · [code-reviewer](roles/code-reviewer.md). Startup line for a new session: "Read `E:\My files\0 My_Dev\my_prj\my_claude\AGENT_ROLES\<role>.md`, then `docs/delivery/roles/<role>.md`, and follow them."
