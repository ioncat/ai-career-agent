# Multi-user watchlist

> A running list of places that assume ONE user (or one machine) and will certainly need a second look when the product goes multi-user (see EPIC-25, authorization and billing). Not a backlog: nothing here is a defect today. Any agent that notices such a place while working adds a row (append only, newest at the bottom, never delete; mark a row `done <hash>` when it is handled). Created 2026-10-09 at the owner's request.

**Columns:** `Area` (where), `What assumes one user` (the single-user fact), `What will have to change` (the likely work), `Found` (date, who or which review), `Status` (`watch` or `done <hash>`).

| # | Area | What assumes one user | What will have to change | Found | Status |
|---|---|---|---|---|---|
| 1 | `notifications` retention (`db/database.py`) | The 2000-row cap is shared by all users, so one user's burst can push out another user's unread events | Cap per user (or per user plus a system cap); revisit the 90-day rule for unread rows | 2026-10-09, notifications phase 2 | watch |
| 2 | System events (`user_id` NULL) | One read flag for everybody: one user's "read all" clears a system event for all | Per-user read state for system events (a link table) | 2026-10-09, review RF-024 | watch |
| 3 | `mark_notification_read(id)` | It does not check which user owns the row | Check ownership in every read and write of notifications | 2026-10-09, review RF-031 | watch |
| 4 | Telegram | One bot, one `TELEGRAM_CHAT_ID` from `.env`; the monitor and the health check send to that single chat | Chat id per user (profile or settings), the router chooses the recipient; system alerts go to an owner chat | 2026-10-09, notifications design | watch |
| 5 | Web Push | `push_subscriptions` has `user_id`, but the sender and tests use `user_id=1` | Subscriptions per user end to end, test with two users | 2026-10-09, notifications design | watch |
| 6 | API defaults | `web/api.py` takes `user_id: int = 1` as the default on several endpoints (notifications, mark-all-read, others) | Take the user from authentication, never from a default | 2026-10-09, audit | watch |
| 7 | LLM configuration | `phase_llm_config`, `provider_config_snapshots` and `system_kv` have no `user_id`; `config_store.py` says "single-user today" | Per-user settings or an explicit split between a global (admin) and a per-user part | 2026-10-09, audit | watch |
| 8 | Active profile | `skill/active_user` is one global file; the local `/analyze` flow assumes one active user at a time | A user chosen per session or per request, not per machine | 2026-10-09, audit | watch |
| 9 | Job feeds and the monitor | `feeds.json` and `seen_jobs.json` are global, one set of feeds for everyone | Feeds per user (or a shared pool with a per-user filter), per-user "seen" state | 2026-10-09, audit | watch |
| 10 | SQLite file | One database file, single writer | Check concurrency limits; decide on keeping SQLite with a write queue or moving to a server database | 2026-10-09, audit | watch |
| 11 | Profile files and secrets | Profiles are local files in `skill/users/<id>/`; `.env` holds one set of keys | A storage and access model for profiles; per-user API keys or a billing relay | 2026-10-09, audit | watch |
| 12 | Backups | `db/backups/` is a manual convention for one owner | Automatic, per-environment backups and a restore drill before real users | 2026-10-09, audit | watch |

*Rows 6 to 12 come from a quick read of the code and the live schema on the day this file was created; each deserves a proper check when the multi-user work starts, they are pointers, not findings.*
