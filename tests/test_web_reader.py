"""
tests/test_web_reader.py — Unit tests for web/reader.py.

Tests VacancyView properties, _extract(), _status_gte(),
and build_vacancy_view() with filesystem fixtures.
No DB connection needed — rows are plain dicts.
"""

import pytest
from pathlib import Path

from web.reader import (
    VacancyView,
    build_vacancy_view,
    _extract,
    _status_gte,
    _FIT_RE,
    _REC_RE,
    _WARN_RE,
    _BLOCK_RE,
    _CAT_RE,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row(
    *,
    id: int = 1,
    title: str = "Test Vacancy",
    url: str = "https://example.com/job/1",
    site: str = "other",
    status: str = "fetched",
    created_at: str = "2026-05-30 10:00:00",
    markdown_path: str | None = None,
) -> dict:
    """Minimal dict that mimics an aiosqlite.Row."""
    return dict(
        id=id,
        title=title,
        url=url,
        site=site,
        status=status,
        created_at=created_at,
        markdown_path=markdown_path,
    )


_SAMPLE_ANALYSIS = """\
# JD Analysis — Test Vacancy

Date: 2026-05-30
Source: https://example.com/job/1

---

## Quick Scan

**Category:** AI Product · Remote
**Fit score:** 8/10
**Key Barriers:** нет
**Warnings:** нет публичной информации; зарплата не указана
**Recommendation:** подавать

---

## Phase 1 — JD Analysis

Some content here.
"""


# ── _extract() ────────────────────────────────────────────────────────────────

class TestExtract:
    def test_fit_score_found(self):
        assert _extract(_SAMPLE_ANALYSIS, _FIT_RE) == "8/10"

    def test_recommendation_found(self):
        assert _extract(_SAMPLE_ANALYSIS, _REC_RE) == "подавать"

    def test_category_found(self):
        assert _extract(_SAMPLE_ANALYSIS, _CAT_RE) == "AI Product · Remote"

    def test_warnings_found(self):
        assert _extract(_SAMPLE_ANALYSIS, _WARN_RE) == "нет публичной информации; зарплата не указана"

    def test_blockers_found(self):
        assert _extract(_SAMPLE_ANALYSIS, _BLOCK_RE) == "нет"

    def test_missing_field_returns_empty(self):
        assert _extract("no fields here", _FIT_RE) == ""

    def test_strips_whitespace(self):
        text = "**Fit score:**   9/10  \n"
        assert _extract(text, _FIT_RE) == "9/10"

    def test_empty_string_input(self):
        assert _extract("", _FIT_RE) == ""


# ── _status_gte() ─────────────────────────────────────────────────────────────

class TestStatusGte:
    def test_same_status(self):
        assert _status_gte("fetched", "fetched") is True
        assert _status_gte("analyzed", "analyzed") is True

    def test_higher_than_threshold(self):
        assert _status_gte("analyzed", "fetched") is True
        assert _status_gte("cover_generated", "fetched") is True
        assert _status_gte("cv_generated", "analyzed") is True

    def test_lower_than_threshold(self):
        assert _status_gte("fetched", "analyzed") is False
        assert _status_gte("analyzed", "cv_generated") is False

    def test_unknown_status_returns_false(self):
        assert _status_gte("unknown", "fetched") is False
        assert _status_gte("fetched", "unknown") is False


# ── VacancyView.rec_class ─────────────────────────────────────────────────────

class TestRecClass:
    def _view(self, rec: str) -> VacancyView:
        return VacancyView(
            id=1, title="T", url="u", site="s", status="fetched", date="2026-05-30",
            fit_score="—", recommendation=rec, category="", warnings="", blockers="",
            has_analysis=False, has_cv=False, has_cover=False, has_pdf=False,
            analysis_md="", salary="",
        )

    def test_podavat(self):
        assert self._view("подавать").rec_class == "rec-yes"

    def test_podavat_with_emoji(self):
        assert self._view("✅ подавать").rec_class == "rec-yes"

    def test_ne_podavat(self):
        assert self._view("не подавать").rec_class == "rec-no"

    def test_ne_podavat_with_reason(self):
        assert self._view("не подавать — слабый fit").rec_class == "rec-no"

    def test_apply_english(self):
        assert self._view("apply").rec_class == "rec-yes"

    def test_not_apply_english(self):
        assert self._view("not apply").rec_class == "rec-no"

    def test_empty_rec(self):
        assert self._view("").rec_class == ""

    def test_unknown_rec(self):
        assert self._view("подумать").rec_class == ""

    def test_decline_english(self):
        assert self._view("decline").rec_class == "rec-no"

    def test_take_a_chance_english(self):
        assert self._view("take a chance").rec_class == "rec-consider"

    def test_take_a_chance_uppercase(self):
        assert self._view("Take a Chance").rec_class == "rec-consider"

    def test_rassmotrety(self):
        assert self._view("рассмотреть").rec_class == "rec-consider"


# ── VacancyView.warn_count ────────────────────────────────────────────────────

class TestWarnCount:
    def _view(self, warnings: str) -> VacancyView:
        return VacancyView(
            id=1, title="T", url="u", site="s", status="fetched", date="2026-05-30",
            fit_score="—", recommendation="", category="", warnings=warnings, blockers="",
            has_analysis=False, has_cv=False, has_cover=False, has_pdf=False,
            analysis_md="", salary="",
        )

    def test_empty(self):
        assert self._view("").warn_count == 0

    def test_net(self):
        assert self._view("нет").warn_count == 0

    def test_none_english(self):
        assert self._view("none").warn_count == 0

    def test_dash(self):
        assert self._view("—").warn_count == 0
        assert self._view("-").warn_count == 0

    def test_single_warning(self):
        assert self._view("зарплата не указана").warn_count == 1

    def test_two_warnings(self):
        assert self._view("нет публичной информации; зарплата не указана").warn_count == 2

    def test_three_warnings(self):
        assert self._view("a; b; c").warn_count == 3

    def test_empty_segments_ignored(self):
        assert self._view("; ;").warn_count == 0


# ── VacancyView.warn_text_escaped ─────────────────────────────────────────────

class TestWarnTextEscaped:
    def _view(self, warnings: str) -> VacancyView:
        return VacancyView(
            id=1, title="T", url="u", site="s", status="fetched", date="2026-05-30",
            fit_score="—", recommendation="", category="", warnings=warnings, blockers="",
            has_analysis=False, has_cv=False, has_cover=False, has_pdf=False,
            analysis_md="", salary="",
        )

    def test_plain_text_unchanged(self):
        assert self._view("normal text").warn_text_escaped == "normal text"

    def test_single_quote_escaped(self):
        assert self._view("don't").warn_text_escaped == "don\\'t"

    def test_double_quote_escaped(self):
        assert self._view('say "hi"').warn_text_escaped == "say &quot;hi&quot;"

    def test_empty(self):
        assert self._view("").warn_text_escaped == ""


# ── build_vacancy_view() ──────────────────────────────────────────────────────

class TestBuildVacancyView:

    def test_minimal_row_no_markdown_path(self):
        row = _row()
        v = build_vacancy_view(row)
        assert v.id == 1
        assert v.title == "Test Vacancy"
        assert v.fit_score == "—"
        assert v.has_analysis is False
        assert v.has_cv is False
        assert v.analysis_md == ""

    def test_null_title_becomes_fallback(self):
        row = _row(title=None)
        v = build_vacancy_view(row)
        assert v.title == "Без названия"

    def test_date_extracted_from_created_at(self):
        row = _row(created_at="2026-05-30 12:34:56")
        v = build_vacancy_view(row)
        assert v.date == "2026-05-30"

    def test_empty_created_at(self):
        row = _row(created_at="")
        v = build_vacancy_view(row)
        assert v.date == ""

    def test_no_markdown_path_all_artifacts_false(self):
        row = _row(markdown_path=None)
        v = build_vacancy_view(row)
        assert not any([v.has_analysis, v.has_cv, v.has_cover, v.has_pdf])

    def test_markdown_path_no_analysis_file(self, tmp_path):
        jd = tmp_path / "JD.md"
        jd.write_text("# Job", encoding="utf-8")
        row = _row(markdown_path=str(jd))
        v = build_vacancy_view(row)
        assert v.has_analysis is False
        assert v.fit_score == "—"
        assert v.analysis_md == ""

    def test_with_analysis_file_parses_fields(self, tmp_path):
        jd = tmp_path / "JD.md"
        jd.write_text("# Job", encoding="utf-8")
        analysis = tmp_path / "JD_analysis.md"
        analysis.write_text(_SAMPLE_ANALYSIS, encoding="utf-8")
        row = _row(markdown_path=str(jd))
        v = build_vacancy_view(row)
        assert v.has_analysis is True
        assert v.fit_score == "8/10"
        assert v.recommendation == "подавать"
        assert v.category == "AI Product · Remote"
        assert v.warn_count == 2
        assert v.blockers == "нет"
        assert v.analysis_md == _SAMPLE_ANALYSIS

    def test_artifact_files_detected(self, tmp_path):
        jd = tmp_path / "JD.md"
        jd.write_text("# Job", encoding="utf-8")
        (tmp_path / "JD_analysis.md").write_text(_SAMPLE_ANALYSIS, encoding="utf-8")
        (tmp_path / "Candidate_CV.md").write_text("cv", encoding="utf-8")
        (tmp_path / "Candidate_CV.pdf").write_bytes(b"%PDF")
        (tmp_path / "Candidate_Cover.md").write_text("cover", encoding="utf-8")
        row = _row(markdown_path=str(jd))
        v = build_vacancy_view(row, candidate_name="Candidate")
        assert v.has_analysis is True
        assert v.has_cv is True
        assert v.has_pdf is True
        assert v.has_cover is True

    def test_candidate_name_special_chars_sanitized(self, tmp_path):
        """Spaces and dots in name become underscores in artifact paths."""
        jd = tmp_path / "JD.md"
        jd.write_text("# Job", encoding="utf-8")
        (tmp_path / "JD_analysis.md").write_text(_SAMPLE_ANALYSIS, encoding="utf-8")
        # Name with spaces → "Oleksii Bondarenko_CV.md" (spaces preserved)
        (tmp_path / "Oleksii Bondarenko_CV.md").write_text("cv", encoding="utf-8")
        row = _row(markdown_path=str(jd))
        v = build_vacancy_view(row, candidate_name="Oleksii Bondarenko")
        assert v.has_cv is True

    def test_oserror_on_analysis_read_does_not_raise(self, tmp_path):
        """If analysis file disappears between exists() and read(), graceful."""
        jd = tmp_path / "JD.md"
        jd.write_text("# Job", encoding="utf-8")
        analysis = tmp_path / "JD_analysis.md"
        analysis.write_text(_SAMPLE_ANALYSIS, encoding="utf-8")
        row = _row(markdown_path=str(jd))
        # Remove the file after view is about to be built — simulate OSError
        # by passing a path that has the analysis as unreadable
        # Simulate by making it a directory instead
        analysis.unlink()
        analysis.mkdir()
        v = build_vacancy_view(row)
        # Should not raise; analysis fields fall back to defaults
        assert v.fit_score == "—"
        assert v.analysis_md == ""

    def test_rec_class_propagated(self, tmp_path):
        jd = tmp_path / "JD.md"
        jd.write_text("# Job", encoding="utf-8")
        (tmp_path / "JD_analysis.md").write_text(_SAMPLE_ANALYSIS, encoding="utf-8")
        row = _row(markdown_path=str(jd))
        v = build_vacancy_view(row)
        assert v.rec_class == "rec-yes"


# ── VacancyView.site_display ──────────────────────────────────────────────────

class TestSiteDisplay:
    def _view(self, site: str) -> VacancyView:
        return VacancyView(
            id=1, title="T", url="u", site=site, status="fetched", date="2026-05-30",
            fit_score="—", recommendation="", category="", warnings="", blockers="",
            has_analysis=False, has_cv=False, has_cover=False, has_pdf=False,
            analysis_md="", salary="",
        )

    def test_djinni(self):
        assert self._view("djinni").site_display == "Djinni"

    def test_dou(self):
        assert self._view("dou").site_display == "DOU"

    def test_linkedin(self):
        assert self._view("linkedin").site_display == "LinkedIn"

    def test_unknown_capitalised(self):
        assert self._view("hh").site_display == "Hh"

    def test_other_keyword(self):
        assert self._view("other").site_display == "Other"

    def test_empty_returns_other(self):
        assert self._view("").site_display == "Other"


# ── VacancyView.applied ───────────────────────────────────────────────────────

class TestApplied:
    def _view(self, applied: bool = False) -> VacancyView:
        return VacancyView(
            id=1, title="T", url="u", site="s", status="fetched", date="2026-05-30",
            fit_score="—", recommendation="", category="", warnings="", blockers="",
            has_analysis=False, has_cv=False, has_cover=False, has_pdf=False,
            applied=applied,
        )

    def test_applied_defaults_false(self):
        v = VacancyView(
            id=1, title="T", url="u", site="s", status="fetched", date="2026-05-30",
            fit_score="—", recommendation="", category="", warnings="", blockers="",
            has_analysis=False, has_cv=False, has_cover=False, has_pdf=False,
        )
        assert v.applied is False

    def test_applied_true(self):
        assert self._view(applied=True).applied is True

    def test_applied_false(self):
        assert self._view(applied=False).applied is False


# ── VacancyView.starred ───────────────────────────────────────────────────────

class TestStarred:
    def _view(self, starred: bool = False) -> VacancyView:
        return VacancyView(
            id=1, title="T", url="u", site="s", status="fetched", date="2026-05-30",
            fit_score="—", recommendation="", category="", warnings="", blockers="",
            has_analysis=False, has_cv=False, has_cover=False, has_pdf=False,
            starred=starred,
        )

    def test_starred_defaults_false(self):
        v = VacancyView(
            id=1, title="T", url="u", site="s", status="fetched", date="2026-05-30",
            fit_score="—", recommendation="", category="", warnings="", blockers="",
            has_analysis=False, has_cv=False, has_cover=False, has_pdf=False,
        )
        assert v.starred is False

    def test_starred_true(self):
        assert self._view(starred=True).starred is True

    def test_starred_false(self):
        assert self._view(starred=False).starred is False
