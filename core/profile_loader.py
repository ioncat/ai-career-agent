"""
core/profile_loader.py — Parse PROFILE.md into a CandidateProfile.

Reads two sections from PROFILE.md:
  ## Settings        → skill_type, language
  ## Vacancy Preferences (yaml block) → domain_interests, company_stage_prefs

Never raises — returns CandidateProfile defaults on parse failure.
"""

import re
from pathlib import Path

from contracts.profile import CandidateProfile


def parse_profile_md(text: str) -> CandidateProfile:
    """Extract structured fields from PROFILE.md text.

    Args:
        text: Full PROFILE.md content.

    Returns:
        CandidateProfile with parsed fields; defaults where fields are absent.
    """
    return CandidateProfile(
        skill_type=_setting(text, "skill_type") or "pm",
        language=_setting(text, "language") or "ru",
        **_vacancy_prefs(text),
    )


def load_and_parse(path: Path) -> CandidateProfile:
    """Read PROFILE.md from disk and return parsed CandidateProfile."""
    return parse_profile_md(path.read_text(encoding="utf-8"))


# ── Internals ─────────────────────────────────────────────────────────────────


def _setting(text: str, key: str) -> str | None:
    """Return first `key: value` from the ## Settings section, or None."""
    m = re.search(r"^##\s+Settings\b(.+?)(?=\n##\s|\Z)", text, re.DOTALL | re.MULTILINE)
    if not m:
        return None
    for match in re.finditer(rf"^{re.escape(key)}:\s*(\S+)", m.group(1), re.MULTILINE):
        return match.group(1)
    return None


def _vacancy_prefs(text: str) -> dict:
    """Return {domain_interests, company_stage_prefs} from ## Vacancy Preferences yaml block."""
    m = re.search(r"^##\s+Vacancy Preferences\b(.+?)(?=\n##\s|\Z)", text, re.DOTALL | re.MULTILINE)
    if not m:
        return {}
    yaml_m = re.search(r"```yaml\s*(.+?)```", m.group(1), re.DOTALL)
    if not yaml_m:
        return {}
    yaml_text = yaml_m.group(1)
    return {
        "domain_interests": _yaml_list(yaml_text, "domain_interests"),
        "company_stage_prefs": _yaml_list(yaml_text, "company_stage_prefs"),
    }


def _yaml_list(yaml_text: str, key: str) -> list[str]:
    """Extract a simple YAML list `key:\\n  - item` into a Python list."""
    m = re.search(rf"^{re.escape(key)}:\s*\n((?:[ \t]+-[^\n]*\n?)*)", yaml_text, re.MULTILINE)
    if not m:
        return []
    return [
        re.sub(r"^\s*-\s*", "", line).strip()
        for line in m.group(1).splitlines()
        if line.strip()
    ]
