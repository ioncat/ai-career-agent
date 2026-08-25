"""
tests/test_cv_prefilter.py — tests for tools/cv_prefilter.py (EPIC-27).

Mocks: database module, llm.complete, filesystem (tmp_path). Same pattern as
tests/test_cv_analyze.py. Prompts read from the real prompts/ directory.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.cv_prefilter import (
    _check_country,
    _check_english_level,
    _check_remote_format,
    _check_title_allowlist,
    _check_title_domain_signals,
    _parse_prefilter_output,
    apply_language_stage,
    apply_location_stage,
    apply_title_stage,
    cv_prefilter,
)


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


def test_parse_multiple_blocked_lines_uses_last_but_flags_format_not_ok():
    """Found 2026-07-23, vacancy #725: model wrote 'BLOCKED: yes' with a title
    reason, then self-corrected inline ('Wait — ... IS on allowlist. No title
    conflict.') and ended with 'BLOCKED: no'. The self-corrected (last) answer
    is used as the verdict, but format_ok=False so this leak is still visible
    rather than silently treated as a clean 'no' — same principle as the
    no-BLOCKED-line case above."""
    text = (
        "BLOCKED: yes\n"
        "REASONS:\n"
        "- title: \"Product Manager\"\n"
        "\n"
        "Wait — title check: \"Product Manager\" IS on allowlist. No title conflict.\n"
        "\n"
        "Recheck other blockers:\n"
        "\n"
        "BLOCKED: no\n"
    )
    blocked, reasons, format_ok = _parse_prefilter_output(text)
    assert blocked is False
    assert reasons == []
    assert format_ok is False


def test_parse_multiple_blocked_lines_final_yes_picks_up_its_own_reasons():
    text = (
        "BLOCKED: no\n"
        "\n"
        "Wait — actually there is a conflict.\n"
        "\n"
        "BLOCKED: yes\n"
        "REASONS:\n"
        "- english: \"C1 required\"\n"
    )
    blocked, reasons, format_ok = _parse_prefilter_output(text)
    assert blocked is True
    assert reasons == ['english: "C1 required"']
    assert format_ok is False


# ── Title allowlist (deterministic, 2026-07-23) ────────────────────────────────
# Added after real-data testing showed an LLM asked to judge title as one of
# 10 blocker categories in a single call made execution slips a pure string
# match should never make ("Product Owner Lead" flagged despite containing
# "Product Owner"; "Business Analyst / Project Manager" flagged despite
# containing both terms) — see docs/discovery/prefilter-local-model-selection.md.

def test_title_allowlist_fits_exact_term():
    assert _check_title_allowlist("Product Manager") is None


def test_title_allowlist_fits_with_seniority_prefix():
    assert _check_title_allowlist("Senior Product Owner") is None


def test_title_allowlist_fits_case_insensitive():
    assert _check_title_allowlist("PRODUCT OWNER lead") is None


def test_title_allowlist_regression_814_product_owner_lead():
    """#814 (2026-07-23): LLM flagged this despite the literal term being
    present — title contains "Product Owner", must fit deterministically."""
    assert _check_title_allowlist("Product Owner Lead") is None


def test_title_allowlist_regression_813_business_analyst_project_manager():
    """#813 (2026-07-23): LLM flagged despite containing two allowlist terms."""
    assert _check_title_allowlist("Business Analyst / Project Manager") is None


def test_title_allowlist_flags_mismatch():
    reason = _check_title_allowlist("Product Marketing Lead")
    assert reason is not None
    assert reason.startswith("title:")
    assert "Product Marketing Lead" in reason


def test_title_allowlist_flags_no_known_term():
    """#814 fresh-batch counterpart: title with NO allowlist term must flag,
    even if it superficially sounds product-adjacent."""
    reason = _check_title_allowlist("Product Adoption Analytics Lead")
    assert reason is not None


def test_title_allowlist_empty_title_does_not_flag():
    assert _check_title_allowlist("") is None
    assert _check_title_allowlist(None) is None


def test_title_allowlist_regression_779_growth_prefix_flags():
    """#779 (2026-07-23 audit): "Growth Product Manager" literally contains
    "Product Manager" but Growth is a function-changing prefix (a distinct
    discipline, growth marketing) — must still flag despite the substring."""
    reason = _check_title_allowlist("Growth Product Manager (iGaming)")
    assert reason is not None


def test_title_allowlist_regression_776_domain_suffix_fits():
    """#776 counterpart: a word AFTER the term (domain/platform, in parens)
    must NOT affect the verdict — iGaming here says nothing about function."""
    assert _check_title_allowlist("Product Manager (iGaming)") is None


def test_title_allowlist_prefix_denylist_case_insensitive():
    assert _check_title_allowlist("GROWTH Product Manager") is not None


def test_title_allowlist_prefix_denylist_falls_through_to_other_term():
    """A bad prefix on one matched term doesn't poison the whole title if a
    clean allowlist term also appears elsewhere."""
    assert _check_title_allowlist("Growth Product Manager / Business Analyst") is None


# ── Title domain-signal fast-path (2026-07-23) ─────────────────────────────────
# NOT a new blocker category — same `domain`/`igaming` verdict the LLM would
# reach reading the JD body, caught for free when the title names the domain
# outright (most commonly a parenthetical suffix).

def test_title_domain_signals_igaming_flags():
    reason = _check_title_domain_signals("Product Manager (iGaming)")
    assert reason is not None
    assert reason.startswith("igaming:")


def test_title_domain_signals_mobile_flags():
    reason = _check_title_domain_signals("Product Manager (Mobile Apps)")
    assert reason is not None
    assert reason.startswith("domain:")


def test_title_domain_signals_gambling_betting_flag_as_igaming():
    assert _check_title_domain_signals("Product Manager, Gambling").startswith("igaming:")
    assert _check_title_domain_signals("Product Manager (Betting)").startswith("igaming:")


def test_title_domain_signals_clean_title_returns_none():
    assert _check_title_domain_signals("Product Manager") is None


def test_title_domain_signals_empty_title_does_not_flag():
    assert _check_title_domain_signals("") is None
    assert _check_title_domain_signals(None) is None


# ── _check_english_level (Djinni requirements sidebar, 2026-08-11) ─────────────

_JD_WITH_C1 = (
    "# Product Manager\n\nSome JD body with no language mention at all.\n\n"
    "## Vacancy Requirements\n\nВиключно від 4 років досвіду\n"
    "Англійська C1 – Просунутий\nУкраїнська Носій мови\n"
)

_JD_WITH_B1 = (
    "# Product Manager\n\nSome JD body.\n\n"
    "## Vacancy Requirements\n\nАнглійська B1 – Середній\n"
)

_JD_WITH_ENGLISH_LOCALE = (
    "# Product Manager\n\n## Vacancy Requirements\n\nEnglish C2 – Proficient\n"
)


def test_english_level_flags_requirement_above_candidate():
    reason = _check_english_level(_JD_WITH_C1)
    assert reason is not None
    assert reason.startswith("english:")
    assert "C1" in reason


def test_english_level_no_flag_when_at_or_below_candidate():
    assert _check_english_level(_JD_WITH_B1) is None


def test_english_level_handles_english_locale_render():
    reason = _check_english_level(_JD_WITH_ENGLISH_LOCALE)
    assert reason is not None
    assert "C2" in reason


def test_english_level_no_requirements_section_returns_none():
    assert _check_english_level("# Product Manager\n\nJust a JD body.") is None


def test_english_level_requirements_section_without_language_line_returns_none():
    jd = "# Product Manager\n\n## Vacancy Requirements\n\nТільки віддалено\n"
    assert _check_english_level(jd) is None


def test_english_level_ignores_casual_mention_outside_requirements_section():
    """A JD body mentioning 'English C1' in prose (not Djinni's structured
    field) must never trigger a false blocker — only the requirements
    section counts."""
    jd = "# Product Manager\n\nWe need English C1 speakers on the team ideally.\n"
    assert _check_english_level(jd) is None


# ── apply_title_stage (auto-trigger helper, 2026-07-23) ────────────────────────

@pytest.mark.asyncio
async def test_apply_title_stage_writes_blocker_on_mismatch():
    mock_db = _mock_db()
    with patch("tools.cv_prefilter.database", mock_db):
        result = await apply_title_stage(1, "Product Marketing Lead")

    assert result is True
    mock_db.set_vacancy_blocker.assert_awaited_once()
    args, kwargs = mock_db.set_vacancy_blocker.call_args
    assert args[0] == 1
    assert args[1] is True
    assert args[2][0].startswith("title:")


@pytest.mark.asyncio
async def test_apply_title_stage_no_write_on_fit():
    mock_db = _mock_db()
    with patch("tools.cv_prefilter.database", mock_db):
        result = await apply_title_stage(1, "Product Manager")

    assert result is False
    mock_db.set_vacancy_blocker.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_title_stage_domain_signal_also_writes():
    mock_db = _mock_db()
    with patch("tools.cv_prefilter.database", mock_db):
        result = await apply_title_stage(1, "Product Manager (iGaming)")

    assert result is True
    args, kwargs = mock_db.set_vacancy_blocker.call_args
    assert args[2][0].startswith("igaming:")


# ── apply_language_stage (Djinni requirements sidebar, 2026-08-11) ─────────────

@pytest.mark.asyncio
async def test_apply_language_stage_writes_blocker_on_mismatch():
    mock_db = _mock_db()
    with patch("tools.cv_prefilter.database", mock_db):
        result = await apply_language_stage(1, _JD_WITH_C1)

    assert result is True
    mock_db.set_vacancy_blocker.assert_awaited_once()
    args, kwargs = mock_db.set_vacancy_blocker.call_args
    assert args[0] == 1
    assert args[1] is True
    assert args[2][0].startswith("english:")
    assert kwargs["stage"] == "title"


@pytest.mark.asyncio
async def test_apply_language_stage_no_write_when_within_candidate_level():
    mock_db = _mock_db()
    with patch("tools.cv_prefilter.database", mock_db):
        result = await apply_language_stage(1, _JD_WITH_B1)

    assert result is False
    mock_db.set_vacancy_blocker.assert_not_awaited()


# ── _check_country / _check_remote_format (Djinni requirements sidebar,
#    2026-08-25 — same structured section _check_english_level reads) ─────────

_JD_EU_ONLY = (
    "# Product Manager\n\n## Vacancy Requirements\n\n"
    "  * **Тільки віддалено**\n"
    "  * ** Країни ЄС **\n\n"
    "Країни, де розглядаємо кандидатів\n\n"
    "  * **Англійська B2 – Вище середнього**\n"
)

_JD_UKRAINE_AND_EUROPE = (
    "# Product Manager\n\n## Vacancy Requirements\n\n"
    "  * **Тільки віддалено**\n"
    "  * ** Країни Європи та Україна **\n\n"
    "Країни, де розглядаємо кандидатів\n\n"
    "  * **Англійська B2 – Вище середнього**\n"
)

_JD_WORLDWIDE = (
    "# Product Manager\n\n## Vacancy Requirements\n\n"
    "  * **Тільки віддалено**\n"
    "  * ** Весь світ **\n\n"
    "Країни, де розглядаємо кандидатів\n\n"
)

_JD_HYBRID_FORMAT = (
    "# Product Manager\n\n## Vacancy Requirements\n\n"
    "  * **Офіс, Віддалена робота, Гібридний формат роботи**\n"
    "  * ** Україна **\n\n"
    "Країни, де розглядаємо кандидатів\n\n"
)


def test_check_country_flags_eu_only_for_ukraine_candidate():
    reason = _check_country(_JD_EU_ONLY)
    assert reason is not None
    assert reason.startswith("location:")
    assert "ЄС" in reason


def test_check_country_no_flag_when_ukraine_included():
    assert _check_country(_JD_UKRAINE_AND_EUROPE) is None


def test_check_country_no_flag_worldwide():
    assert _check_country(_JD_WORLDWIDE) is None


def test_check_country_no_requirements_section_returns_none():
    assert _check_country("# Product Manager\n\nJust a JD body.") is None


def test_check_country_ignores_casual_mention_outside_requirements_section():
    jd = "# Product Manager\n\nWe only hire from EU countries ideally.\n"
    assert _check_country(jd) is None


def test_check_remote_format_no_flag_when_remote_only():
    assert _check_remote_format(_JD_EU_ONLY) is None


def test_check_remote_format_flags_hybrid_office_listing():
    reason = _check_remote_format(_JD_HYBRID_FORMAT)
    assert reason is not None
    assert reason.startswith("remote_format:")
    assert "Гібридний" in reason


def test_check_remote_format_no_requirements_section_returns_none():
    assert _check_remote_format("# Product Manager\n\nJust a JD body.") is None


# ── apply_location_stage (2026-08-25) ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_apply_location_stage_writes_blocker_on_country_mismatch():
    mock_db = _mock_db()
    with patch("tools.cv_prefilter.database", mock_db):
        result = await apply_location_stage(1, _JD_EU_ONLY)

    assert result is True
    mock_db.set_vacancy_blocker.assert_awaited_once()
    args, kwargs = mock_db.set_vacancy_blocker.call_args
    assert args[0] == 1
    assert args[1] is True
    assert args[2][0].startswith("location:")
    assert kwargs["stage"] == "title"


@pytest.mark.asyncio
async def test_apply_location_stage_writes_both_reasons_when_both_fail():
    jd = (
        "# Product Manager\n\n## Vacancy Requirements\n\n"
        "  * **Офіс, Віддалена робота, Гібридний формат роботи**\n"
        "  * ** Країни ЄС **\n\n"
        "Країни, де розглядаємо кандидатів\n\n"
    )
    mock_db = _mock_db()
    with patch("tools.cv_prefilter.database", mock_db):
        result = await apply_location_stage(1, jd)

    assert result is True
    args, kwargs = mock_db.set_vacancy_blocker.call_args
    assert len(args[2]) == 2
    assert any(r.startswith("location:") for r in args[2])
    assert any(r.startswith("remote_format:") for r in args[2])


@pytest.mark.asyncio
async def test_apply_location_stage_no_write_when_clean():
    mock_db = _mock_db()
    with patch("tools.cv_prefilter.database", mock_db):
        result = await apply_location_stage(1, _JD_UKRAINE_AND_EUROPE)

    assert result is False
    mock_db.set_vacancy_blocker.assert_not_awaited()


# ── cv_prefilter ─────────────────────────────────────────────────────────────

def _make_vacancy_row(jd_path: Path, vacancy_id: int = 1, title: str = "Product Manager") -> MagicMock:
    data = {"id": vacancy_id, "markdown_path": str(jd_path), "title": title}
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
        1, True, ["english: JD requires C1"], raw_output="BLOCKED: yes\nREASONS:\n- english: JD requires C1",
        stage="content",
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

    mock_db.set_vacancy_blocker.assert_awaited_once_with(1, False, [], raw_output="BLOCKED: no", stage="content")
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
    mock_db.set_vacancy_blocker.assert_awaited_once_with(1, False, [], raw_output=rambling, stage="content")
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
async def test_prefilter_title_mismatch_short_circuits_no_llm_call(tmp_path):
    """Title check runs before the LLM — a mismatch must never reach get_llm()."""
    jd_path = _write_jd(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path, title="Product Marketing Lead")
    ctx = _make_ctx()
    mock_db = _mock_db(vacancy_row)

    with patch("tools.cv_prefilter.database", mock_db):
        result = await cv_prefilter(ctx, 1)

    ctx.deps.get_llm.assert_not_awaited()
    assert result["ok"] is True
    assert result["blocked"] is True
    assert result["format_ok"] is True
    assert len(result["reasons"]) == 1
    assert result["reasons"][0].startswith("title:")
    mock_db.set_vacancy_blocker.assert_awaited_once()
    args, kwargs = mock_db.set_vacancy_blocker.call_args
    assert args[0] == 1
    assert args[1] is True
    mock_db.update_pipeline_run.assert_any_call(1, status="done")


@pytest.mark.asyncio
async def test_prefilter_domain_signal_short_circuits_no_llm_call(tmp_path):
    """A fitting title with a blocked domain suffix (iGaming) still short-
    circuits — domain signal is checked before the allowlist fit check."""
    jd_path = _write_jd(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path, title="Product Manager (iGaming)")
    ctx = _make_ctx()
    mock_db = _mock_db(vacancy_row)

    with patch("tools.cv_prefilter.database", mock_db):
        result = await cv_prefilter(ctx, 1)

    ctx.deps.get_llm.assert_not_awaited()
    assert result["blocked"] is True
    assert result["reasons"][0].startswith("igaming:")


@pytest.mark.asyncio
async def test_prefilter_title_fit_proceeds_to_llm(tmp_path):
    """Title on the allowlist must still go through the normal LLM content check."""
    jd_path = _write_jd(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path, title="Product Owner Lead")
    llm = _make_llm("BLOCKED: no")
    ctx = _make_ctx(llm)
    mock_db = _mock_db(vacancy_row)

    with patch("tools.cv_prefilter.database", mock_db):
        result = await cv_prefilter(ctx, 1)

    ctx.deps.get_llm.assert_awaited_once()
    assert result["blocked"] is False


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
