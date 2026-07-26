"""
tests/test_pipeline_runner.py — tests for core/pipeline_runner.py.

Verifies: FSM pre-step called, tool called, notifier called, rollback on failure.
All external calls (DB, FSM, tools, notifier) are mocked.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.pipeline_fsm import FSMError, VacancyState
from core.notifier import PipelineEvent


# ── Shared mocks ──────────────────────────────────────────────────────────────

def _make_deps(user_id: int = 1):
    deps = MagicMock()
    deps.user_id = user_id
    return deps


def _patch_fsm():
    return patch("core.pipeline_runner.fsm_transition", new_callable=AsyncMock)


def _patch_notify():
    return patch("core.pipeline_runner.notify", new_callable=AsyncMock)


def _patch_db_status():
    return patch("core.pipeline_runner.database.update_vacancy_status", new_callable=AsyncMock)


def _patch_db_error():
    return patch("core.pipeline_runner.database.set_analysis_error", new_callable=AsyncMock)


def _patch_title(title="Acme — PM"):
    return patch("core.pipeline_runner._vacancy_title", new_callable=AsyncMock, return_value=title)


def _patch_editorial_audit(result="⚠️ vacancy not found"):
    """Default: simulate the gate skipping (most vacancies don't qualify) —
    keeps existing happy-path tests' `notify` call-count assertions valid."""
    return patch("tools.cv_editorial_audit.cv_editorial_audit",
                 new_callable=AsyncMock, return_value=result)


# ── run_analyze — happy path ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_analyze_happy_path():
    from core.pipeline_runner import run_analyze

    deps = _make_deps()
    mock_analyze = AsyncMock()

    with _patch_fsm() as mock_fsm, _patch_notify() as mock_notify, _patch_title("Acme — PM"):
        with patch("tools.cv_analyze.cv_analyze", mock_analyze):
            await run_analyze(deps, 42)

    mock_fsm.assert_awaited_once_with(42, VacancyState.ANALYZING)
    mock_notify.assert_awaited_once()
    event_arg = mock_notify.call_args[0][1]
    assert event_arg == PipelineEvent.ANALYSIS_DONE


@pytest.mark.asyncio
async def test_run_analyze_calls_tool_with_vacancy_id():
    from core.pipeline_runner import run_analyze

    deps = _make_deps()
    mock_analyze = AsyncMock()

    with _patch_fsm(), _patch_notify(), _patch_title():
        with patch("tools.cv_analyze.cv_analyze", mock_analyze):
            await run_analyze(deps, 99)

    mock_analyze.assert_awaited_once()
    call_args = mock_analyze.call_args[0]
    assert 99 in call_args  # vacancy_id passed positionally


# ── run_analyze — failure path ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_analyze_failure_sets_error_and_notifies():
    from core.pipeline_runner import run_analyze

    deps = _make_deps()
    boom = RuntimeError("LLM timeout")

    with _patch_fsm(), \
         _patch_notify() as mock_notify, \
         _patch_db_error() as mock_set_err, \
         _patch_title():
        with patch("tools.cv_analyze.cv_analyze", AsyncMock(side_effect=boom)):
            with pytest.raises(RuntimeError):
                await run_analyze(deps, 5)

    mock_set_err.assert_awaited_once_with(5, "LLM timeout")
    mock_notify.assert_awaited_once()
    assert mock_notify.call_args[0][1] == PipelineEvent.ANALYSIS_FAILED


@pytest.mark.asyncio
async def test_run_analyze_fsm_error_propagates_without_notify():
    """FSMError (wrong pre-state) stops execution before tool or notify."""
    from core.pipeline_runner import run_analyze

    deps = _make_deps()

    with patch("core.pipeline_runner.fsm_transition",
               new_callable=AsyncMock, side_effect=FSMError("bad state")):
        with _patch_notify() as mock_notify:
            with pytest.raises(FSMError):
                await run_analyze(deps, 1)

    mock_notify.assert_not_called()


# ── run_generate_cv — happy path ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_generate_cv_happy_path():
    from core.pipeline_runner import run_generate_cv

    deps = _make_deps()
    mock_gen = AsyncMock()

    with _patch_fsm() as mock_fsm, _patch_notify() as mock_notify, _patch_title("Stripe — PM"), \
         _patch_editorial_audit():
        with patch("tools.cv_generate.cv_generate", mock_gen):
            await run_generate_cv(deps, 7, language="en")

    mock_fsm.assert_awaited_once_with(7, VacancyState.CV_GENERATING)
    mock_notify.assert_awaited_once()
    assert mock_notify.call_args[0][1] == PipelineEvent.CV_DONE


# ── run_generate_cv — failure path ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_generate_cv_failure_rolls_back_and_notifies():
    from core.pipeline_runner import run_generate_cv

    deps = _make_deps()

    with _patch_fsm(), \
         _patch_notify() as mock_notify, \
         _patch_db_status() as mock_status, \
         _patch_title():
        with patch("tools.cv_generate.cv_generate",
                   AsyncMock(side_effect=RuntimeError("pdf service down"))):
            with pytest.raises(RuntimeError):
                await run_generate_cv(deps, 8)

    mock_status.assert_awaited_once_with(8, VacancyState.ANALYZED)
    assert mock_notify.call_args[0][1] == PipelineEvent.CV_FAILED


# ── run_generate_cover — happy path ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_generate_cover_happy_path():
    from core.pipeline_runner import run_generate_cover

    deps = _make_deps()
    mock_cover = AsyncMock()

    with _patch_fsm() as mock_fsm, _patch_notify() as mock_notify, _patch_title("Acme — PM"), \
         _patch_editorial_audit():
        with patch("tools.cv_cover.cv_cover", mock_cover):
            await run_generate_cover(deps, 15)

    mock_fsm.assert_awaited_once_with(15, VacancyState.COVER_GENERATING)
    assert mock_notify.call_args[0][1] == PipelineEvent.COVER_DONE


# ── run_generate_cover — failure path ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_generate_cover_failure_rolls_back_to_cv_generated():
    from core.pipeline_runner import run_generate_cover

    deps = _make_deps()

    with _patch_fsm(), \
         _patch_notify() as mock_notify, \
         _patch_db_status() as mock_status, \
         _patch_title():
        with patch("tools.cv_cover.cv_cover",
                   AsyncMock(side_effect=RuntimeError("cover parse error"))):
            with pytest.raises(RuntimeError):
                await run_generate_cover(deps, 20)

    mock_status.assert_awaited_once_with(20, VacancyState.CV_GENERATED)
    assert mock_notify.call_args[0][1] == PipelineEvent.COVER_FAILED


# ── Notification includes user_id and vacancy_id ──────────────────────────────

@pytest.mark.asyncio
async def test_run_analyze_notify_receives_correct_user_and_vacancy():
    from core.pipeline_runner import run_analyze

    deps = _make_deps(user_id=3)

    with _patch_fsm(), _patch_notify() as mock_notify, _patch_title():
        with patch("tools.cv_analyze.cv_analyze", AsyncMock()):
            await run_analyze(deps, 77)

    args = mock_notify.call_args[0]
    assert args[0] == 3     # user_id
    assert args[2] == 77    # vacancy_id


# ── Phase 3.7 Editorial Audit — auto-triggered after CV/Cover, opt-in via gate ──

@pytest.mark.asyncio
async def test_run_generate_cv_triggers_editorial_audit_with_cv_target():
    """The whole point of Phase 3.7 being 'opt-in' is the gate INSIDE
    cv_editorial_audit — not a human deciding whether to call it. run_generate_cv
    must call it automatically, every time, for every vacancy."""
    from core.pipeline_runner import run_generate_cv

    deps = _make_deps()

    with _patch_fsm(), _patch_notify(), _patch_title():
        with patch("tools.cv_generate.cv_generate", AsyncMock()):
            with _patch_editorial_audit() as mock_audit:
                await run_generate_cv(deps, 7)

    mock_audit.assert_awaited_once()
    call_args = mock_audit.call_args
    assert call_args.kwargs.get("target") == "cv" or "cv" in call_args.args


@pytest.mark.asyncio
async def test_run_generate_cover_triggers_editorial_audit_with_cover_target():
    from core.pipeline_runner import run_generate_cover

    deps = _make_deps()

    with _patch_fsm(), _patch_notify(), _patch_title():
        with patch("tools.cv_cover.cv_cover", AsyncMock()):
            with _patch_editorial_audit() as mock_audit:
                await run_generate_cover(deps, 15)

    mock_audit.assert_awaited_once()
    call_args = mock_audit.call_args
    assert call_args.kwargs.get("target") == "cover" or "cover" in call_args.args


@pytest.mark.asyncio
async def test_editorial_audit_gate_skip_does_not_send_extra_notification():
    """Most vacancies don't qualify (gate fails inside cv_editorial_audit) —
    that must stay silent, not spam a notification for every vacancy."""
    from core.pipeline_runner import run_generate_cv

    deps = _make_deps()

    with _patch_fsm(), _patch_notify() as mock_notify, _patch_title():
        with patch("tools.cv_generate.cv_generate", AsyncMock()):
            with _patch_editorial_audit(result="⚠️ вакансия не найдена"):
                await run_generate_cv(deps, 7)

    # Only CV_DONE — no EDITORIAL_AUDIT_DONE/FAILED for a skipped audit.
    mock_notify.assert_awaited_once()
    assert mock_notify.call_args[0][1] == PipelineEvent.CV_DONE


@pytest.mark.asyncio
async def test_editorial_audit_ran_sends_done_notification():
    """When the gate passes and a real report comes back, a separate
    EDITORIAL_AUDIT_DONE notification fires — the CV_DONE notify already fired
    with its own title, this is additive, not a replacement."""
    from core.pipeline_runner import run_generate_cv

    deps = _make_deps()
    fake_vacancy = MagicMock()
    fake_vacancy.__getitem__ = lambda self, k: '{"p3_7_cv": {"naturalness": 7}}' if k == "analysis_json" else None
    fake_vacancy.keys = lambda: ["analysis_json"]

    with _patch_fsm(), _patch_notify() as mock_notify, _patch_title():
        with patch("tools.cv_generate.cv_generate", AsyncMock()):
            with _patch_editorial_audit(result="# Executive Summary\n\nNaturalness: 7/10"):
                with patch("core.pipeline_runner.database.get_vacancy_by_id",
                           new_callable=AsyncMock, return_value=fake_vacancy):
                    await run_generate_cv(deps, 7)

    assert mock_notify.await_count == 2
    events = [c[0][1] for c in mock_notify.call_args_list]
    assert PipelineEvent.CV_DONE in events
    assert PipelineEvent.EDITORIAL_AUDIT_DONE in events


@pytest.mark.asyncio
async def test_editorial_audit_failure_does_not_fail_cv_generation():
    """A real error inside the audit (LLM error, etc.) must not roll back or
    fail the CV generation that already succeeded — it's supplementary."""
    from core.pipeline_runner import run_generate_cv

    deps = _make_deps()

    with _patch_fsm(), _patch_notify() as mock_notify, _patch_title(), \
         _patch_db_status() as mock_status:
        with patch("tools.cv_generate.cv_generate", AsyncMock()):
            with patch("tools.cv_editorial_audit.cv_editorial_audit",
                       new_callable=AsyncMock, side_effect=RuntimeError("LLM down")):
                await run_generate_cv(deps, 7)  # must NOT raise

    # CV status was never rolled back — only the (non-existent) audit failed.
    mock_status.assert_not_called()
    events = [c[0][1] for c in mock_notify.call_args_list]
    assert PipelineEvent.CV_DONE in events
    assert PipelineEvent.EDITORIAL_AUDIT_FAILED in events
