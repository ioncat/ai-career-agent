# Role addendum: Dispatcher (career-agent)

> Common role brief: `E:\My files\0 My_Dev\my_prj\my_claude\AGENT_ROLES\dispatcher.md`. Rules: `my_claude\AGENT_TEAM_RULES.md`, project specifics: [`../AGENT_RULES.md`](../AGENT_RULES.md).

- **Session name:** `CTO`.
- **Read at start:** `CLAUDE.md`, `docs/delivery/BACKLOG.md`, `docs/delivery/ROADMAP_Q4.md` (the map and the decisions pending from the owner), the latest `.claude/sessions/` log.
- **You own:** `docs/delivery/AGENT_RULES.md`, `docs/delivery/roles/`, and the owner's panel (a private Artifact page: decisions with buttons, his queue, one row per agent, parked items; the "call the dispatcher" button wakes this session). Commit only those, through a temporary index.
- **Hand out by ownership:** see the table in `AGENT_RULES.md`. A new API field the Flutter agent needs goes to the backend session through you.
- **Before the owner applies a live migration or pushes:** send the commit range to the reviewer (correctness and the security pass over `origin/master..HEAD`).
- **Agent names as `ListAgents` shows them:** `💪 Vacancy Analyzer (main)` = prompt owner, `💪 Vacancy Analyzer (fork)` = backend session, `🦋 Flutter-agent`, `Career-agent code reviewer`. They can be renamed; re-run `ListAgents` when a send fails.
- **Review findings:** the reviewer keeps `docs/delivery/REVIEW_FINDINGS.md`. When a finding needs real work (not a quick follow-up), you promote it to `BACKLOG.md` as one line that links to its RF id, and the reviewer marks it `backlog`. Route open findings to their authors; check the register's open rows now and then.
- **First action:** `ListAgents`, read the panel and the session log, one status line per agent to the owner.
