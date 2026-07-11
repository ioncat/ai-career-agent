"""
tests/test_notifier.py — tests for core/notifier.py.

Verifies event routing: DB insert always called; Web Push called only for
_WEB_PUSH_EVENTS; errors swallowed silently.
"""

from unittest.mock import AsyncMock, patch

import pytest

from core.notifier import PipelineEvent, _WEB_PUSH_EVENTS, notify


# ── Helpers ───────────────────────────────────────────────────────────────────

def _patch_db(return_value=1):
    return patch("core.notifier.database.insert_notification", new_callable=AsyncMock,
                 return_value=return_value)

def _patch_push():
    return patch("core.notifier._try_web_push", new_callable=AsyncMock)


# ── notify() — DB insert always happens ──────────────────────────────────────

@pytest.mark.asyncio
async def test_notify_always_inserts_to_db():
    with _patch_db() as mock_db, _patch_push():
        await notify(1, PipelineEvent.ANALYSIS_DONE, 42, title="done", body="fit 8/10")
        mock_db.assert_awaited_once_with(1, PipelineEvent.ANALYSIS_DONE, 42, "done", "fit 8/10")


@pytest.mark.asyncio
async def test_notify_without_vacancy_id():
    with _patch_db() as mock_db, _patch_push():
        await notify(1, PipelineEvent.ANALYSIS_FAILED, title="err")
        mock_db.assert_awaited_once_with(1, PipelineEvent.ANALYSIS_FAILED, None, "err", "")


# ── Web Push routing ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("event", list(_WEB_PUSH_EVENTS))
async def test_notify_triggers_web_push_for_push_events(event):
    with _patch_db(), _patch_push() as mock_push:
        await notify(1, event, 10, title="t", body="b")
        mock_push.assert_awaited_once_with(1, "t", "b")


@pytest.mark.asyncio
async def test_notify_no_web_push_for_new_vacancy():
    """NEW_VACANCY is not in _WEB_PUSH_EVENTS — Telegram handles it."""
    assert PipelineEvent.NEW_VACANCY not in _WEB_PUSH_EVENTS
    with _patch_db(), _patch_push() as mock_push:
        await notify(1, PipelineEvent.NEW_VACANCY, 5)
        mock_push.assert_not_called()


@pytest.mark.asyncio
async def test_notify_web_push_uses_event_name_as_title_fallback():
    """When title is empty, _try_web_push receives event value as title."""
    with _patch_db(), _patch_push() as mock_push:
        await notify(1, PipelineEvent.ANALYSIS_DONE, 1)
        call_args = mock_push.call_args
        assert call_args[0][1] == PipelineEvent.ANALYSIS_DONE  # positional title arg


# ── Error resilience ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notify_db_error_does_not_raise():
    """DB failure must be silently swallowed — pipeline must not abort."""
    with patch("core.notifier.database.insert_notification", new_callable=AsyncMock,
               side_effect=RuntimeError("DB down")):
        await notify(1, PipelineEvent.ANALYSIS_DONE, 1)  # must not raise


@pytest.mark.asyncio
async def test_notify_web_push_error_does_not_raise():
    with _patch_db():
        with patch("core.notifier._try_web_push", new_callable=AsyncMock,
                   side_effect=RuntimeError("push service unreachable")):
            await notify(1, PipelineEvent.ANALYSIS_DONE, 1)  # must not raise


# ── PipelineEvent enum ────────────────────────────────────────────────────────

def test_pipeline_event_values():
    assert PipelineEvent.ANALYSIS_DONE   == "analysis_done"
    assert PipelineEvent.ANALYSIS_FAILED == "analysis_failed"
    assert PipelineEvent.CV_DONE         == "cv_done"
    assert PipelineEvent.CV_FAILED       == "cv_failed"
    assert PipelineEvent.COVER_DONE      == "cover_done"
    assert PipelineEvent.COVER_FAILED    == "cover_failed"
    assert PipelineEvent.NEW_VACANCY     == "new_vacancy"
