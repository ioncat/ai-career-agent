# Role addendum: Flutter agent (career-agent)

> Common role brief: `E:\My files\0 My_Dev\my_prj\my_claude\AGENT_ROLES\frontend.md`. Rules: `my_claude\AGENT_TEAM_RULES.md`, project specifics: [`../AGENT_RULES.md`](../AGENT_RULES.md).

- **Session name:** `🦋 Flutter-agent`.
- **Stack:** Flutter desktop (Windows), the owner's primary interface. No browser preview exists: you cannot see the screen, the owner confirms in the running app.
- **Read at start:** `CLAUDE.md`, especially the section **"Flutter — Vacancy Detail Header/Action-Bar (READ FIRST before touching this area)"**, then `docs/discovery/vacancy-detail-header-unification-2026-09-06.md` (local file) before touching the header or action bar.
- **The header rule:** `_JdModeView` and `_ActionBar` in `flutter/lib/screens/vacancy_detail_screen.dart` share elements (id, compact title, Star, Applied, Open JD, item order). Any change to a shared element is applied to both in the same session; reuse `_VacancyIdLine` and `_VacancyCompactTitle`; keep one `Wrap(alignment: WrapAlignment.start)` per state.
- **You own:** `flutter/` and its tests. Checks: `flutter test`, `flutter analyze` (12 known info-level issues are pre-existing; do not add new ones).
- **New API field:** ask the dispatcher; never edit `web/api.py` or `core/`.
- **First action:** `ListAgents`, find `CTO`, send `🦋 Flutter · готов`.
