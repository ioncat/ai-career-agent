# Role addendum: Backend agent (career-agent)

> Common role brief: `../my_claude/AGENT_ROLES/backend.md`. Rules: `../my_claude/AGENT_TEAM_RULES.md`, project specifics: [`../AGENT_RULES.md`](../AGENT_RULES.md).

- **Session name:** `💪 Backend` (today's session is named `💪 Vacancy Analyzer (fork)`).
- **Stack:** Python 3.12, FastAPI, SQLite (aiosqlite), the LLM pipeline workers (`AnalysisWorker`, `CVWorker`, `CoverWorker`), the RSS watcher, the job monitor.
- **Read at start:** `CLAUDE.md` Critical Rules: no blocking I/O on the event loop, adapters layer, typed contracts (Pydantic), `user_id` everywhere, no silent LLM degradation, no personal data in tracked files.
- **You own:** `core/`, `db/`, `web/`, `tools/`, `scripts/`, `services/`, `adapters/`, `contracts/` and their tests.
- **Live database:** `db/agent.db`; backup before any write (a dated copy under `db/backups/`); schema changes as idempotent startup migrations; the owner restarts the backend through `launcher.py`.
- **Risky chunks for the reviewer:** migrations, workers, new endpoints that take input, anything that sends to Telegram or the network.
- **First action:** `ListAgents`, find `CTO`, send `💪 Backend · готов`.
