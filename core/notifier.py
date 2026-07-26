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
    user_id: int,
    event: PipelineEvent,
    vacancy_id: int | None = None,
    *,
    title: str = "",
    body: str = "",
) -> None:
    """Persist event to DB and fan-out to enabled channels.

    Never raises — all channel errors are logged and swallowed so a notification
    failure never aborts the pipeline.
    """
    try:
        await database.insert_notification(user_id, event, vacancy_id, title, body)
    except Exception as exc:
        log.error("notifier: DB insert failed (user=%d event=%s): %s", user_id, event, exc)

    if event in _WEB_PUSH_EVENTS:
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
