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


@pytest.mark.asyncio
async def test_fresh_llm_ollama_uses_db_model():
    """When provider=ollama_api, _fresh_llm builds OllamaProvider with the
    config_store-selected model (single source of truth, not self._settings)."""
    worker = _make_worker()
    worker._settings.ollama_base_url = "http://localhost:11434"
    worker._settings.ollama_timeout = 300
    worker._settings.max_tokens = 4000

    cfg = {"provider": "ollama_api", "model": "qwen3:8b", "thinking_effort": "off"}

    with (
        patch("core.analysis_worker.config_store.get_config", new_callable=AsyncMock, return_value=cfg),
        patch("core.llm_client.OllamaProvider") as MockOllama,
    ):
        await worker._fresh_llm("phase1")

    # DB-selected model (via config_store) wins over the env default
    assert MockOllama.call_args.kwargs["model"] == "qwen3:8b"


@pytest.mark.asyncio
async def test_fresh_llm_ollama_falls_back_to_env_model(monkeypatch):
    """No DB model → OllamaProvider uses OLLAMA_MODEL env, not the Claude llm_model."""
    worker = _make_worker()
    worker._settings.ollama_base_url = "http://localhost:11434"
    worker._settings.ollama_timeout = 300
    worker._settings.max_tokens = 4000
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:32b")

    cfg = {"provider": "ollama_api", "model": None, "thinking_effort": "off"}

    with (
        patch("core.analysis_worker.config_store.get_config", new_callable=AsyncMock, return_value=cfg),
        patch("core.llm_client.OllamaProvider") as MockOllama,
    ):
        await worker._fresh_llm("phase1")

    assert MockOllama.call_args.kwargs["model"] == "qwen2.5:32b"


@pytest.mark.asyncio
async def test_execute_timeout_sets_analysis_error():
    """_execute sets analysis_failed when cv_analyze hangs past _ANALYSIS_TIMEOUT.

    Mocks config_store.get_config directly (not the DB layer underneath it) —
    this file's contract is "no real DB needed"; going through the real
    database.get_user_settings/set_user_settings here would let a missing
    mock silently seed/write the actual production DB (config_store's seed
    path calls set_user_settings when the mocked read returns falsy).
    """
    worker = _make_worker()
    worker._ANALYSIS_TIMEOUT = 0.05  # 50ms for test speed

    async def hanging_analyze(_ctx, _vid):
        await asyncio.sleep(10)  # longer than timeout

    error_calls = []
    cfg = {"provider": "claude_cli", "model": "claude-haiku-4-5-20251001", "thinking_effort": "off"}

    with (
        patch("core.analysis_worker.database.update_vacancy_status", new_callable=AsyncMock),
        patch("core.analysis_worker.config_store.get_config", new_callable=AsyncMock, return_value=cfg),
        patch("core.analysis_worker.database.set_analysis_error", new_callable=AsyncMock) as mock_err,
        patch("tools.cv_analyze.cv_analyze", hanging_analyze),
    ):
        mock_err.side_effect = lambda vid, msg: error_calls.append((vid, msg))
        await worker._execute(99)

    assert len(error_calls) == 1
    vid, msg = error_calls[0]
    assert vid == 99
    assert "timed out" in msg.lower()
