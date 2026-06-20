"""
tests/test_profile_loader.py — unit tests for core/profile_loader.py
"""

import json
from pathlib import Path

import pytest

from contracts.profile import CandidateProfile
from core.profile_loader import _setting, _yaml_list, _vacancy_prefs, parse_profile_md

# ── Fixtures ──────────────────────────────────────────────────────────────────

PROFILE_SNIPPET = """
## Settings

language: ru
skill_type: pm
# comment line — ignored

---

## Vacancy Preferences

Used by Phase 1 (section 1.7) to compute VScore.

```yaml
domain_interests:
  - AI / ML
  - fintech
  - b2b saas

company_stage_prefs:
  - startup
  - founder-led
  - scaleup
```

*To extend: add items to either list.*
"""

MINIMAL_PROFILE = """
## Settings

language: en
skill_type: generic
"""

EMPTY_PROFILE = "# Some Profile\n\nNo structured sections here.\n"


# ── _setting ─────────────────────────────────────────────────────────────────


def test_setting_reads_language():
    assert _setting(PROFILE_SNIPPET, "language") == "ru"


def test_setting_reads_skill_type():
    assert _setting(PROFILE_SNIPPET, "skill_type") == "pm"


def test_setting_returns_none_when_key_missing():
    assert _setting(PROFILE_SNIPPET, "nonexistent_key") is None


def test_setting_returns_none_when_section_absent():
    assert _setting(EMPTY_PROFILE, "language") is None


def test_setting_ignores_comment_lines():
    # comment "# comment line — ignored" should not match as a key
    assert _setting(PROFILE_SNIPPET, "#") is None


# ── _yaml_list ────────────────────────────────────────────────────────────────

YAML_BLOCK = """
domain_interests:
  - AI / ML
  - fintech
  - b2b saas

company_stage_prefs:
  - startup
  - founder-led
"""


def test_yaml_list_domain_interests():
    result = _yaml_list(YAML_BLOCK, "domain_interests")
    assert result == ["AI / ML", "fintech", "b2b saas"]


def test_yaml_list_company_stage_prefs():
    result = _yaml_list(YAML_BLOCK, "company_stage_prefs")
    assert result == ["startup", "founder-led"]


def test_yaml_list_missing_key_returns_empty():
    assert _yaml_list(YAML_BLOCK, "nonexistent") == []


def test_yaml_list_strips_leading_dash_and_whitespace():
    yaml = "items:\n  - foo bar\n  -   baz qux  \n"
    assert _yaml_list(yaml, "items") == ["foo bar", "baz qux"]


# ── _vacancy_prefs ────────────────────────────────────────────────────────────


def test_vacancy_prefs_extracts_both_lists():
    prefs = _vacancy_prefs(PROFILE_SNIPPET)
    assert prefs["domain_interests"] == ["AI / ML", "fintech", "b2b saas"]
    assert prefs["company_stage_prefs"] == ["startup", "founder-led", "scaleup"]


def test_vacancy_prefs_missing_section_returns_empty():
    assert _vacancy_prefs(EMPTY_PROFILE) == {}


def test_vacancy_prefs_section_without_yaml_block():
    text = "## Vacancy Preferences\n\nNo code block here.\n\n## Next\n"
    assert _vacancy_prefs(text) == {}


# ── parse_profile_md ─────────────────────────────────────────────────────────


def test_parse_full_snippet():
    profile = parse_profile_md(PROFILE_SNIPPET)
    assert profile.language == "ru"
    assert profile.skill_type == "pm"
    assert "AI / ML" in profile.domain_interests
    assert "fintech" in profile.domain_interests
    assert "b2b saas" in profile.domain_interests
    assert "startup" in profile.company_stage_prefs
    assert "founder-led" in profile.company_stage_prefs
    assert "scaleup" in profile.company_stage_prefs


def test_parse_minimal_returns_defaults_for_missing_prefs():
    profile = parse_profile_md(MINIMAL_PROFILE)
    assert profile.language == "en"
    assert profile.skill_type == "generic"
    assert profile.domain_interests == []
    assert profile.company_stage_prefs == []


def test_parse_empty_returns_all_defaults():
    profile = parse_profile_md(EMPTY_PROFILE)
    assert isinstance(profile, CandidateProfile)
    assert profile.skill_type == "pm"
    assert profile.language == "ru"
    assert profile.domain_interests == []
    assert profile.company_stage_prefs == []


def test_parse_never_raises_on_garbage():
    # Must not raise under any circumstances
    result = parse_profile_md("!!!! \x00 random garbage \n```")
    assert isinstance(result, CandidateProfile)


# ── CandidateProfile.phase1_context ──────────────────────────────────────────


def test_phase1_context_is_valid_json():
    profile = parse_profile_md(PROFILE_SNIPPET)
    ctx = profile.phase1_context()
    parsed = json.loads(ctx)
    assert "domain_interests" in parsed
    assert "company_stage_prefs" in parsed


def test_phase1_context_contains_domain_interests():
    profile = parse_profile_md(PROFILE_SNIPPET)
    ctx = profile.phase1_context()
    assert "AI / ML" in ctx
    assert "fintech" in ctx


def test_phase1_context_empty_profile():
    profile = CandidateProfile()
    ctx = profile.phase1_context()
    parsed = json.loads(ctx)
    assert parsed["domain_interests"] == []
    assert parsed["company_stage_prefs"] == []


# ── Integration: parse real PROFILE.md if available ──────────────────────────


@pytest.mark.skipif(
    not (Path(__file__).parent.parent / "skill" / "users" / "1" / "PROFILE.md").exists(),
    reason="PROFILE.md not present in this environment",
)
def test_parse_real_profile_md():
    profile_path = Path(__file__).parent.parent / "skill" / "users" / "1" / "PROFILE.md"
    from core.profile_loader import load_and_parse
    profile = load_and_parse(profile_path)
    assert profile.skill_type == "pm"
    assert profile.language == "ru"
    assert len(profile.domain_interests) > 0
    assert len(profile.company_stage_prefs) > 0
    # Serialise → deserialise round-trip
    data = json.loads(profile.model_dump_json())
    restored = CandidateProfile(**data)
    assert restored == profile
