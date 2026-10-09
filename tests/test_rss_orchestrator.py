"""
tests/test_rss_orchestrator.py — RSSWatcher B4 orchestration flow.

Tests: _process chains fetch_jd → cv_analyze → push_result.
Mocks all external calls (fetch_jd, cv_analyze, send_push, database).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from core.rss_watcher import RSSWatcher
from db import database


@pytest_asyncio.fixture(autouse=True)
async def _temp_database(tmp_path):
    """RSSWatcher._process looks the vacancy up in the database before it fetches; those lookups used to run
    against whatever database was configured, which by default is the live one. Give every test its own."""
    database.configure(tmp_path / "test.db")
    await database.init_db()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_watcher(concurrency: int = 1, analysis_mode: str = "full_auto") -> tuple[RSSWatcher, MagicMock]:
    deps = MagicMock()
    deps.user_id = 1
    settings = MagicMock()
    settings.analysis_mode = analysis_mode
    bot = MagicMock()
    bot.send_message = AsyncMock()
    watcher = RSSWatcher(deps=deps, telegram_bot=bot, poll_interval=999, concurrency=concurrency, settings=settings)
    return watcher, bot


def _make_vacancy_row(analysis_json: str | None = None) -> MagicMock:
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "id": 42, "url": "https://djinni.co/jobs/42", "title": "PM at Stripe",
        "analysis_json": analysis_json,
    }[k]
    row.__contains__ = lambda self, k: k in ("id", "url", "title", "analysis_json")
    row.keys = lambda: ["id", "url", "title", "analysis_json"]
    return row


# ── Notification fires first ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notification_sent_before_fetch():
    """Telegram notify fires before fetch_jd starts."""
    watcher, bot = _make_watcher()
    call_order = []

    async def fake_fetch(deps, url):
        call_order.append("fetch")
        return 42

    async def fake_analyze(ctx, vid):
        call_order.append("analyze")

    with patch("tools.cv_fetch_jd.fetch_jd", new=fake_fetch), \
         patch("tools.cv_analyze.cv_analyze", new=fake_analyze), \
         patch("core.rss_watcher.finish_analysis", new=AsyncMock()):
        await watcher._process("https://djinni.co/jobs/1", rss_title="PM at Stripe")

    bot.send_message.assert_awaited_once()
    assert call_order[0] == "fetch"  # notify is before fetch but both before analyze


@pytest.mark.asyncio
async def test_fetch_then_analyze_chained():
    """fetch_jd result (vacancy_id) is passed to cv_analyze."""
    watcher, _ = _make_watcher()
    analyzed_ids = []

    async def fake_fetch(deps, url):
        return 99

    async def fake_analyze(ctx, vid):
        analyzed_ids.append(vid)

    with patch("tools.cv_fetch_jd.fetch_jd", new=fake_fetch), \
         patch("tools.cv_analyze.cv_analyze", new=fake_analyze), \
         patch("core.rss_watcher.finish_analysis", new=AsyncMock()):
        await watcher._process("https://djinni.co/jobs/99")

    assert analyzed_ids == [99]


@pytest.mark.asyncio
async def test_finish_analysis_called_once_after_analyze_with_origin_auto():
    """The automatic analysis hands its result to the shared helper (state + event + push through the router)."""
    watcher, _ = _make_watcher()
    calls = []

    async def fake_fetch(deps, url):
        return 42

    async def fake_analyze(ctx, vid):
        return "analysis result"

    async def fake_finish(user_id, vid, result, origin):
        calls.append((user_id, vid, result, origin))

    with patch("tools.cv_fetch_jd.fetch_jd", new=fake_fetch),          patch("tools.cv_analyze.cv_analyze", new=fake_analyze),          patch("core.rss_watcher.finish_analysis", new=fake_finish):
        await watcher._process("https://djinni.co/jobs/42")

    assert calls == [(1, 42, "analysis result", "auto")]


# ── Error handling ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_failure_stops_chain():
    """If fetch_jd fails, cv_analyze is NOT called."""
    watcher, _ = _make_watcher()
    analyze_called = []

    async def fake_fetch(deps, url):
        raise RuntimeError("parser down")

    async def fake_analyze(ctx, vid):
        analyze_called.append(vid)

    with patch("tools.cv_fetch_jd.fetch_jd", new=fake_fetch), \
         patch("tools.cv_analyze.cv_analyze", new=fake_analyze), \
         patch("core.rss_watcher.finish_analysis", new=AsyncMock()):
        await watcher._process("https://djinni.co/jobs/1")

    assert analyze_called == []


@pytest.mark.asyncio
async def test_analyze_failure_is_recorded_and_not_finished():
    """If cv_analyze raises, the failure is recorded (state + event, origin auto) and the finish step is NOT run."""
    watcher, _ = _make_watcher()
    finished, recorded = [], []

    async def fake_fetch(deps, url):
        return 42

    async def fake_analyze(ctx, vid):
        raise RuntimeError("LLM timeout")

    async def fake_record(user_id, vid, origin, reason, code):
        recorded.append((user_id, vid, origin, reason, code))

    with patch("tools.cv_fetch_jd.fetch_jd", new=fake_fetch),          patch("tools.cv_analyze.cv_analyze", new=fake_analyze),          patch("core.rss_watcher.finish_analysis", new=AsyncMock(side_effect=lambda *a: finished.append(a))),          patch("core.rss_watcher.record_analysis_failure", new=fake_record):
        await watcher._process("https://djinni.co/jobs/42")

    assert finished == []
    assert recorded == [(1, 42, "auto", "LLM timeout", "analysis_failed")]
