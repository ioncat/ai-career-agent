# Review findings register

> Owner of this file: the Code and Security Reviewer (the only agent that edits it). Every finding of every review goes here, so nothing is lost when a message scrolls away. Not a backlog: it records what was found and what became of it. A finding that needs real work is promoted by the dispatcher to `BACKLOG.md` as one line that links here.

**Status values:** `open` (not fixed, no decision), `fixed <hash>` (fixed in that commit, confirmed by a re-check), `accepted` (the owner or the author decided to live with it, reason in the note), `wontfix` (not a defect after discussion), `backlog` (promoted to `BACKLOG.md`).
**Severity:** `Med` (fix before merge or push), `Low` (worth fixing, author's call), `Info` (observation), `Sec` (security finding, any level).
**Rules:** Medium and security findings are always recorded; Low and Info are recorded too, so an unfixed one stays visible. On every re-check the reviewer updates the status of the findings in that range. IDs only grow (RF-001, RF-002, ...); never reuse or renumber.

| ID | Date | Range | Sev | Where | Finding | Status | Note |
|---|---|---|---|---|---|---|---|
| RF-001 | 2026-10-09 | 38c0ed7 | Med | core/failure_projection.py:73 | A stored generation failure was projected at any status, so during a retry the old failure kept a live Retry | fixed 9e9b7d7 | |
| RF-002 | 2026-10-09 | 38c0ed7 | Med | db/database.py:720 | `generation_failure.code` and `failure.code` could differ for one record | fixed 9e9b7d7 | |
| RF-003 | 2026-10-09 | 38c0ed7 | Low | core/generation_failure.py:40 | Soft-failure codes matched by substrings of Russian tool texts | fixed 9e9b7d7 | shared constants, tests use real tool responses |
| RF-004 | 2026-10-09 | 38c0ed7 | Low | adapters/cv_adapter.py:108 | Any HTTPError became `pdf_service_unreachable` | fixed 9e9b7d7 | only connect errors now |
| RF-005 | 2026-10-09 | 38c0ed7 | Low | core/failure_projection.py:70 | `at` for fetch/analysis failures is `updated_at`, approximate | accepted | until the stored time exists (phase 2 schema, phase 3 wiring) |
| RF-006 | 2026-10-09 | 38c0ed7 | Info | tools/cv_cover.py:68, cv_generate.py:109 | "Vacancy not found" has no code of its own | accepted | no row, nothing to show |
| RF-007 | 2026-10-09 | 38c0ed7 | Info | core/generation_failure.py:38,75 | Wrong comment about check order; duplicated check | fixed 9e9b7d7 | |
| RF-008 | 2026-10-09 | d531c30 | Med | flutter/lib/widgets/failure_widgets.dart:87 | FailureBlock did not know the status: Retry active during a run (409 on second click) | fixed 583f2dc | |
| RF-009 | 2026-10-09 | d531c30 | Med | flutter/lib/widgets/failure_widgets.dart:94 | Retry CV ignored the language of the failed run | fixed 583f2dc | uses `failure.lang` (backend 9e9b7d7) |
| RF-010 | 2026-10-09 | d531c30 | Low | failure_widgets.dart:160 | `at` parsed but not shown | fixed 583f2dc | |
| RF-011 | 2026-10-09 | d531c30 | Low | flutter/lib/models/vacancy_failure.dart:40 | Hard `as String?` casts could break the whole list parse | fixed 583f2dc | |
| RF-012 | 2026-10-09 | d531c30 | Low | failure_widgets.dart:98 | PDF failure without target silently rendered the CV | fixed 583f2dc | |
| RF-013 | 2026-10-09 | d531c30 | Low | flutter/test/vacancy_failure_test.dart | No test that FailureBlock renders in both header states | backlog | in BACKLOG Icebox as a widget test; the retry mapping itself is unit-tested since 583f2dc |
| RF-014 | 2026-10-09 | d531c30 | Info | flutter/lib/widgets/vacancy_card.dart:370 | FailurePill built in two branches | fixed 583f2dc | |
| RF-015 | 2026-10-09 | 9e9b7d7 | Med | core/failure_projection.py:87, db/database.py:306 | Recovery set `cv_queued`, which nothing processes; the failure mark was hidden for good | fixed 3244d84 | recovery to `analyzed` / `cv_generated` |
| RF-016 | 2026-10-09 | 9e9b7d7 | Info | core/failure_projection.py:87 | An old PDF failure came back after a new CV | fixed 3244d84 | |
| RF-017 | 2026-10-09 | 3244d84..583f2dc | Low | db/database.py:309,315 | Recovery lowers the status to `analyzed` / `cv_generated` even if a higher one was held before the regeneration | open | same semantics as the existing rollback in fail_generation; author's call |
| RF-018 | 2026-10-09 | 3244d84..583f2dc | Low | db/database.py:309 | A run interrupted by a restart leaves no error; the vacancy silently returns to analyzed | open | |
| RF-019 | 2026-10-09 | 3244d84..583f2dc | Info | flutter/lib/models/vacancy_failure.dart:31 | `_runningStatuses` duplicates the backend set; no sync test across languages | open | |
| RF-020 | 2026-10-09 | 3244d84..583f2dc | Info | scripts/vacancy_track.py:167 | Setting `cv_generated` by hand through the CLI now also clears a pdf/cv failure | open | rare |
| RF-021 | 2026-10-09 | d663850 | Med | tests/conftest.py:26 | The test guard sets only the env var `DB_PATH`, which `db/database.py` does not read; a direct `database.*` call still opens the live DB | open | author is fixing (monkeypatch `database._db_path`) |
| RF-022 | 2026-10-09 | d663850 | Low | db/database.py:2021 | `INSERT OR IGNORE` also swallows NOT NULL/CHECK errors; `notify(title=None)` is dropped with a "duplicate" log | open | prefer `ON CONFLICT DO NOTHING` on the key index |
| RF-023 | 2026-10-09 | d663850 | Low | db/database.py:2036 | Retention deletes unread events and the 2000 cap is shared by all users | open | the owner accepted 90 days / 2000; the unread case is not written down |
| RF-024 | 2026-10-09 | d663850 | Low | db/database.py:2094 | A system event (user_id NULL) has one read flag for everybody | open | harmless with one user |
| RF-025 | 2026-10-09 | d663850 | Low | db/database.py:355 | ROLLBACK after a failure before BEGIN raises "no transaction is active" and hides the original error | open | diagnostics only |
| RF-026 | 2026-10-09 | d663850 | Info | db/database.py:2025 | Exception in prune after commit makes notify log "DB insert failed" though the row is saved | open | |
| RF-027 | 2026-10-09 | d663850 | Sec | db/database.py (notifications), future POST /api/events | `code`, title and body are not length-limited or checked against the vocabulary (`key` is capped at 200) | open | close before phase 5 (POST /api/events); in BACKLOG |
| RF-028 | 2026-10-09 | d663850 | Info | docs | The migration was applied to the live DB by an accidental test run without a backup; no note that other databases need a backup first | open | table was empty, owner accepted the state |
| RF-029 | 2026-10-09 | 9e9b7d7 | Info | web/api.py:1622 | The render-pdf endpoint reports every transport error as "pdf-service unavailable" with HTTP 503, though the code now tells unreachable from a failed exchange | open | the `code` field is right; only the reason text and HTTP status are generic |
