"""
tests/test_analysis_worker.py — tests for core/analysis_worker.py.

Focuses on _recover_loop: DB recovery of analysis_queued vacancies on startup.
Mocks: database.list_vacancies, database.update_vacancy_status.
No real DB, LLM, or network needed.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.analysis_worker import AnalysisWorker


def _make_worker():
    deps = MagicMock()
    deps.user_id = 1
    settings = MagicMock()
    settings.llm_provider = "claude_cli"
    settings.llm_model = "claude-haiku-4-5-20251001"
    settings.claude_cli_timeout = 60
    settings.profile_md_path = MagicMock()
    settings.profile_md_path.exists.return_value = False
    sem = asyncio.Semaphore(1)
    return AnalysisWorker(deps=deps, settings=settings, llm_sem=sem)


@pytest.mark.asyncio
async def test_recover_queued_enqueues_vacancies():
    """_recover_queued picks up analysis_queued vacancies and enqueues them."""
    row1 = MagicMock()
    row1.__getitem__ = MagicMock(side_effect=lambda k: 538 if k == "id" else None)
    row2 = MagicMock()
    row2.__getitem__ = MagicMock(side_effect=lambda k: 539 if k == "id" else None)

    worker = _make_worker()
    enqueued = []

    async def fake_enqueue(vid):
        enqueued.append(vid)

    worker.enqueue = fake_enqueue

    with patch("core.analysis_worker.database.list_vacancies", new_callable=AsyncMock) as mock_lv:
        mock_lv.return_value = [row1, row2]
        await worker._recover_queued()

    assert enqueued == [538, 539]


@pytest.mark.asyncio
async def test_recover_queued_empty_db_no_enqueue():
    """_recover_queued with no queued vacancies does nothing."""
    worker = _make_worker()
    enqueued = []

    async def fake_enqueue(vid):
        enqueued.append(vid)

    worker.enqueue = fake_enqueue

    with patch("core.analysis_worker.database.list_vacancies", new_callable=AsyncMock) as mock_lv:
        mock_lv.return_value = []
        await worker._recover_queued()

    assert enqueued == []


@pytest.mark.asyncio
async def test_recover_queued_db_error_does_not_crash():
    """_recover_queued swallows DB errors without raising."""
    worker = _make_worker()

    with patch("core.analysis_worker.database.list_vacancies", new_callable=AsyncMock) as mock_lv:
        mock_lv.side_effect = RuntimeError("DB unavailable")
        await worker._recover_queued()  # must not raise


@pytest.mark.asyncio
async def test_start_creates_recovery_task():
    """start() creates both main and recovery tasks."""
    worker = _make_worker()

    with (
        patch("core.analysis_worker.database.list_vacancies", new_callable=AsyncMock) as mock_lv,
        patch("core.analysis_worker.database.get_user_settings", new_callable=AsyncMock),
    ):
        mock_lv.return_value = []

        await worker.start()
        assert worker._task is not None
        assert worker._recovery_task is not None
        await worker.stop()
