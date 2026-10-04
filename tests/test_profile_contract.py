"""Contract between the engine files and a candidate profile.

The prompts and `skill/SKILL.md` tell the model to read named sections of the profile
("the profile's Languages entry", "Generation Rules", "Name variants", ...). If a profile
restructure renames or drops one of them, the references silently dangle: the model finds
nothing and guesses. That happened on 2026-09-23 (prompts kept pointing at `## Contacts`
and `## Additional Evidence` after the restructure) and was only found by blind runs.

Two directions are checked:
- every section the engine depends on exists in each local `pm` profile (skipped when no
  such profile is present, e.g. on a fresh clone);
- every section in the contract is actually mentioned by the engine files, so the contract
  list cannot go stale on its own.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent

# name -> (regex that finds it in a profile, phrase the engine files use to refer to it)
PM_PROFILE_CONTRACT: dict[str, tuple[str, str]] = {
    "Settings": (r"^#{2,3} (?:[A-Z]\. )?Settings\b", "Settings section"),
    "Name variants": (r"^#{2,3} Name variants\b", "Name variants"),
    "Contacts line": (r"^\*\*Contacts line", "Contacts line"),
    "Certifications": (r"^#{2,3} Certifications\b", "Certifications section"),
    "Languages": (r"^\*\*Languages:\*\*", "Languages entry"),
    "Archetype & Role Positioning": (r"^#{2,3} Archetype & Role Positioning\b", "Archetype & Role Positioning"),
    "Experience": (r"^## (?:[A-Z]\. )?Experience\b", "Experience"),
    "Generation Rules": (r"^## (?:[A-Z]\. )?Generation Rules\b", "Generation Rules"),
    "CV cutoff year": (r"^#{2,3} CV cutoff year\b", "cutoff"),
    "AI Tooling Paragraph": (r"^#{2,3} AI Tooling Paragraph\b", "AI Tooling Paragraph"),
    "Vacancy Preferences": (r"^#{2,3} Vacancy Preferences\b", "Vacancy Preferences"),
}


def missing_sections(profile_text: str) -> list[str]:
    """Contract sections that a profile does not contain."""
    return [
        name
        for name, (pattern, _) in PM_PROFILE_CONTRACT.items()
        if not re.search(pattern, profile_text, re.M)
    ]


def _engine_text() -> str:
    parts = [f.read_text(encoding="utf-8") for f in (_ROOT / "prompts").rglob("*.md")]
    parts.append((_ROOT / "skill" / "SKILL.md").read_text(encoding="utf-8"))
    return "\n".join(parts)


def _is_pm_profile(text: str) -> bool:
    return re.search(r"^skill_type:\s*pm\b", text, re.M) is not None


_PM_PROFILES = [
    p for p in sorted((_ROOT / "skill" / "users").glob("*/PROFILE.md"))
    if _is_pm_profile(p.read_text(encoding="utf-8"))
]


def test_checker_flags_a_missing_section():
    full = "\n".join(
        {
            "Settings": "## A. Settings\nskill_type: pm",
            "Name variants": "### Name variants",
            "Contacts line": "**Contacts line (copy verbatim)**",
            "Certifications": "### Certifications",
            "Languages": "**Languages:** English",
            "Archetype & Role Positioning": "### Archetype & Role Positioning",
            "Experience": "## D. Experience",
            "Generation Rules": "## F. Generation Rules",
            "CV cutoff year": "### CV cutoff year",
            "AI Tooling Paragraph": "### AI Tooling Paragraph",
            "Vacancy Preferences": "### Vacancy Preferences",
        }.values()
    )
    assert missing_sections(full) == []
    assert missing_sections(full.replace("### Certifications", "### Certs")) == ["Certifications"]


@pytest.mark.parametrize("phrase_key", list(PM_PROFILE_CONTRACT))
def test_engine_mentions_every_contract_section(phrase_key):
    phrase = PM_PROFILE_CONTRACT[phrase_key][1]
    assert phrase in _engine_text(), (
        f"no engine file mentions '{phrase}': drop '{phrase_key}' from the contract or restore the reference"
    )


@pytest.mark.skipif(not _PM_PROFILES, reason="no local pm profile")
@pytest.mark.parametrize("profile", _PM_PROFILES, ids=lambda p: p.parent.name)
def test_pm_profile_has_every_section_the_engine_reads(profile):
    missing = missing_sections(profile.read_text(encoding="utf-8"))
    assert not missing, f"{profile.parent.name}/PROFILE.md lacks sections the engine reads: {missing}"
