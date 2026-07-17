"""
tests/test_cv_prefilter.py — tests for tools/cv_prefilter.py (EPIC-27).

Mocks: database module, llm.complete, filesystem (tmp_path). Same pattern as
tests/test_cv_analyze.py. Prompts read from the real prompts/ directory.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.cv_prefilter import _parse_prefilter_output, cv_prefilter


# ── Parser ───────────────────────────────────────────────────────────────────

def test_parse_blocked_yes_with_reasons():
    text = (
        "BLOCKED: yes\n"
        "REASONS:\n"
        "- english: JD requires C1, candidate is B2\n"
        "- location: must reside in EU\n"
    )
    blocked, reasons, format_ok = _parse_prefilter_output(text)
    assert blocked is True
    assert format_ok is True
    assert reasons == ["english: JD requires C1, candidate is B2", "location: must reside in EU"]


def test_parse_blocked_no():
    blocked, reasons, format_ok = _parse_prefilter_output("BLOCKED: no")
    assert blocked is False
    assert format_ok is True
    assert reasons == []


def test_parse_unparseable_output_not_treated_as_blocker_but_flagged_as_bad_format():
    """No BLOCKED: line at all → never treated as a blocker (fail-open for the
    decision), but format_ok=False so the caller can tell this apart from a
    real "BLOCKED: no" answer — the exact distinction missing on vacancy #716
    (2026-07-17), where a rambling model output looked identical to "all clear"."""
    blocked, reasons, format_ok = _parse_prefilter_output("the model rambled about something else entirely")
    assert blocked is False
    assert reasons == []
    assert format_ok is False


def test_parse_caps_reasons_at_five():
    text = "BLOCKED: yes\nREASONS:\n" + "\n".join(f"- reason {i}" for i in range(8))
    _, reasons, format_ok = _parse_prefilter_output(text)
    assert len(reasons) == 5
    assert format_ok is True


# ── cv_prefilter ─────────────────────────────────────────────────────────────

def _make_vacancy_row(jd_path: Path, vacancy_id: int = 1) -> MagicMock:
    data = {"id": vacancy_id, "markdown_path": str(jd_path)}
    row = MagicMock()
    row.__getitem__ = lambda self, key: data[key]
    return row


def _write_jd(tmp_path: Path, content: str = "# Backend Dev\n\nGreat job.") -> Path:
    jd_dir = tmp_path / "vacancies" / "djinni" / "123-backend"
    jd_dir.mkdir(parents=True)
    jd_path = jd_dir / "JD.md"
    jd_path.write_text(content, encoding="utf-8")
    return jd_path


def _make_ctx(llm=None) -> MagicMock:
    ctx = MagicMock()
    ctx.deps.get_llm = AsyncMock(return_value=llm or _make_llm())
    ctx.deps.skill_type = "pm"
    ctx.deps.user_id = 1
    return ctx


def _make_llm(return_value="BLOCKED: no", side_effect=None) -> AsyncMock:
    llm = AsyncMock()
    llm.last_call_usage = None
    if side_effect is not None:
        llm.complete = AsyncMock(side_effect=side_effect)
    else:
        llm.complete = AsyncMock(return_value=return_value)
    return llm


def _mock_db(vacancy_row=None, run_id: int = 1) -> MagicMock:
    mock_db = MagicMock()
    mock_db.get_vacancy_by_id = AsyncMock(return_value=vacancy_row)
    mock_db.insert_pipeline_run = AsyncMock(return_value=run_id)
    mock_db.update_pipeline_run = AsyncMock()
    mock_db.insert_llm_usage = AsyncMock()
    mock_db.set_vacancy_blocker = AsyncMock()
    return mock_db


@pytest.mark.asyncio
async def test_prefilter_flags_blocker(tmp_path):
    jd_path = _write_jd(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm("BLOCKED: yes\nREASONS:\n- english: JD requires C1")
    ctx = _make_ctx(llm)
    mock_db = _mock_db(vacancy_row)

    with patch("tools.cv_prefilter.database", mock_db):
        result = await cv_prefilter(ctx, 1)

    mock_db.set_vacancy_blocker.assert_awaited_once_with(
        1, True, ["english: JD requires C1"], raw_output="BLOCKED: yes\nREASONS:\n- english: JD requires C1"
    )
    mock_db.update_pipeline_run.assert_any_call(1, status="done", error_message=None)
    assert result == {
        "ok": True, "blocked": True, "reasons": ["english: JD requires C1"],
        "raw_output": "BLOCKED: yes\nREASONS:\n- english: JD requires C1",
        "format_ok": True, "error": None, "provider_unavailable": False,
    }


@pytest.mark.asyncio
async def test_prefilter_no_blocker(tmp_path):
    jd_path = _write_jd(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    ctx = _make_ctx(_make_llm("BLOCKED: no"))
    mock_db = _mock_db(vacancy_row)

    with patch("tools.cv_prefilter.database", mock_db):
        result = await cv_prefilter(ctx, 1)

    mock_db.set_vacancy_blocker.assert_awaited_once_with(1, False, [], raw_output="BLOCKED: no")
    assert result["ok"] is True
    assert result["blocked"] is False


@pytest.mark.asyncio
async def test_prefilter_format_mismatch_reported_as_not_ok(tmp_path):
    """Regression guard for the #716 bug: a real LLM call that succeeds but
    doesn't match the expected format must NOT look like a clean 'no blocker'
    answer to callers — ok=False, format_ok=False, raw_output preserved."""
    jd_path = _write_jd(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    rambling = "Well, looking at this JD, the candidate might face some challenges here..."
    ctx = _make_ctx(_make_llm(rambling))
    mock_db = _mock_db(vacancy_row)

    with patch("tools.cv_prefilter.database", mock_db):
        result = await cv_prefilter(ctx, 1)

    assert result["ok"] is False
    assert result["blocked"] is False  # still fail-open for the decision itself
    assert result["raw_output"] == rambling
    assert "format" in result["error"].lower()
    mock_db.set_vacancy_blocker.assert_awaited_once_with(1, False, [], raw_output=rambling)
    mock_db.update_pipeline_run.assert_any_call(
        1, status="error", error_message="Model output didn't match the expected BLOCKED: format"
    )


@pytest.mark.asyncio
async def test_prefilter_fails_open_on_generic_llm_error(tmp_path):
    """A generic (non-LLMUnavailableError) exception → no exception propagates,
    no blocker recorded (DB default stands), result.ok=False, but
    provider_unavailable=False — this is NOT the "service is down" case."""
    jd_path = _write_jd(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(side_effect=RuntimeError("something unexpected"))
    ctx = _make_ctx(llm)
    mock_db = _mock_db(vacancy_row)

    with patch("tools.cv_prefilter.database", mock_db):
        result = await cv_prefilter(ctx, 1)  # must not raise

    mock_db.set_vacancy_blocker.assert_not_awaited()
    mock_db.update_pipeline_run.assert_any_call(1, status="error", error_message="something unexpected")
    assert result == {
        "ok": False, "blocked": False, "reasons": [], "raw_output": None,
        "format_ok": False, "error": "something unexpected", "provider_unavailable": False,
    }


@pytest.mark.asyncio
async def test_prefilter_provider_unavailable_flagged_distinctly(tmp_path):
    """LLMUnavailableError (raised identically by every provider — Ollama down,
    Claude API down/rate-limited, claude CLI missing) must be distinguished from
    generic failures so the UI can say something actionable. Gap found
    2026-07-17: Ollama not running looked like any other opaque error."""
    from core.llm_client import LLMUnavailableError

    jd_path = _write_jd(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(side_effect=LLMUnavailableError("Ollama unreachable at http://localhost:11434: connection refused"))
    ctx = _make_ctx(llm)
    mock_db = _mock_db(vacancy_row)

    with patch("tools.cv_prefilter.database", mock_db):
        result = await cv_prefilter(ctx, 1)  # must not raise

    mock_db.set_vacancy_blocker.assert_not_awaited()
    assert result["ok"] is False
    assert result["provider_unavailable"] is True
    assert "unreachable" in result["error"].lower()


@pytest.mark.asyncio
async def test_prefilter_cancelled_records_error_then_reraises(tmp_path):
    """Regression guard: a stuck 'running' row for 3+ hours (vacancy #716,
    2026-07-17) traced to asyncio.CancelledError — a BaseException, not an
    Exception, so `except Exception` never caught it and the row was never
    marked as failed. Must record the interruption AND re-raise (swallowing
    cancellation silently breaks asyncio task-cancellation semantics)."""
    import asyncio

    jd_path = _write_jd(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(side_effect=asyncio.CancelledError())
    ctx = _make_ctx(llm)
    mock_db = _mock_db(vacancy_row)

    with patch("tools.cv_prefilter.database", mock_db):
        with pytest.raises(asyncio.CancelledError):
            await cv_prefilter(ctx, 1)

    mock_db.set_vacancy_blocker.assert_not_awaited()
    mock_db.update_pipeline_run.assert_any_call(
        1, status="error", error_message="Cancelled — client disconnected or request interrupted"
    )


@pytest.mark.asyncio
async def test_prefilter_vacancy_not_found_returns_early():
    ctx = _make_ctx()
    mock_db = _mock_db(vacancy_row=None)

    result = None
    with patch("tools.cv_prefilter.database", mock_db):
        result = await cv_prefilter(ctx, 999)  # must not raise

    mock_db.set_vacancy_blocker.assert_not_awaited()
    mock_db.insert_pipeline_run.assert_not_awaited()
    assert result["ok"] is False


@pytest.mark.asyncio
async def test_prefilter_jd_missing_on_disk_returns_early(tmp_path):
    vacancy_row = _make_vacancy_row(tmp_path / "does" / "not" / "exist" / "JD.md")
    ctx = _make_ctx()
    mock_db = _mock_db(vacancy_row)

    with patch("tools.cv_prefilter.database", mock_db):
        result = await cv_prefilter(ctx, 1)  # must not raise

    mock_db.set_vacancy_blocker.assert_not_awaited()
    assert result["ok"] is False


@pytest.mark.asyncio
async def test_prefilter_uses_prefilter_phase_for_llm_usage(tmp_path):
    jd_path = _write_jd(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm("BLOCKED: no")
    llm.last_call_usage = {
        "model": "gemma3:2b", "provider": "ollama_api", "thinking_effort": "",
        "profile_tokens": 10, "prompt_tokens": 5, "user_tokens": 20,
        "input_tokens": 35, "output_tokens": 5, "cache_write_tokens": 0,
        "cache_read_tokens": 0, "budget_tokens": 0, "thinking_tokens": 0,
        "elapsed_ms": 100, "cost_usd": 0.0,
    }
    ctx = _make_ctx(llm)
    mock_db = _mock_db(vacancy_row)

    with patch("tools.cv_prefilter.database", mock_db):
        await cv_prefilter(ctx, 1)

    mock_db.insert_llm_usage.assert_awaited_once()
    _, kwargs = mock_db.insert_llm_usage.call_args
    assert kwargs["phase"] == "prefilter"
    assert kwargs["vacancy_id"] == 1
