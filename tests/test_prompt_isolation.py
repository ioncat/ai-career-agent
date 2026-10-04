"""Leak lint: the engine files (`prompts/`, `skill/SKILL.md`, `.claude/commands/`) must not carry one candidate's personal data.

Facts, URLs, names and company names belong to the profile (`skill/users/*/PROFILE.md`),
never to the working prompts. A second user would otherwise receive the first user's
portfolio link or employer names in their CV.

Two layers, so the test is useful even on a fresh clone where profiles (gitignored) are absent:
- static: patterns that are never legitimate in a prompt (emails, personal profile URLs);
- dynamic: entities extracted from every local profile (person name, employers, personal URLs).
  Skipped when no profile exists.

Vacancy numbers ("found live on vacancy #1577") are provenance, not behaviour, and are allowed.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_PROMPTS = _ROOT / "prompts"
_PROFILES = sorted((_ROOT / "skill" / "users").glob("*/PROFILE.md"))

_STATIC_PATTERNS = {
    "email address": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "personal github.io page": re.compile(r"[A-Za-z0-9-]+\.github\.io"),
    "linkedin profile URL": re.compile(r"linkedin\.com/in/", re.I),
    "telegram handle URL": re.compile(r"\bt\.me/[A-Za-z0-9_]+", re.I),
}

_GENERIC_HEADINGS = {"independent", "personal", "cross-role", "freelance"}


def _prompt_files() -> list[Path]:
    """Every file that steers the pipeline for ALL users: prompts, the skill file, slash commands."""
    files = list(_PROMPTS.rglob("*.md"))
    files.append(_ROOT / "skill" / "SKILL.md")
    files.extend((_ROOT / ".claude" / "commands").glob("*.md"))
    return sorted(f for f in files if f.exists())


def extract_profile_entities(profile_text: str) -> dict[str, set[str]]:
    """Pull the strings that identify one candidate out of a profile's text."""
    entities: dict[str, set[str]] = {"name": set(), "employer": set(), "url": set()}

    m = re.match(r"#\s*([^\n—-]+?)\s*(?:[—-]\s*Profile)?\s*$", profile_text.splitlines()[0]) if profile_text.strip() else None
    if m and " " in m.group(1).strip():
        entities["name"].add(m.group(1).strip())
    variants = re.search(r"^### Name variants\b.*?(?=^##|\Z)", profile_text, re.M | re.S)
    if variants:
        for nm in re.findall(r"^- \*\*([^*]+?)\*\*", variants.group(0), re.M):
            nm = nm.strip()
            if 1 < len(nm.split()) <= 4:
                entities["name"].add(nm)

    for full in list(entities["name"]):
        for part in full.split():
            if len(part) >= 4:
                entities["name"].add(part)

    exp = re.search(r"^## [A-Z]\. Experience\b.*?(?=^## |\Z)", profile_text, re.M | re.S)
    if exp:
        for h in re.findall(r"^### (.+)$", exp.group(0), re.M):
            first = re.split(r"\s+[—-]\s+", h.strip())[0]
            first = re.sub(r"\.com$", "", first, flags=re.I)
            if " " in first or "/" in first or len(first) < 5:
                continue
            if first.lower() in _GENERIC_HEADINGS:
                continue
            entities["employer"].add(first)

    for url in re.findall(r"https?://[^\s)\]>`'\"]+", profile_text):
        bare = re.sub(r"^https?://", "", url).rstrip("/.,;")
        if "/" in bare or bare.count(".") >= 2:
            entities["url"].add(bare)
    for em in re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", profile_text):
        entities["url"].add(em)
    return entities


def test_extractor_finds_name_employer_and_url():
    sample = (
        "# John Doe — Profile\n\n### Name variants\n\n**English CV:**\n- **Johnny Doe** — informal\n\n"
        "## D. Experience\n\n### Independent / Project-based\ntext\n\n"
        "### AcmeCorp\ntext\n\n### Globex.com — Product Manager\ntext\n\n## E. Skills\n"
        "[site](https://janedoe.github.io/) [mail](mailto:jane@example.com)\n"
    )
    ent = extract_profile_entities(sample)
    assert ent["name"] == {"John Doe", "Johnny Doe", "John", "Johnny"}
    assert ent["employer"] == {"AcmeCorp", "Globex"}
    assert "janedoe.github.io" in ent["url"]
    assert "jane@example.com" in ent["url"]


@pytest.mark.parametrize("label,pattern", list(_STATIC_PATTERNS.items()))
def test_prompts_have_no_personal_contact_data(label, pattern):
    hits = []
    for f in _prompt_files():
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{f.relative_to(_ROOT)}:{i}")
    assert not hits, f"{label} found in engine prompts (belongs in the profile): {hits}"


@pytest.mark.skipif(not _PROFILES, reason="no local profile to derive candidate entities from")
def test_prompts_do_not_name_any_profile_entity():
    leaks: list[str] = []
    for profile in _PROFILES:
        ent = extract_profile_entities(profile.read_text(encoding="utf-8"))
        needles = ent["name"] | ent["employer"] | ent["url"]
        for f in _prompt_files():
            text = f.read_text(encoding="utf-8")
            for needle in needles:
                if re.search(r"(?<![A-Za-z0-9])" + re.escape(needle) + r"(?![A-Za-z0-9])", text):
                    leaks.append(f"{f.relative_to(_ROOT)} mentions '{needle}' (from {profile.parent.name}/PROFILE.md)")
    assert not leaks, "candidate-specific content in engine prompts:\n" + "\n".join(leaks)
