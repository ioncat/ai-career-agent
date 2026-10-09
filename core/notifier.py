"""core/notifier.py — Centralized pipeline event notification router.

All pipeline state changes (success / failure / progress) flow through notify().
Routing:
  - Every event → stored in DB notifications table (Flutter polls /api/notifications).
  - Selected events → Web Push (background notification when browser is open).
  - Telegram → NOT handled here; new vacancy only, sent by rss_watcher directly.

Usage:
    from core.notifier import notify, PipelineEvent
    await notify(user_id=1, event=PipelineEvent.ANALYSIS_DONE, vacancy_id=42,
                 title="Analysis done — Stripe PM", body="Fit 8/10 · apply")
"""

from __future__ import annotations

import logging
from enum import StrEnum

from db import database

log = logging.getLogger(__name__)


# ── Event types ───────────────────────────────────────────────────────────────


class PipelineEvent(StrEnum):
    ANALYSIS_DONE   = "analysis_done"
    ANALYSIS_FAILED = "analysis_failed"
    CV_DONE         = "cv_done"
    CV_FAILED       = "cv_failed"
    COVER_DONE      = "cover_done"
    COVER_FAILED    = "cover_failed"
    EDITORIAL_AUDIT_DONE   = "editorial_audit_done"
    EDITORIAL_AUDIT_FAILED = "editorial_audit_failed"
    NEW_VACANCY     = "new_vacancy"   # informational; rss_watcher is the sender


# Events that also trigger a Web Push (browser background notification)
_WEB_PUSH_EVENTS: frozenset[PipelineEvent] = frozenset({
    PipelineEvent.ANALYSIS_DONE,
    PipelineEvent.ANALYSIS_FAILED,
    PipelineEvent.CV_DONE,
    PipelineEvent.CV_FAILED,
    PipelineEvent.COVER_DONE,
    PipelineEvent.COVER_FAILED,
    PipelineEvent.EDITORIAL_AUDIT_DONE,
})


# ── Public API ────────────────────────────────────────────────────────────────


async def notify(
    user_id: int | None,
    event: PipelineEvent,
    vacancy_id: int | None = None,
    *,
    title: str = "",
    body: str = "",
    severity: str | None = None,
    origin: str = "auto",
    code: str | None = None,
    key: str | None = None,
) -> None:
    """Persist event to DB and fan-out to enabled channels.

    The first five parameters are the original signature and keep working unchanged. New, all
    optional: `severity` (success | info | warning | error; default from the event name),
    `origin` (user | auto | system), `code` (core/failure_codes.py, for failures) and `key`
    (idempotency key: an event with a key that already exists is neither stored nor pushed
    again). `user_id` None is a system event (no per-user Web Push).

    Never raises — all channel errors are logged and swallowed so a notification
    failure never aborts the pipeline.
    """
    try:
        # Only what was set is passed on, so a legacy call reaches the DB layer exactly as before.
        extra = {
            name: value
            for name, value in (("severity", severity), ("code", code), ("key", key))
            if value is not None
        }
        if origin != "auto":
            extra["origin"] = origin
        stored = await database.insert_notification(user_id, event, vacancy_id, title, body, **extra)
        if stored is None:
            log.info("notifier: duplicate event skipped (user=%s event=%s key=%s)", user_id, event, key)
            return
    except Exception as exc:
        log.error("notifier: DB insert failed (user=%s event=%s): %s", user_id, event, exc)

    if event in _WEB_PUSH_EVENTS and user_id is not None:
        try:
            await _try_web_push(user_id, title or event, body)
        except Exception as exc:
            log.warning("notifier: web push channel error (user=%d): %s", user_id, exc)


# ── Internal ──────────────────────────────────────────────────────────────────


async def _try_web_push(user_id: int, title: str, body: str) -> None:
    try:
        from core.push import send_push
        await send_push(user_id=user_id, title=title, body=body)
    except Exception as exc:
        log.warning("notifier: web push failed (user=%d): %s", user_id, exc)
