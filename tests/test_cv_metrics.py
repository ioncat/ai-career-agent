"""Tests for core/cv_metrics.py — pre-computed CV/JD metric functions."""

import pytest

from core.cv_metrics import (
    detect_repetition,
    format_freq_table,
    format_tools_table,
    scan_tools,
    top_n_words,
)


# ── top_n_words ───────────────────────────────────────────────────────────────


class TestTopNWords:
    def test_returns_list_of_tuples(self):
        result = top_n_words("product manager roadmap roadmap roadmap")
        assert isinstance(result, list)
        assert all(isinstance(t, tuple) and len(t) == 2 for t in result)

    def test_counts_frequencies(self):
        result = top_n_words("roadmap roadmap roadmap product product")
        words = dict(result)
        assert words["roadmap"] == 3
        assert words["product"] == 2

    def test_sorted_descending(self):
        result = top_n_words("roadmap roadmap roadmap product product stakeholder")
        counts = [c for _, c in result]
        assert counts == sorted(counts, reverse=True)

    def test_stopwords_excluded(self):
        text = "the a an and or but in on at to for of with by from product"
        result = top_n_words(text)
        words = [w for w, _ in result]
        assert "the" not in words
        assert "and" not in words
        assert "product" in words

    def test_respects_n_limit(self):
        text = " ".join(f"word{i}" * (20 - i) for i in range(20))
        result = top_n_words(text, n=5)
        assert len(result) <= 5

    def test_empty_text_returns_empty(self):
        assert top_n_words("") == []

    def test_case_insensitive(self):
        result = top_n_words("Roadmap roadmap ROADMAP")
        words = dict(result)
        assert words.get("roadmap") == 3

    def test_min_word_length_three(self):
        # Words shorter than 3 chars should be excluded by regex
        result = top_n_words("ab cd ef roadmap")
        words = [w for w, _ in result]
        assert "ab" not in words
        assert "cd" not in words
        assert "roadmap" in words

    def test_default_n_is_15(self):
        # Generate 20 distinct words each appearing once
        text = " ".join(f"uniqueword{i}" * 1 for i in range(20))
        result = top_n_words(text)
        assert len(result) <= 15


# ── scan_tools ────────────────────────────────────────────────────────────────


class TestScanTools:
    def test_returns_list_of_dicts(self):
        result = scan_tools("We use Jira for tracking", "Managed backlog in Jira")
        assert isinstance(result, list)
        for row in result:
            assert "tool" in row
            assert "category" in row
            assert "in_jd" in row
            assert "in_cv" in row
            assert "signal" in row

    def test_aligned_signal(self):
        result = scan_tools("Uses Jira", "Experience with Jira")
        jira_rows = [r for r in result if r["tool"] == "Jira"]
        assert len(jira_rows) == 1
        assert jira_rows[0]["signal"] == "aligned"
        assert jira_rows[0]["in_jd"] is True
        assert jira_rows[0]["in_cv"] is True

    def test_missing_signal(self):
        result = scan_tools("Requires Figma", "Used Sketch and Miro")
        figma_rows = [r for r in result if r["tool"] == "Figma"]
        assert len(figma_rows) == 1
        assert figma_rows[0]["signal"] == "missing"
        assert figma_rows[0]["in_jd"] is True
        assert figma_rows[0]["in_cv"] is False

    def test_extra_signal(self):
        result = scan_tools("No specific tools required", "Experienced in Notion")
        notion_rows = [r for r in result if r["tool"] == "Notion"]
        assert len(notion_rows) == 1
        assert notion_rows[0]["signal"] == "extra"
        assert notion_rows[0]["in_jd"] is False
        assert notion_rows[0]["in_cv"] is True

    def test_tools_not_mentioned_excluded(self):
        result = scan_tools("Generic job description", "Generic CV content")
        assert result == []

    def test_case_insensitive_match(self):
        result = scan_tools("Use jira for tasks", "Experience in JIRA")
        jira_rows = [r for r in result if r["tool"] == "Jira"]
        assert len(jira_rows) == 1
        assert jira_rows[0]["signal"] == "aligned"

    def test_assigns_correct_category(self):
        result = scan_tools("Uses Mixpanel", "")
        mixpanel_rows = [r for r in result if r["tool"] == "Mixpanel"]
        assert len(mixpanel_rows) == 1
        assert mixpanel_rows[0]["category"] == "Analytics / tracking"

    def test_multiple_tools_same_jd(self):
        result = scan_tools("Uses Jira and Figma and SQL", "Has Jira")
        tools_in_jd = [r for r in result if r["in_jd"]]
        tool_names = {r["tool"] for r in tools_in_jd}
        assert "Jira" in tool_names
        assert "Figma" in tool_names
        assert "SQL" in tool_names

    def test_word_boundary_match(self):
        # "Figmatic" should NOT match "Figma"
        result = scan_tools("Figmatic tool", "Figmatic CV")
        figma_rows = [r for r in result if r["tool"] == "Figma"]
        assert len(figma_rows) == 0


# ── detect_repetition ─────────────────────────────────────────────────────────


class TestDetectRepetition:
    def test_returns_list(self):
        result = detect_repetition("some text here")
        assert isinstance(result, list)

    def test_finds_repeated_words(self):
        text = "managed backlog managed backlog managed stakeholders"
        result = detect_repetition(text, threshold=3)
        assert "managed" in result

    def test_threshold_respected(self):
        text = "roadmap roadmap planning planning planning"
        result = detect_repetition(text, threshold=3)
        assert "roadmap" not in result  # only 2 occurrences
        assert "planning" in result  # 3 occurrences

    def test_stopwords_excluded(self):
        text = "the the the the and and and"
        result = detect_repetition(text, threshold=3)
        assert "the" not in result
        assert "and" not in result

    def test_focuses_on_body_after_summary(self):
        # Words before SUMMARY should not be counted
        text = "prologue prologue prologue\nSUMMARY\nbody content roadmap roadmap roadmap"
        result = detect_repetition(text, threshold=3)
        assert "prologue" not in result
        assert "roadmap" in result

    def test_empty_text_returns_empty(self):
        assert detect_repetition("") == []

    def test_min_word_length_four(self):
        # Words under 4 chars excluded by regex
        text = "abc abc abc"
        result = detect_repetition(text, threshold=3)
        assert "abc" not in result

    def test_sorted_by_frequency(self):
        text = "roadmap " * 5 + "planning " * 4 + "stakeholder " * 3
        result = detect_repetition(text, threshold=3)
        # roadmap should come before stakeholder
        assert result.index("roadmap") < result.index("stakeholder")


# ── format_freq_table ─────────────────────────────────────────────────────────


class TestFormatFreqTable:
    def _sample_freq(self, words: list[str]) -> list[tuple[str, int]]:
        from collections import Counter
        c = Counter(words)
        return c.most_common(15)

    def test_returns_string(self):
        jd = self._sample_freq(["product"] * 5 + ["roadmap"] * 3)
        cv = self._sample_freq(["product"] * 4 + ["backlog"] * 2)
        result = format_freq_table(jd, cv)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_header_row(self):
        jd = [("product", 5), ("roadmap", 3)]
        cv = [("product", 4), ("backlog", 2)]
        result = format_freq_table(jd, cv)
        assert "JD top-15" in result
        assert "CV top-15" in result

    def test_contains_word_entries(self):
        jd = [("product", 5)]
        cv = [("product", 4)]
        result = format_freq_table(jd, cv)
        assert "product" in result

    def test_empty_inputs(self):
        result = format_freq_table([], [])
        assert isinstance(result, str)

    def test_missing_flag_for_top5_jd_word_absent_cv(self):
        # Build JD top-5 word not in CV
        jd_freq = [("product", 10), ("roadmap", 8), ("stakeholder", 6),
                   ("backlog", 5), ("sprint", 4), ("velocity", 3)]
        cv_freq = [("planning", 9), ("delivery", 7), ("release", 5)]
        result = format_freq_table(jd_freq, cv_freq)
        assert "👻" in result

    def test_overloaded_flag_for_top3_cv_word_not_in_jd(self):
        # Build CV top-3 word not in JD top-10
        jd_freq = [("product", 5)]
        cv_freq = [("synergy", 20), ("dynamic", 15), ("leverage", 12)]
        result = format_freq_table(jd_freq, cv_freq)
        assert "📣" in result


# ── format_tools_table ────────────────────────────────────────────────────────


class TestFormatToolsTable:
    def test_returns_string(self):
        rows = [{"tool": "Jira", "category": "Project / backlog",
                 "in_jd": True, "in_cv": True, "signal": "aligned"}]
        result = format_tools_table(rows)
        assert isinstance(result, str)

    def test_contains_header(self):
        rows = [{"tool": "Figma", "category": "Design / prototyping",
                 "in_jd": True, "in_cv": False, "signal": "missing"}]
        result = format_tools_table(rows)
        assert "🛠️ Tools & Technologies" in result

    def test_empty_rows_no_tools_message(self):
        result = format_tools_table([])
        assert "no specific tools" in result.lower() or "names no" in result.lower()

    def test_aligned_signal_shown(self):
        rows = [{"tool": "Notion", "category": "Project / backlog",
                 "in_jd": True, "in_cv": True, "signal": "aligned"}]
        result = format_tools_table(rows)
        assert "✅ aligned" in result
        assert "Notion" in result

    def test_missing_signal_shown(self):
        rows = [{"tool": "SQL", "category": "Data / BI",
                 "in_jd": True, "in_cv": False, "signal": "missing"}]
        result = format_tools_table(rows)
        assert "👻 missing" in result

    def test_extra_signal_shown(self):
        rows = [{"tool": "Zapier", "category": "Automation",
                 "in_jd": False, "in_cv": True, "signal": "extra"}]
        result = format_tools_table(rows)
        assert "📣 extra" in result

    def test_missing_tool_shows_dash_in_cv_column(self):
        rows = [{"tool": "Figma", "category": "Design / prototyping",
                 "in_jd": True, "in_cv": False, "signal": "missing"}]
        result = format_tools_table(rows)
        assert "—" in result

    def test_multiple_rows(self):
        rows = [
            {"tool": "Jira", "category": "Project / backlog",
             "in_jd": True, "in_cv": True, "signal": "aligned"},
            {"tool": "Figma", "category": "Design / prototyping",
             "in_jd": True, "in_cv": False, "signal": "missing"},
        ]
        result = format_tools_table(rows)
        assert "Jira" in result
        assert "Figma" in result
