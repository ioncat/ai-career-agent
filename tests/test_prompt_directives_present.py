"""Regression guards for three small prompt directives (see CHANGELOG 2026-10-08).

- prefilter: the Stage 2 language check compares CEFR levels instead of reacting to a mention;
- fit score: each piece of evidence earns credit once;
- cover: no example that models a personal-preference construction (a relative-clause
  self-intro); that preference lives in the user's profile, not in the engine.
"""
from __future__ import annotations

import re
from pathlib import Path

_PM = Path(__file__).resolve().parent.parent / "prompts" / "pm"


def _text(name: str) -> str:
    return " ".join((_PM / name).read_text(encoding="utf-8").split())


def test_prefilter_spells_out_the_cefr_order_and_labels():
    text = _text("prefilter.md")
    assert "A1, A2, B1, B2, C1, C2" in text
    assert "Upper-Intermediate = B2" in text
    assert "strictly higher" in text
    assert "Fluent = C1 to C2" in text and "Native = C2" in text
    assert "proficiency" in text  # the bare word is explicitly not a level label
    assert "profile's Critical Blockers" in text
    assert "Languages entry" not in text  # Stage 2 never receives it


def test_prefilter_names_no_candidate_level():
    """The candidate's level comes from the profile; the prompt must not state it."""
    text = _text("prefilter.md")
    assert not re.search(r"candidate(?:'s)? (?:is|level is|has) (?:about )?[ABC][12]\b", text)


def test_fit_score_counts_each_piece_of_evidence_once():
    text = _text("phase2_fit.md")
    assert "Count each piece of evidence once" in text
    assert "Signal Coverage Table may map one fact to several signals" in text


def test_cover_prompt_shows_no_relative_clause_self_intro():
    for f in _PM.rglob("*.md"):
        assert not re.search(r"який працює|яка працює", f.read_text(encoding="utf-8")), f.name


def test_phase_3_8_exists_and_hands_its_terms_to_phase_3_7():
    text = _text("phase3_7_ats_coverage.md")
    assert "Inserted terms:" in text and "literally" in text
    assert "Not run by default" in text or "not run by default" in text
    assert "Inserted terms" in _text("phase3_8_editorial_audit.md")


def test_skill_and_analyze_wire_phase_3_8_in_and_keep_it_out_of_lite():
    root = _PM.parent.parent
    skill = " ".join((root / "skill" / "SKILL.md").read_text(encoding="utf-8").split())
    analyze = " ".join((root / ".claude" / "commands" / "analyze.md").read_text(encoding="utf-8").split())
    assert "prompts/[skill_type]/phase3_7_ats_coverage.md" in skill
    assert "Phase 3.7 — ATS Keyword Coverage" in skill
    assert "Phase 3.6, 3.7 and 3.8 do not run" in skill
    assert "Phase 3.6, 3.7 and 3.8 do not run" in analyze
