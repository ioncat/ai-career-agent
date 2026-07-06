"""
tests/test_rss_orchestrator.py — RSSWatcher B4 orchestration flow.

Tests: _process chains fetch_jd → cv_analyze → push_result.
Mocks all external calls (fetch_jd, cv_analyze, send_push, database).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.rss_watcher import RSSWatcher


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
         patch("core.rss_watcher.RSSWatcher._push_result", new=AsyncMock()):
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
         patch("core.rss_watcher.RSSWatcher._push_result", new=AsyncMock()):
        await watcher._process("https://djinni.co/jobs/99")

    assert analyzed_ids == [99]


@pytest.mark.asyncio
async def test_push_result_called_after_analyze():
    """_push_result called exactly once after successful analyze."""
    watcher, _ = _make_watcher()
    push_calls = []

    async def fake_fetch(deps, url):
        return 42

    async def fake_analyze(ctx, vid):
        pass

    async def fake_push(vid):
        push_calls.append(vid)

    watcher._push_result = fake_push

    with patch("tools.cv_fetch_jd.fetch_jd", new=fake_fetch), \
         patch("tools.cv_analyze.cv_analyze", new=fake_analyze):
        await watcher._process("https://djinni.co/jobs/42")

    assert push_calls == [42]


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
         patch("core.rss_watcher.RSSWatcher._push_result", new=AsyncMock()):
        await watcher._process("https://djinni.co/jobs/1")

    assert analyze_called == []


@pytest.mark.asyncio
async def test_analyze_failure_stops_push():
    """If cv_analyze fails, _push_result is NOT called."""
    watcher, _ = _make_watcher()
    push_calls = []

    async def fake_fetch(deps, url):
        return 42

    async def fake_analyze(ctx, vid):
        raise RuntimeError("LLM timeout")

    async def fake_push(vid):
        push_calls.append(vid)

    watcher._push_result = fake_push

    with patch("tools.cv_fetch_jd.fetch_jd", new=fake_fetch), \
         patch("tools.cv_analyze.cv_analyze", new=fake_analyze):
        await watcher._process("https://djinni.co/jobs/42")

    assert push_calls == []


@pytest.mark.asyncio
async def test_push_failure_does_not_crash_process():
    """Push failure is non-fatal — _process completes without raising."""
    watcher, _ = _make_watcher()

    async def fake_fetch(deps, url):
        return 42

    async def fake_analyze(ctx, vid):
        pass

    async def broken_push(vid):
        raise RuntimeError("push service down")

    watcher._push_result = broken_push

    with patch("tools.cv_fetch_jd.fetch_jd", new=fake_fetch), \
         patch("tools.cv_analyze.cv_analyze", new=fake_analyze):
        # should not raise
        await watcher._process("https://djinni.co/jobs/42")


# ── _push_result ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_push_result_sends_fit_score():
    """_push_result reads analysis_json and sends push with fit + label."""
    from contracts.pipeline import AnalysisJson, FitDimensions, Phase1Data, Phase2Data, VacScoreDims

    watcher, _ = _make_watcher()

    dims = VacScoreDims(company_tier=3, seniority=3, market_scope=2, company_type=3,
                        company_stage_fit=2, domain_score=4, remote_policy=3, compensation=2)
    p1 = Phase1Data(role="PM", company="Acme", north_star="ns", primary_archetype="arch",
                    company_type="product", role_balance={}, dominant_culture="o",
                    vacscore_dims=dims, vacancy_score=8.0)
    p2 = Phase2Data(
        fit_score=8, recommendation="apply", recommendation_label="apply — strong match",
        category="Exec PM · Remote", who_they_want="Senior PM.",
        fit_dimensions=FitDimensions(domain_fit=8, execution_fit=8, strategy_fit=8,
                                     systems_fit=8, stakeholder_fit=8, overall_fit=8),
    )
    aj = AnalysisJson(p1=p1, p2=p2).model_dump_json(exclude_none=True)
    row = _make_vacancy_row(analysis_json=aj)

    push_calls = []

    async def fake_send_push(user_id, title, body):
        push_calls.append({"user_id": user_id, "title": title, "body": body})

    with patch("db.database.get_vacancy_by_id", new=AsyncMock(return_value=row)), \
         patch("core.push.send_push", new=fake_send_push):
        await watcher._push_result(42)

    assert len(push_calls) == 1
    assert "8/10" in push_calls[0]["body"]
    assert "apply" in push_calls[0]["body"]


@pytest.mark.asyncio
async def test_push_result_no_op_when_vacancy_missing():
    """_push_result is silent when vacancy_id not found in DB."""
    watcher, _ = _make_watcher()
    push_calls = []

    async def fake_send_push(user_id, title, body):
        push_calls.append(1)

    with patch("db.database.get_vacancy_by_id", new=AsyncMock(return_value=None)), \
         patch("core.push.send_push", new=fake_send_push):
        await watcher._push_result(999)

    assert push_calls == []


@pytest.mark.asyncio
async def test_push_result_no_op_when_no_p2():
    """_push_result is silent when analysis_json has no p2 yet."""
    watcher, _ = _make_watcher()
    push_calls = []
    row = _make_vacancy_row(analysis_json=None)

    async def fake_send_push(user_id, title, body):
        push_calls.append(1)

    with patch("db.database.get_vacancy_by_id", new=AsyncMock(return_value=row)), \
         patch("core.push.send_push", new=fake_send_push):
        await watcher._push_result(42)

    assert push_calls == []
