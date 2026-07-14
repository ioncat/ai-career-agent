"""
tests/test_cv_analyze.py — tests for tools/cv_analyze.py.

Mocks: database module, llm.complete, filesystem (tmp_path).
Prompts files are read from the real prompts/ directory (bundled code, no side effects).
No real Claude API or DB needed.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from core.llm_client import LLMError
from tools.cv_analyze import (
    _build_analysis_file,
    _extract_quick_scan,
    _extract_vacancy_title,
    _parse_phase2_data,
    cv_analyze,
)


# ── Parser robustness across provider formatting variations ───────────────────

def _p2_text(fit: str, rec: str) -> str:
    return (
        f"## Quick Scan\n**Fit score:** {fit}/10\n**Recommendation:** {rec}\n"
        f"**Category:** PM\n**Ideal Candidate Archetype:** X\n"
    )


def test_parse_phase2_decimal_fit_score():
    """Local/small models emit '8.5/10' — parser rounds instead of failing."""
    p2 = _parse_phase2_data(_p2_text("8.5", "Apply"), None)
    assert p2 is not None
    assert p2.fit_score == 8


def test_parse_phase2_capitalised_recommendation():
    """Provider capitalises 'Apply' — must still parse (case-insensitive)."""
    p2 = _parse_phase2_data(_p2_text("7", "Apply — strong match"), None)
    assert p2 is not None
    assert p2.recommendation == "apply"


def test_parse_phase2_integer_still_works():
    p2 = _parse_phase2_data(_p2_text("6", "decline — not worth it"), None)
    assert p2 is not None
    assert p2.fit_score == 6
    assert p2.recommendation == "decline"


# ── Fixtures / helpers ────────────────────────────────────────────────────────

# Minimal Phase 2 output that satisfies all parser requirements
_VALID_PHASE2 = (
    "## Quick Scan\n"
    "**Fit score:** 7/10\n"
    "**Recommendation:** apply\n"
    "**Category:** Strong match\n"
    "**Key Barriers:** none\n"
    "**Hidden Risks:** none\n"
    "**Warnings:** none\n\n"
    "## Internal Analysis\n"
    "| Domain fit | 7 | ok |\n"
    "| Execution fit | 7 | ok |\n"
    "| Strategy fit | 7 | ok |\n"
    "| Systems fit | 7 | ok |\n"
    "| Stakeholder fit | 7 | ok |\n"
    "| Overall fit | 7 | ok |\n"
)


def _make_llm(side_effect=None, return_value="LLM output") -> AsyncMock:
    """Build mock ClaudeProvider.complete."""
    llm = AsyncMock()
    llm.last_call_usage = None  # prevent **unpacking AsyncMock in insert_llm_usage
    if side_effect is not None:
        llm.complete = AsyncMock(side_effect=side_effect)
    else:
        llm.complete = AsyncMock(return_value=return_value)
    return llm


def _make_ctx(tmp_path: Path, llm=None) -> MagicMock:
    """Build mock RunContext[AgentDeps]."""
    ctx = MagicMock()
    ctx.deps.llm = llm or _make_llm()
    ctx.deps.vacancies_path = tmp_path / "vacancies"
    ctx.deps.skill_type = "pm"
    ctx.deps.user_id = 1
    return ctx


def _make_vacancy_row(
    jd_path: Path,
    vacancy_id: int = 1,
    title: str = "Backend Dev",
    url: str = "https://djinni.co/jobs/123-backend/",
) -> MagicMock:
    """Build a mock aiosqlite.Row for a vacancy."""
    data = {
        "id": vacancy_id,
        "title": title,
        "markdown_path": str(jd_path),
        "url": url,
        "status": "fetched",
    }
    row = MagicMock()
    row.__getitem__ = lambda self, key: data[key]
    return row


def _write_jd(tmp_path: Path, content: str = "# Backend Dev\n\nGreat job.") -> Path:
    """Create a JD.md in a realistic vacancy folder and return its path."""
    jd_dir = tmp_path / "vacancies" / "djinni" / "2026-05" / "123-backend"
    jd_dir.mkdir(parents=True)
    jd_path = jd_dir / "JD.md"
    jd_path.write_text(content, encoding="utf-8")
    return jd_path


def _mock_db(
    vacancy_row=None,
    run_ids: list[int] | None = None,
) -> MagicMock:
    """Build a mock database module."""
    run_ids = run_ids or [1, 2]
    mock_db = MagicMock()
    mock_db.get_vacancy_by_id = AsyncMock(return_value=vacancy_row)
    mock_db.insert_pipeline_run = AsyncMock(side_effect=run_ids)
    mock_db.update_pipeline_run = AsyncMock()
    mock_db.update_vacancy_status = AsyncMock()
    mock_db.update_vacancy_fields = AsyncMock()
    mock_db.insert_llm_usage = AsyncMock()
    mock_db.set_analysis_error = AsyncMock()
    mock_db.patch_analysis_json = AsyncMock()
    return mock_db


# ── _extract_quick_scan ───────────────────────────────────────────────────────

def test_extract_quick_scan_finds_block():
    text = (
        "### Summary\n\nSome text.\n\n"
        "## Quick Scan\n\n"
        "**Category:** Execution-heavy\n"
        "**Fit score:** 7/10\n"
        "**Recommendation:** подавать\n\n"
        "## Detailed Assessment\n\nRest."
    )
    result = _extract_quick_scan(text)
    assert "Quick Scan" in result
    assert "7/10" in result
    assert "Detailed Assessment" not in result


def test_extract_quick_scan_at_end_of_string():
    """Quick Scan is the last section — no following ## header."""
    text = "## Phase 2\n\nSome text.\n\n## Quick Scan\n\n**Fit score:** 8/10\n**Recommendation:** подавать"
    result = _extract_quick_scan(text)
    assert "8/10" in result
    assert "подавать" in result


def test_extract_quick_scan_case_insensitive():
    text = "## quick scan\n\n**Fit score:** 6/10"
    result = _extract_quick_scan(text)
    assert "6/10" in result


def test_extract_quick_scan_fallback_when_missing():
    text = "No quick scan block here. Just plain analysis output that goes on and on."
    result = _extract_quick_scan(text)
    assert "No quick scan" in result
    assert len(result) <= 500


# ── _build_analysis_file ──────────────────────────────────────────────────────

def test_build_analysis_file_structure():
    content = _build_analysis_file(
        title="Test Role",
        url="https://djinni.co/jobs/1/",
        phase1="Phase 1 content here",
        phase2="Phase 2 content here",
        quick_scan="## Quick Scan\n\n**Fit score:** 7/10",
    )
    assert "# Analysis: Test Role" in content
    assert "https://djinni.co/jobs/1/" in content
    assert "Phase 1 content here" in content
    assert "Phase 2 content here" in content
    assert "## Quick Scan" in content
    # Quick Scan should appear before the full analysis sections
    qs_pos = content.index("## Quick Scan")
    p1_pos = content.index("Phase 1 content here")
    assert qs_pos < p1_pos


# ── _extract_vacancy_title ───────────────────────────────────────────────────

def test_extract_vacancy_title_happy_path():
    text = "**Role:** Senior PM\n**Company:** Acme Corp\n\nMore text."
    assert _extract_vacancy_title(text) == "Senior PM — Acme Corp"


def test_extract_vacancy_title_case_insensitive():
    text = "**role:** Product Lead\n**company:** Involve.software"
    assert _extract_vacancy_title(text) == "Product Lead — Involve.software"


def test_extract_vacancy_title_missing_company_returns_none():
    text = "**Role:** Senior PM\n\nNo company line here."
    assert _extract_vacancy_title(text) is None


def test_extract_vacancy_title_missing_role_returns_none():
    text = "**Company:** Acme Corp\n\nNo role line here."
    assert _extract_vacancy_title(text) is None


def test_extract_vacancy_title_empty_fields_returns_none():
    text = "**Role:**   \n**Company:**   \n"
    assert _extract_vacancy_title(text) is None


def test_extract_vacancy_title_no_header_returns_none():
    text = "Plain phase 1 output without structured header."
    assert _extract_vacancy_title(text) is None


# ── cv_analyze — title update ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_analyze_updates_db_title_when_phase1_has_header(tmp_path):
    """When Phase 1 output contains **Role:** + **Company:**, DB title is updated."""
    jd_path = _write_jd(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    phase1_with_header = "**Role:** Product Lead\n**Company:** Involve.software\n\nRest of analysis."
    llm = _make_llm(side_effect=[phase1_with_header, _VALID_PHASE2])
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_analyze.database", mock_db):
        result = await cv_analyze(ctx, 1)

    mock_db.update_vacancy_fields.assert_awaited_once_with(1, title="Product Lead — Involve.software")
    assert "Product Lead — Involve.software" in result


@pytest.mark.asyncio
async def test_analyze_skips_title_update_when_no_header(tmp_path):
    """When Phase 1 output has no structured header, title is not updated."""
    jd_path = _write_jd(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(side_effect=["Plain Phase 1 output without header.", _VALID_PHASE2])
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_analyze.database", mock_db):
        await cv_analyze(ctx, 1)

    mock_db.update_vacancy_fields.assert_not_awaited()


# ── cv_analyze — happy path ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_analyze_happy_path(tmp_path):
    jd_path = _write_jd(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(side_effect=["Phase 1 output", _VALID_PHASE2])
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_analyze.database", mock_db):
        result = await cv_analyze(ctx, 1)

    assert "✅" in result
    assert "Backend Dev" in result
    assert "Quick Scan" in result
    assert "7/10" in result


@pytest.mark.asyncio
async def test_analyze_saves_jd_analysis_md(tmp_path):
    jd_path = _write_jd(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(side_effect=["Phase 1 output", "Phase 2 output"])
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_analyze.database", mock_db):
        await cv_analyze(ctx, 1)

    analysis_path = jd_path.parent / "JD_analysis.md"
    assert analysis_path.exists()
    content = analysis_path.read_text(encoding="utf-8")
    assert "Phase 1 output" in content
    assert "Phase 2 output" in content


@pytest.mark.asyncio
async def test_analyze_calls_llm_twice(tmp_path):
    jd_path = _write_jd(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(return_value="output")
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_analyze.database", mock_db):
        await cv_analyze(ctx, 1)

    assert llm.complete.await_count == 2


@pytest.mark.asyncio
async def test_analyze_phase2_receives_phase1_output(tmp_path):
    """Phase 2 user input must contain Phase 1 output text."""
    jd_path = _write_jd(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    phase1_text = "UNIQUE_PHASE1_MARKER_XYZ"
    llm = _make_llm(side_effect=[phase1_text, "phase2 output"])
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_analyze.database", mock_db):
        await cv_analyze(ctx, 1)

    second_call_user = llm.complete.call_args_list[1][0][0]
    assert phase1_text in second_call_user


@pytest.mark.asyncio
async def test_analyze_updates_status_to_analyzed(tmp_path):
    jd_path = _write_jd(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(side_effect=["Phase 1 output", _VALID_PHASE2])
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_analyze.database", mock_db):
        await cv_analyze(ctx, 1)

    mock_db.update_vacancy_status.assert_awaited_once_with(1, "analyzed")


@pytest.mark.asyncio
async def test_analyze_inserts_two_pipeline_runs(tmp_path):
    jd_path = _write_jd(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(return_value="output")
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_analyze.database", mock_db):
        await cv_analyze(ctx, 1)

    assert mock_db.insert_pipeline_run.await_count == 2
    calls = mock_db.insert_pipeline_run.call_args_list
    phases = [c.kwargs["phase"] for c in calls]
    assert "phase1" in phases
    assert "phase2" in phases


# ── cv_analyze — error cases ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_analyze_vacancy_not_found(tmp_path):
    ctx = _make_ctx(tmp_path)
    mock_db = _mock_db(vacancy_row=None)

    with patch("tools.cv_analyze.database", mock_db):
        result = await cv_analyze(ctx, 999)

    assert "⚠️" in result
    assert "999" in result


@pytest.mark.asyncio
async def test_analyze_jd_file_missing(tmp_path):
    jd_path = _write_jd(tmp_path)
    jd_path.unlink()  # delete file after creating row
    vacancy_row = _make_vacancy_row(jd_path)
    ctx = _make_ctx(tmp_path)
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_analyze.database", mock_db):
        result = await cv_analyze(ctx, 1)

    assert "⚠️" in result
    assert "JD.md" in result


@pytest.mark.asyncio
async def test_analyze_phase1_llm_error(tmp_path):
    jd_path = _write_jd(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(side_effect=LLMError("API timeout on phase 1"))
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=vacancy_row, run_ids=[1])

    with patch("tools.cv_analyze.database", mock_db):
        result = await cv_analyze(ctx, 1)

    assert "⚠️" in result
    assert "API timeout on phase 1" in result
    mock_db.update_vacancy_status.assert_not_called()


@pytest.mark.asyncio
async def test_analyze_reanalysis_saves_to_claude_desktop_subfolder(tmp_path):
    """Re-analysis saves to Claude Desktop/ subfolder when JD_analysis.md already exists."""
    jd_path = _write_jd(tmp_path)
    (jd_path.parent / "JD_analysis.md").write_text("old analysis", encoding="utf-8")
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(side_effect=["Phase 1 output", _VALID_PHASE2])
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_analyze.database", mock_db):
        result = await cv_analyze(ctx, 1)

    assert (jd_path.parent / "JD_analysis.md").read_text(encoding="utf-8") == "old analysis"
    new_path = jd_path.parent / "Claude Desktop" / "JD_analysis.md"
    assert new_path.exists()
    assert "Phase 1 output" in new_path.read_text(encoding="utf-8")
    assert "✅" in result


@pytest.mark.asyncio
async def test_analyze_phase2_llm_error(tmp_path):
    jd_path = _write_jd(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(side_effect=["Phase 1 ok", LLMError("Rate limit on phase 2")])
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_analyze.database", mock_db):
        result = await cv_analyze(ctx, 1)

    assert "⚠️" in result
    assert "Rate limit on phase 2" in result
    # JD_analysis.md must NOT be written on phase 2 failure
    assert not (jd_path.parent / "JD_analysis.md").exists()
    mock_db.update_vacancy_status.assert_not_called()
