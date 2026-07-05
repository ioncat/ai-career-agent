"""
tests/test_rss_watcher.py — tests for core/rss_watcher.py.

New behaviour (EPIC-16): RSSWatcher polls DB for status='queued' vacancies
instead of polling seen_jobs.json file.

Notification design: Telegram message is sent FIRST (before cv_fetch_jd),
so users get notified immediately regardless of parser availability.

Mocks: database.list_vacancies, database.update_vacancy_status,
       cv_fetch_jd, telegram_bot.send_message.
No real network, Telegram, or DB needed.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.rss_watcher import RSSWatcher, _extract_salary


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_watcher(poll_interval: int = 1) -> tuple[RSSWatcher, MagicMock]:
    deps = MagicMock()
    deps.user_id = 1
    deps.settings.analysis_mode = "inbox_first"  # default
    bot = MagicMock()
    bot.send_message = AsyncMock()
    watcher = RSSWatcher(deps=deps, telegram_bot=bot, poll_interval=poll_interval)
    return watcher, bot


def _make_row(
    vacancy_id: int,
    url: str,
    status: str = "queued",
    title: str = "",
) -> MagicMock:
    row = MagicMock()
    row.__getitem__ = lambda self, key: {
        "id": vacancy_id, "url": url, "status": status, "title": title,
    }[key]
    return row


def _mock_db(queued_rows: list) -> MagicMock:
    db = MagicMock()
    db.list_vacancies = AsyncMock(return_value=queued_rows)
    db.update_vacancy_status = AsyncMock()
    return db


# ── _extract_salary ────────────────────────────────────────────────────────────

def test_extract_salary_djinni_range():
    assert _extract_salary("Product Manager в Company, $2000–3200, відда...") == "$2000–3200"

def test_extract_salary_dou_single():
    assert _extract_salary("Business Analyst, до $1700, Київ") == "$1700"

def test_extract_salary_no_salary():
    assert _extract_salary("Product Manager в Company") == ""

def test_extract_salary_with_spaces():
    assert _extract_salary("PM, $2 000–3 500, remote") == "$2000–3500"


# ── start / stop ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_watcher_start_stop_clean():
    watcher, _ = _make_watcher()
    mock_db = _mock_db([])

    with patch("core.rss_watcher.database", mock_db):
        await watcher.start()
        await watcher.stop()

    assert watcher._task is not None
    assert watcher._task.done()


@pytest.mark.asyncio
async def test_watcher_start_logs_interval():
    """start() should create a background task without raising."""
    watcher, _ = _make_watcher(poll_interval=5)
    mock_db = _mock_db([])

    with patch("core.rss_watcher.database", mock_db):
        await watcher.start()
        await watcher.stop()


# ── _poll_once — DB queued vacancies ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_poll_once_triggers_fetch_for_queued_vacancy():
    watcher, bot = _make_watcher()
    row = _make_row(42, "https://djinni.co/jobs/42/", title="Product Manager в Acme")
    mock_db = _mock_db([row])

    with patch("core.rss_watcher.database", mock_db), \
         patch("tools.cv_fetch_jd.fetch_jd", AsyncMock(return_value=42)), \
         patch("tools.cv_analyze.cv_analyze", AsyncMock()), \
         patch("core.rss_watcher.RSSWatcher._push_result", AsyncMock()):
        await watcher._poll_once()

    # 'fetching' claimed before processing; 'fetched' set after JD saved
    assert mock_db.update_vacancy_status.await_count == 2
    mock_db.update_vacancy_status.assert_any_await(42, "fetching")
    mock_db.update_vacancy_status.assert_any_await(42, "fetched")
    # telegram notified (notification sent first, before fetch)
    bot.send_message.assert_awaited_once()
    msg = bot.send_message.call_args[0][0]
    assert "Новая вакансия" in msg
    assert "djinni.co" in msg.lower()


@pytest.mark.asyncio
async def test_poll_once_skips_when_no_queued():
    watcher, bot = _make_watcher()
    mock_db = _mock_db([])

    with patch("core.rss_watcher.database", mock_db):
        await watcher._poll_once()

    bot.send_message.assert_not_awaited()
    mock_db.update_vacancy_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_poll_once_processes_multiple_vacancies():
    watcher, bot = _make_watcher()
    rows = [
        _make_row(1, "https://djinni.co/jobs/1/", title="PM at Company A"),
        _make_row(2, "https://dou.ua/jobs/2/", title="PO at Company B, $2000"),
    ]
    mock_db = _mock_db(rows)
    mock_fetch = AsyncMock(return_value="✅ Done")

    with patch("core.rss_watcher.database", mock_db):
        with patch("tools.cv_fetch_jd.cv_fetch_jd", mock_fetch):
            await watcher._poll_once()

    assert mock_db.update_vacancy_status.await_count == 2
    assert bot.send_message.await_count == 2


@pytest.mark.asyncio
async def test_poll_once_queries_for_user_id():
    """list_vacancies called with status='queued' and correct user_id."""
    watcher, _ = _make_watcher()
    mock_db = _mock_db([])

    with patch("core.rss_watcher.database", mock_db):
        await watcher._poll_once()

    mock_db.list_vacancies.assert_awaited_once_with(status="queued", user_id=1)


# ── _process — notification sent first, then parse ───────────────────────────

@pytest.mark.asyncio
async def test_process_sends_notification_before_fetch():
    """Telegram notification must fire before cv_fetch_jd is called."""
    watcher, bot = _make_watcher()
    url = "https://djinni.co/jobs/1/"
    call_order: list[str] = []

    async def track_notify(msg: str) -> None:
        call_order.append("notify")

    async def track_fetch(deps, url: str) -> int:
        call_order.append("fetch")
        return 1

    mock_db = _mock_db([])
    bot.send_message.side_effect = track_notify
    with patch("core.rss_watcher.database", mock_db), \
         patch("tools.cv_fetch_jd.fetch_jd", track_fetch), \
         patch("tools.cv_analyze.cv_analyze", AsyncMock()), \
         patch("core.rss_watcher.RSSWatcher._push_result", AsyncMock()):
        await watcher._process(url)

    assert call_order == ["notify", "fetch"], "Notification must precede fetch"


@pytest.mark.asyncio
async def test_process_sends_result_to_telegram():
    """Notification includes source label and URL."""
    watcher, bot = _make_watcher()
    url = "https://djinni.co/jobs/1/"
    mock_fetch = AsyncMock(return_value="✅ Backend Dev сохранена!")

    with patch("tools.cv_fetch_jd.cv_fetch_jd", mock_fetch):
        await watcher._process(url)

    bot.send_message.assert_awaited_once()
    msg = bot.send_message.call_args[0][0]
    assert "Новая вакансия" in msg
    assert "Djinni" in msg


@pytest.mark.asyncio
async def test_process_fetch_error_still_notifies():
    """Notification is sent even when cv_fetch_jd raises. No error message to user."""
    watcher, bot = _make_watcher()
    url = "https://djinni.co/jobs/bad/"
    mock_fetch = AsyncMock(side_effect=Exception("Parser connection refused"))

    with patch("tools.cv_fetch_jd.cv_fetch_jd", mock_fetch):
        await watcher._process(url)

    # Notification was still sent
    bot.send_message.assert_awaited_once()
    msg = bot.send_message.call_args[0][0]
    assert "Новая вакансия" in msg
    # No error surfaced to user
    assert "⚠️" not in msg
    assert "ошибка" not in msg.lower()


@pytest.mark.asyncio
async def test_process_extracts_salary_from_rss_title():
    """Salary is extracted and shown in notification when present in rss_title."""
    watcher, bot = _make_watcher()
    url = "https://dou.ua/jobs/1/"
    rss_title = "Product Manager в Company, $2000–3000, відда..."

    with patch("tools.cv_fetch_jd.cv_fetch_jd", AsyncMock()):
        await watcher._process(url, rss_title=rss_title)

    msg = bot.send_message.call_args[0][0]
    assert "💰" in msg
    assert "$2000" in msg
    assert "📌" in msg


@pytest.mark.asyncio
async def test_process_no_salary_when_absent():
    """No salary line in notification when rss_title has no salary."""
    watcher, bot = _make_watcher()
    url = "https://djinni.co/jobs/1/"
    rss_title = "Product Manager at Big Corp"

    with patch("tools.cv_fetch_jd.cv_fetch_jd", AsyncMock()):
        await watcher._process(url, rss_title=rss_title)

    msg = bot.send_message.call_args[0][0]
    assert "💰" not in msg
    assert "📌" in msg


@pytest.mark.asyncio
async def test_process_source_label_dou():
    watcher, bot = _make_watcher()
    with patch("tools.cv_fetch_jd.cv_fetch_jd", AsyncMock()):
        await watcher._process("https://dou.ua/jobs/123/")
    msg = bot.send_message.call_args[0][0]
    assert "DOU.ua" in msg


@pytest.mark.asyncio
async def test_process_source_label_djinni():
    watcher, bot = _make_watcher()
    with patch("tools.cv_fetch_jd.cv_fetch_jd", AsyncMock()):
        await watcher._process("https://djinni.co/jobs/123/")
    msg = bot.send_message.call_args[0][0]
    assert "Djinni" in msg


# ── analysis_mode ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_process_inbox_first_skips_analysis():
    """ANALYSIS_MODE=inbox_first (default): analysis not triggered after fetch."""
    watcher, _ = _make_watcher()  # analysis_mode="inbox_first" set in _make_watcher
    mock_analyze = AsyncMock()
    mock_db = _mock_db([])

    with patch("core.rss_watcher.database", mock_db), \
         patch("tools.cv_fetch_jd.fetch_jd", AsyncMock(return_value=1)), \
         patch("tools.cv_analyze.cv_analyze", mock_analyze):
        await watcher._process("https://djinni.co/jobs/1/")

    mock_analyze.assert_not_awaited()
    mock_db.update_vacancy_status.assert_awaited_with(1, "fetched")


@pytest.mark.asyncio
async def test_process_full_auto_runs_analysis():
    """ANALYSIS_MODE=full_auto: Phase 1+2 runs automatically after fetch."""
    watcher, _ = _make_watcher()
    watcher._deps.settings.analysis_mode = "full_auto"
    mock_analyze = AsyncMock()
    mock_db = _mock_db([])

    with patch("core.rss_watcher.database", mock_db), \
         patch("tools.cv_fetch_jd.fetch_jd", AsyncMock(return_value=1)), \
         patch("tools.cv_analyze.cv_analyze", mock_analyze), \
         patch("core.rss_watcher.RSSWatcher._push_result", AsyncMock()):
        await watcher._process("https://djinni.co/jobs/1/")

    mock_analyze.assert_awaited_once()
    mock_db.update_vacancy_status.assert_awaited_with(1, "fetched")


# ── Semaphore ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_watcher_default_concurrency_is_2():
    watcher, _ = _make_watcher()
    assert watcher._sem._value == 2


@pytest.mark.asyncio
async def test_watcher_custom_concurrency():
    deps = MagicMock()
    deps.user_id = 1
    bot = MagicMock()
    bot.send_message = AsyncMock()
    watcher = RSSWatcher(deps=deps, telegram_bot=bot, poll_interval=1, concurrency=5)
    assert watcher._sem._value == 5


@pytest.mark.asyncio
async def test_notification_not_gated_by_semaphore():
    """Notification fires before semaphore is acquired — user sees vacancy immediately."""
    import asyncio
    deps = MagicMock()
    deps.user_id = 1
    bot = MagicMock()
    call_order: list[str] = []

    async def track_notify(msg: str) -> None:
        call_order.append("notify")

    bot.send_message = AsyncMock(side_effect=track_notify)

    watcher = RSSWatcher(deps=deps, telegram_bot=bot, poll_interval=1, concurrency=1)

    # Acquire semaphore externally so cv_fetch_jd is forced to wait
    await watcher._sem.acquire()

    fetch_started = asyncio.Event()

    async def track_fetch(deps, url: str) -> int:
        fetch_started.set()
        call_order.append("fetch")
        return 1

    async def run_process():
        with patch("tools.cv_fetch_jd.fetch_jd", track_fetch), \
             patch("tools.cv_analyze.cv_analyze", AsyncMock()), \
             patch("core.rss_watcher.RSSWatcher._push_result", AsyncMock()):
            await watcher._process("https://djinni.co/jobs/1/")

    task = asyncio.create_task(run_process())

    # Give process() a tick to run — notification should fire even while sem is held
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert "notify" in call_order, "Notification must fire before semaphore released"
    assert "fetch" not in call_order, "Fetch must not start until semaphore released"

    # Release semaphore — fetch should now proceed
    watcher._sem.release()
    await task

    assert call_order == ["notify", "fetch"]


@pytest.mark.asyncio
async def test_semaphore_limits_concurrent_fetches():
    """With concurrency=1, two concurrent _process calls serialize at cv_fetch_jd."""
    import asyncio
    deps = MagicMock()
    deps.user_id = 1
    bot = MagicMock()
    bot.send_message = AsyncMock()

    watcher = RSSWatcher(deps=deps, telegram_bot=bot, poll_interval=1, concurrency=1)

    concurrent_peak = 0
    active = 0

    async def slow_fetch(deps, url: str) -> int:
        nonlocal active, concurrent_peak
        active += 1
        concurrent_peak = max(concurrent_peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return 1

    with patch("tools.cv_fetch_jd.fetch_jd", slow_fetch), \
         patch("tools.cv_analyze.cv_analyze", AsyncMock()), \
         patch("core.rss_watcher.RSSWatcher._push_result", AsyncMock()):
        await asyncio.gather(
            watcher._process("https://djinni.co/jobs/1/"),
            watcher._process("https://djinni.co/jobs/2/"),
            watcher._process("https://djinni.co/jobs/3/"),
        )

    assert concurrent_peak == 1, f"Expected max 1 concurrent fetch, got {concurrent_peak}"


@pytest.mark.asyncio
async def test_semaphore_concurrency_2_allows_two_parallel():
    """With concurrency=2, up to 2 fetches run at the same time."""
    import asyncio
    deps = MagicMock()
    deps.user_id = 1
    bot = MagicMock()
    bot.send_message = AsyncMock()

    watcher = RSSWatcher(deps=deps, telegram_bot=bot, poll_interval=1, concurrency=2)

    concurrent_peak = 0
    active = 0

    async def slow_fetch(deps, url: str) -> int:
        nonlocal active, concurrent_peak
        active += 1
        concurrent_peak = max(concurrent_peak, active)
        await asyncio.sleep(0.02)
        active -= 1
        return 1

    with patch("tools.cv_fetch_jd.fetch_jd", slow_fetch), \
         patch("tools.cv_analyze.cv_analyze", AsyncMock()), \
         patch("core.rss_watcher.RSSWatcher._push_result", AsyncMock()):
        await asyncio.gather(
            watcher._process("https://djinni.co/jobs/1/"),
            watcher._process("https://djinni.co/jobs/2/"),
            watcher._process("https://djinni.co/jobs/3/"),
        )

    assert concurrent_peak == 2, f"Expected max 2 concurrent fetches, got {concurrent_peak}"


# ── _poll_analyze_queue ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_poll_analyze_queue_runs_analysis():
    """_poll_analyze_queue: analysis_queued vacancy → cv_analyze called → status=analyzed."""
    watcher, _ = _make_watcher()
    row = _make_row(vacancy_id=10, url="https://djinni.co/jobs/10/", status="analysis_queued")
    mock_analyze = AsyncMock()
    mock_db = _mock_db([])
    mock_db.list_vacancies = AsyncMock(return_value=[row])

    with patch("core.rss_watcher.database", mock_db), \
         patch("tools.cv_analyze.cv_analyze", mock_analyze), \
         patch("core.rss_watcher.RSSWatcher._push_result", AsyncMock()):
        await watcher._poll_analyze_queue()

    mock_db.update_vacancy_status.assert_any_await(10, "analyzing")
    mock_analyze.assert_awaited_once()


@pytest.mark.asyncio
async def test_poll_analyze_queue_empty_does_nothing():
    """_poll_analyze_queue: no analysis_queued vacancies → no calls."""
    watcher, _ = _make_watcher()
    mock_analyze = AsyncMock()
    mock_db = _mock_db([])
    mock_db.list_vacancies = AsyncMock(return_value=[])

    with patch("core.rss_watcher.database", mock_db), \
         patch("tools.cv_analyze.cv_analyze", mock_analyze):
        await watcher._poll_analyze_queue()

    mock_analyze.assert_not_awaited()


@pytest.mark.asyncio
async def test_poll_analyze_queue_failure_sets_analysis_failed():
    """_poll_analyze_queue: cv_analyze raises → set_analysis_error called with error message."""
    watcher, _ = _make_watcher()
    row = _make_row(vacancy_id=11, url="https://djinni.co/jobs/11/", status="analysis_queued")
    mock_db = _mock_db([])
    mock_db.list_vacancies = AsyncMock(return_value=[row])
    mock_db.set_analysis_error = AsyncMock()

    with patch("core.rss_watcher.database", mock_db), \
         patch("tools.cv_analyze.cv_analyze", AsyncMock(side_effect=RuntimeError("LLM error"))):
        await watcher._poll_analyze_queue()

    mock_db.set_analysis_error.assert_awaited_once()
    call_args = mock_db.set_analysis_error.await_args
    assert call_args[0][0] == 11
    assert "LLM error" in call_args[0][1]
