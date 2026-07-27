"""
tests/test_cv_generate.py — tests for tools/cv_generate.py and adapters/cv_adapter.py.

Mocks: database, llm.complete, cv_adapter.generate_pdf, filesystem (tmp_path).
No real Claude API, DB, or subprocess needed.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adapters.cv_adapter import CVAdapter, CVAdapterError
from core.llm_client import LLMError
from tools.cv_generate import _next_version_path, _split_review_and_cv, cv_generate


# ── Fixtures / helpers ────────────────────────────────────────────────────────

_PHASE35_SAMPLE = """CV SELF-REVIEW
—————————————
❌ Remove / doesn't fit:
• Platform section — не релевантно для Feature PM роли

⚠️ Weaken / compress:
• Немає зауважень

🔧 Strengthen / reframe:
• Discovery experience — посилити

✅ Strong — keep as is:
• Key results у першій ролі

Oleksii Bondarenko
Product Owner / Product Manager
[email@example.com](mailto:email@example.com) · [Telegram](https://t.me/test)

SUMMARY

Strong product leader with 8 years of PM experience.

EXPERIENCE

**Senior PM**
Company A | 2020–2026
Owned roadmap.

Key results:
• Grew MAU 40%
"""

_PHASE3_DRAFT = "Oleksii Bondarenko\nProduct Manager\nemail@... \n\nSUMMARY\n\nDraft summary."


def _make_ctx(tmp_path: Path, llm=None, cv_adapter=None) -> MagicMock:
    ctx = MagicMock()
    ctx.deps.get_llm = AsyncMock(return_value=llm or _make_llm())
    ctx.deps.cv_adapter = cv_adapter or _make_cv_adapter()
    ctx.deps.candidate_name = "Oleksii_Bondarenko"
    ctx.deps.candidate_name_uk = "Олексій_Бондаренко"
    ctx.deps.vacancies_path = tmp_path / "vacancies"
    ctx.deps.skill_type = "pm"
    ctx.deps.user_id = 1
    return ctx


def _make_llm(side_effect=None, return_value="output") -> AsyncMock:
    llm = AsyncMock()
    llm.last_call_usage = None  # prevent **unpacking AsyncMock in insert_llm_usage
    if side_effect is not None:
        llm.complete = AsyncMock(side_effect=side_effect)
    else:
        llm.complete = AsyncMock(return_value=return_value)
    return llm


def _make_cv_adapter(pdf_path: Path | None = None) -> AsyncMock:
    adapter = AsyncMock(spec=CVAdapter)
    adapter.generate_pdf = AsyncMock(return_value=pdf_path or Path("/fake/CV.pdf"))
    return adapter


def _make_vacancy_row(
    jd_path: Path,
    vacancy_id: int = 1,
    title: str = "Backend Dev",
    url: str = "https://djinni.co/jobs/123/",
) -> MagicMock:
    data = {"id": vacancy_id, "title": title, "markdown_path": str(jd_path), "url": url, "status": "analyzed"}
    row = MagicMock()
    row.__getitem__ = lambda self, key: data[key]
    return row


def _write_vacancy_files(tmp_path: Path) -> tuple[Path, Path]:
    """Create JD.md + JD_analysis.md and return (jd_path, analysis_path)."""
    jd_dir = tmp_path / "vacancies" / "djinni" / "2026-05" / "123"
    jd_dir.mkdir(parents=True)
    jd_path = jd_dir / "JD.md"
    jd_path.write_text("# Backend Dev\n\nGreat role.", encoding="utf-8")
    analysis_path = jd_dir / "JD_analysis.md"
    analysis_path.write_text("## Quick Scan\n\n**Fit score:** 7/10", encoding="utf-8")
    return jd_path, analysis_path


def _mock_db(vacancy_row=None, run_ids: list[int] | None = None) -> MagicMock:
    run_ids = run_ids or [1, 2]
    db = MagicMock()
    db.get_vacancy_by_id = AsyncMock(return_value=vacancy_row)
    db.get_user_by_id = AsyncMock(return_value=None)  # no progressive_profile by default
    db.insert_pipeline_run = AsyncMock(side_effect=run_ids)
    db.update_pipeline_run = AsyncMock()
    db.update_vacancy_status = AsyncMock()
    db.insert_llm_usage = AsyncMock()
    return db


# ── _split_review_and_cv ──────────────────────────────────────────────────────

def test_split_finds_summary_anchor():
    review, cv = _split_review_and_cv(_PHASE35_SAMPLE)
    assert "CV SELF-REVIEW" in review
    assert "❌" in review
    assert "✅" in review
    # CV should NOT contain the review block
    assert "CV SELF-REVIEW" not in cv


def test_split_cv_contains_name_and_summary():
    _, cv = _split_review_and_cv(_PHASE35_SAMPLE)
    assert "Oleksii Bondarenko" in cv
    assert "SUMMARY" in cv
    assert "EXPERIENCE" in cv


def test_split_no_summary_returns_full_as_cv():
    text = "Just some output without SUMMARY keyword."
    review, cv = _split_review_and_cv(text)
    assert review == ""
    assert cv == text.strip()


def test_split_cv_precedes_experience():
    _, cv = _split_review_and_cv(_PHASE35_SAMPLE)
    summary_pos = cv.index("SUMMARY")
    experience_pos = cv.index("EXPERIENCE")
    assert summary_pos < experience_pos


def test_split_review_contains_all_categories():
    review, _ = _split_review_and_cv(_PHASE35_SAMPLE)
    assert "❌" in review
    assert "⚠️" in review
    assert "🔧" in review
    assert "✅" in review


def test_split_explicit_separator():
    """Strategy 1: ---CV--- separator splits correctly."""
    text = "Some review content\n\n---CV---\n\n# Oleksii Bondarenko\nSUMMARY"
    review, cv = _split_review_and_cv(text)
    assert review == "Some review content"
    assert cv.startswith("# Oleksii Bondarenko")


def test_split_h1_review_headings_do_not_break_strategy4():
    """Regression for vacancy #844 (2026-07-27): review sections used literal
    H1 headings ("# Top-15 Word Frequency", "# Tools & Technologies") instead
    of the code-fenced format other fixtures use. Taking the FIRST H1 match
    landed on the review heading (position 0), tripped the old m.start()>0
    guard, and fell through to "use everything, unsplit" — leaking the whole
    review block into the saved CV. The CV's own name header is reliably the
    LAST H1 in the output; strategy 4 must find that one, not the first.
    """
    text = (
        "# Top-15 Word Frequency\n\n"
        "```\nJD top-15   CV top-15\n13 macpaw   16 product\n```\n\n"
        "# 🛠️ Tools & Technologies\n\n"
        "```\nMake   —   missing\n```\n\n"
        "# CV SELF-REVIEW\n\n"
        "❌ Remove: none.\n\n"
        "# Alex Bondarenko\n"
        "Product Owner / Product Manager\n\n"
        "## SUMMARY\n\nStrong product leader.\n\n## EXPERIENCE\n\nSenior PM at Co.\n"
    )
    review, cv = _split_review_and_cv(text)
    assert cv.startswith("# Alex Bondarenko")
    assert "Top-15 Word Frequency" not in cv
    assert "Tools & Technologies" not in cv
    assert "CV SELF-REVIEW" not in cv
    assert "macpaw" not in cv
    assert "Top-15 Word Frequency" in review
    assert "CV SELF-REVIEW" in review


def test_split_cyrillic_h1_strategy4():
    """Strategy 4 must work for Ukrainian/Russian names (Cyrillic H1)."""
    text = (
        "```\nJD top-15 table\n```\n\n"
        "```\nCV SELF-REVIEW\n❌ remove something\n```\n\n"
        "# Олексій Бондаренко\nProduct Owner\n\nSUMMARY\n\nContent."
    )
    review, cv = _split_review_and_cv(text)
    assert "Олексій" not in review
    assert cv.startswith("# Олексій Бондаренко")


def test_split_cyrillic_uppercase_letters():
    """Strategy 4 covers full Cyrillic uppercase range (Ѐ-ӿ)."""
    text = "Review block\n\n# Іван Петренко\nPO · Kyiv\n\nSUMMARY"
    review, cv = _split_review_and_cv(text)
    assert review == "Review block"
    assert cv.startswith("# Іван Петренко")


def test_split_review_excluded_from_cv_cyrillic():
    """Full Phase 3.5 output with code-block review + Cyrillic CV — review must not leak into CV."""
    phase35 = (
        "```\nJD top-15\n1  продукт*\n```\n\n"
        "```\n🛠️ Tools\nFigma — aligned\n```\n\n"
        "```\nCV SELF-REVIEW\n❌ remove X\n✅ keep Y\n```\n\n"
        "# Олексій Бондаренко\n"
        "Product Owner / Product Manager\n"
        "email@example.com\n\n"
        "---\n\n"
        "PO опис.\n\n"
        "## ДОСВІД\n"
    )
    review, cv = _split_review_and_cv(phase35)
    assert "продукт*" not in cv
    assert "CV SELF-REVIEW" not in cv
    assert cv.startswith("# Олексій Бондаренко")
    assert "продукт*" in review


# ── cv_generate — happy path ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_happy_path(tmp_path):
    jd_path, _ = _write_vacancy_files(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(side_effect=[_PHASE3_DRAFT, _PHASE35_SAMPLE])
    pdf_path = jd_path.parent / "Oleksii_Bondarenko_CV.pdf"
    cv_adapter = _make_cv_adapter(pdf_path)
    ctx = _make_ctx(tmp_path, llm, cv_adapter)
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_generate.database", mock_db):
        result = await cv_generate(ctx, 1)

    assert "✅" in result
    assert "Backend Dev" in result
    assert "CV SELF-REVIEW" in result


@pytest.mark.asyncio
async def test_generate_saves_cv_md(tmp_path):
    jd_path, _ = _write_vacancy_files(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(side_effect=[_PHASE3_DRAFT, _PHASE35_SAMPLE])
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_generate.database", mock_db):
        await cv_generate(ctx, 1)

    cv_path = jd_path.parent / "Oleksii_Bondarenko_CV.md"
    assert cv_path.exists()
    content = cv_path.read_text()
    assert "SUMMARY" in content
    assert "Oleksii Bondarenko" in content


# ── Language-aware candidate name (2026-07-27) ─────────────────────────────────
# Found live on vacancy #844: candidate_name was a single static config value
# fed unconditionally into the Phase 3 prompt, regardless of the CV's language
# (English JD, Ukrainian formal name used). cv_generate() already auto-detects
# language — these assert it's actually wired to name selection now.

@pytest.mark.asyncio
async def test_generate_english_uses_candidate_name(tmp_path):
    jd_path, _ = _write_vacancy_files(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(side_effect=[_PHASE3_DRAFT, _PHASE35_SAMPLE])
    ctx = _make_ctx(tmp_path, llm)
    ctx.deps.candidate_name = "Alex Bondarenko"
    ctx.deps.candidate_name_uk = "Олексій Бондаренко"
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_generate.database", mock_db):
        await cv_generate(ctx, 1, language="English")

    phase3_prompt_sent = llm.complete.await_args_list[0].args[0]
    assert "Candidate name: Alex Bondarenko" in phase3_prompt_sent
    assert (jd_path.parent / "Alex_Bondarenko_CV.md").exists()


@pytest.mark.asyncio
async def test_generate_ukrainian_uses_candidate_name_uk(tmp_path):
    jd_path, _ = _write_vacancy_files(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(side_effect=[_PHASE3_DRAFT, _PHASE35_SAMPLE])
    ctx = _make_ctx(tmp_path, llm)
    ctx.deps.candidate_name = "Alex Bondarenko"
    ctx.deps.candidate_name_uk = "Олексій Бондаренко"
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_generate.database", mock_db):
        await cv_generate(ctx, 1, language="Ukrainian")

    phase3_prompt_sent = llm.complete.await_args_list[0].args[0]
    assert "Candidate name: Олексій Бондаренко" in phase3_prompt_sent
    assert (jd_path.parent / "Oleksii_Bondarenko_CV.md").exists()


@pytest.mark.asyncio
async def test_generate_auto_detected_ukrainian_uses_candidate_name_uk(tmp_path):
    """language='auto' + Cyrillic JD must also route to the Ukrainian name,
    not just an explicit language='Ukrainian' call."""
    jd_dir = tmp_path / "vacancies" / "dou" / "2026-05" / "999"
    jd_dir.mkdir(parents=True)
    jd_path = jd_dir / "JD.md"
    jd_path.write_text("# Продакт менеджер\n\nОпис вакансії українською.", encoding="utf-8")
    (jd_dir / "JD_analysis.md").write_text("## Quick Scan\n\n**Fit score:** 7/10", encoding="utf-8")
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(side_effect=[_PHASE3_DRAFT, _PHASE35_SAMPLE])
    ctx = _make_ctx(tmp_path, llm)
    ctx.deps.candidate_name = "Alex Bondarenko"
    ctx.deps.candidate_name_uk = "Олексій Бондаренко"
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_generate.database", mock_db):
        await cv_generate(ctx, 1, language="auto")

    phase3_prompt_sent = llm.complete.await_args_list[0].args[0]
    assert "Candidate name: Олексій Бондаренко" in phase3_prompt_sent


# ── _next_version_path ────────────────────────────────────────────────────────

def test_next_version_path_returns_base_when_missing(tmp_path):
    base = tmp_path / "Alex_CV.md"
    assert _next_version_path(base) == base


def test_next_version_path_increments_on_conflict(tmp_path):
    base = tmp_path / "Alex_CV.md"
    base.write_text("v1", encoding="utf-8")
    assert _next_version_path(base) == tmp_path / "Alex_CV_v2.md"

    (tmp_path / "Alex_CV_v2.md").write_text("v2", encoding="utf-8")
    assert _next_version_path(base) == tmp_path / "Alex_CV_v3.md"


@pytest.mark.asyncio
async def test_generate_saves_versioned_cv_on_regen(tmp_path):
    """Second generation writes _v2.md instead of overwriting."""
    jd_path, _ = _write_vacancy_files(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    ctx = _make_ctx(tmp_path, _make_llm(side_effect=[_PHASE3_DRAFT, _PHASE35_SAMPLE]))
    mock_db = _mock_db(vacancy_row=vacancy_row, run_ids=[1, 2])

    # First generation
    with patch("tools.cv_generate.database", mock_db):
        await cv_generate(ctx, 1)

    base = jd_path.parent / "Oleksii_Bondarenko_CV.md"
    assert base.exists()

    # Second generation — base file now exists
    ctx2 = _make_ctx(tmp_path, _make_llm(side_effect=[_PHASE3_DRAFT, _PHASE35_SAMPLE]))
    mock_db2 = _mock_db(vacancy_row=vacancy_row, run_ids=[3, 4])
    with patch("tools.cv_generate.database", mock_db2):
        await cv_generate(ctx2, 1)

    v2 = jd_path.parent / "Oleksii_Bondarenko_CV_v2.md"
    assert v2.exists()
    assert base.exists()  # original untouched


@pytest.mark.asyncio
async def test_generate_saves_draft_p3(tmp_path):
    """Phase 3 raw draft is saved for debugging."""
    jd_path, _ = _write_vacancy_files(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(side_effect=[_PHASE3_DRAFT, _PHASE35_SAMPLE])
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_generate.database", mock_db):
        await cv_generate(ctx, 1)

    draft_path = jd_path.parent / "CV_draft_p3.md"
    assert draft_path.exists()


@pytest.mark.asyncio
async def test_generate_appends_review_to_analysis(tmp_path):
    jd_path, analysis_path = _write_vacancy_files(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(side_effect=[_PHASE3_DRAFT, _PHASE35_SAMPLE])
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_generate.database", mock_db):
        await cv_generate(ctx, 1)

    content = analysis_path.read_text(encoding="utf-8")
    assert "Phase 3.5: CV Self-Review" in content
    assert "CV SELF-REVIEW" in content


@pytest.mark.asyncio
async def test_generate_updates_status(tmp_path):
    jd_path, _ = _write_vacancy_files(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(side_effect=[_PHASE3_DRAFT, _PHASE35_SAMPLE])
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_generate.database", mock_db):
        await cv_generate(ctx, 1)

    mock_db.update_vacancy_status.assert_awaited_once_with(1, "cv_generated")


@pytest.mark.asyncio
async def test_generate_calls_llm_twice(tmp_path):
    jd_path, _ = _write_vacancy_files(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(side_effect=[_PHASE3_DRAFT, _PHASE35_SAMPLE])
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_generate.database", mock_db):
        await cv_generate(ctx, 1)

    assert llm.complete.await_count == 2


@pytest.mark.asyncio
async def test_generate_phase35_receives_phase3_output(tmp_path):
    """Phase 3.5 user input must contain Phase 3 draft."""
    jd_path, _ = _write_vacancy_files(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    unique_p3 = "UNIQUE_PHASE3_DRAFT_MARKER"
    llm = _make_llm(side_effect=[unique_p3, _PHASE35_SAMPLE])
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_generate.database", mock_db):
        await cv_generate(ctx, 1)

    second_call_user = llm.complete.call_args_list[1][0][0]
    assert unique_p3 in second_call_user


@pytest.mark.asyncio
async def test_generate_injects_progressive_profile_into_phase3(tmp_path):
    """T6: progressive_profile roles are appended to Phase 3 user message when present."""
    import json as _json
    jd_path, _ = _write_vacancy_files(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(side_effect=[_PHASE3_DRAFT, _PHASE35_SAMPLE])
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=vacancy_row)

    profile = {
        "meta": {"schema_version": 1},
        "roles": [
            {
                "id": "test_po",
                "title": "Product Owner",
                "company": "TestCorp",
                "dates": "2020-2024",
                "narrative": "Led product discovery for B2B platform.",
                "key_results": ["Shipped 3 major features", "NPS +15"],
            }
        ],
    }
    from unittest.mock import MagicMock
    user_row = MagicMock()
    user_row.keys.return_value = ["progressive_profile"]
    user_row.__getitem__ = MagicMock(side_effect=lambda key: _json.dumps(profile) if key == "progressive_profile" else None)
    mock_db.get_user_by_id = AsyncMock(return_value=user_row)

    with patch("tools.cv_generate.database", mock_db):
        await cv_generate(ctx, 1)

    # Phase 3 call (first LLM call) user message should contain the profile evidence
    phase3_user_msg = llm.complete.call_args_list[0][0][0]
    assert "TestCorp" in phase3_user_msg
    assert "Candidate Evidence (DB Profile)" in phase3_user_msg
    assert "NPS +15" in phase3_user_msg


@pytest.mark.asyncio
async def test_generate_pdf_failure_non_fatal(tmp_path):
    """PDF generation failure should not fail the whole tool."""
    jd_path, _ = _write_vacancy_files(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(side_effect=[_PHASE3_DRAFT, _PHASE35_SAMPLE])
    cv_adapter = AsyncMock(spec=CVAdapter)
    cv_adapter.generate_pdf = AsyncMock(side_effect=CVAdapterError("fpdf not installed"))
    ctx = _make_ctx(tmp_path, llm, cv_adapter)
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_generate.database", mock_db):
        result = await cv_generate(ctx, 1)

    assert "✅" in result
    assert "не удалось" in result


# ── cv_generate — error cases ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_vacancy_not_found(tmp_path):
    ctx = _make_ctx(tmp_path)
    mock_db = _mock_db(vacancy_row=None)

    with patch("tools.cv_generate.database", mock_db):
        result = await cv_generate(ctx, 999)

    assert "⚠️" in result
    assert "999" in result


@pytest.mark.asyncio
async def test_generate_jd_missing(tmp_path):
    jd_path, _ = _write_vacancy_files(tmp_path)
    jd_path.unlink()
    vacancy_row = _make_vacancy_row(jd_path)
    ctx = _make_ctx(tmp_path)
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_generate.database", mock_db):
        result = await cv_generate(ctx, 1)

    assert "⚠️" in result
    assert "JD.md" in result


@pytest.mark.asyncio
async def test_generate_analysis_missing(tmp_path):
    jd_path, analysis_path = _write_vacancy_files(tmp_path)
    analysis_path.unlink()
    vacancy_row = _make_vacancy_row(jd_path)
    ctx = _make_ctx(tmp_path)
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_generate.database", mock_db):
        result = await cv_generate(ctx, 1)

    assert "⚠️" in result
    assert "JD_analysis.md" in result


@pytest.mark.asyncio
async def test_generate_phase3_llm_error(tmp_path):
    jd_path, _ = _write_vacancy_files(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(side_effect=LLMError("Phase 3 timeout"))
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=vacancy_row, run_ids=[1])

    with patch("tools.cv_generate.database", mock_db):
        with pytest.raises(LLMError, match="Phase 3 timeout"):
            await cv_generate(ctx, 1)

    mock_db.update_vacancy_status.assert_not_called()


@pytest.mark.asyncio
async def test_generate_phase35_llm_error(tmp_path):
    jd_path, _ = _write_vacancy_files(tmp_path)
    vacancy_row = _make_vacancy_row(jd_path)
    llm = _make_llm(side_effect=[_PHASE3_DRAFT, LLMError("Phase 3.5 rate limit")])
    ctx = _make_ctx(tmp_path, llm)
    mock_db = _mock_db(vacancy_row=vacancy_row)

    with patch("tools.cv_generate.database", mock_db):
        with pytest.raises(LLMError, match="Phase 3.5 rate limit"):
            await cv_generate(ctx, 1)

    mock_db.update_vacancy_status.assert_not_called()
    # [Name]_CV.md must NOT be written
    assert not (jd_path.parent / "Oleksii_Bondarenko_CV.md").exists()

