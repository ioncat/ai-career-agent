"""Overlap lint: a prompt must not repeat a run of words that stands in a user's own files.

The profile holds one candidate's content; a prompt is an instruction for every candidate
(docs/delivery/PROMPT_EDITING_RULES.md). Paraphrased or lightly reworded profile text slips
past the name/employer lint (test_prompt_isolation.py), but a long verbatim run of words
shared with a profile or interview-prep file still gives it away.

What is compared:
- user side: `skill/users/*/PROFILE*.md` and `INTERVIEW_PREP.md`, WITHOUT the engine-config
  sections (Maintenance Rule, Settings, Generation Rules, Pipeline Config): those hold
  instructions, which legitimately resemble prompt text;
- prompt side: the same files test_prompt_isolation.py lints.

Runs of `_RUN` consecutive words are compared. On a clean clone the user files do not
exist (gitignored) and the real-data test is skipped; the unit tests below always run.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_USERS = _ROOT / "skill" / "users"
_RUN = 10

_CONFIG_SECTION = re.compile(
    r"^##\s+(?:[A-Za-z]\.\s+)?(Maintenance Rule|Settings|Generation Rules|Pipeline Config)\b", re.I
)

# Prompt lines that still overlap a profile on purpose or by an open decision. An entry must
# match a line that really overlaps; a stale entry fails the test so this list only shrinks.
_KNOWN_OPEN: dict[str, str] = {}


def _words(text: str) -> list[str]:
    return re.findall(r"[\w']+", text.lower())


def _runs(words: list[str], n: int = _RUN) -> set[tuple[str, ...]]:
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def candidate_content(text: str) -> str:
    """Profile text without the engine-config sections."""
    kept, skip = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            skip = bool(_CONFIG_SECTION.match(line))
        if not skip:
            kept.append(line)
    return "\n".join(kept)


def overlapping_lines(prompt_text: str, user_runs: set[tuple[str, ...]], n: int = _RUN) -> list[str]:
    """Lines of `prompt_text` that share at least one run of `n` words with `user_runs`."""
    return [ln for ln in prompt_text.splitlines() if _runs(_words(ln), n) & user_runs]


def _prompt_files() -> list[Path]:
    files = list((_ROOT / "prompts" / "pm").rglob("*.md"))
    files.append(_ROOT / "skill" / "SKILL.md")
    files.extend((_ROOT / ".claude" / "commands").glob("*.md"))
    return sorted(f for f in files if f.exists())


def _user_files() -> list[Path]:
    return sorted(
        f for f in _USERS.glob("*/*.md") if f.name.startswith(("PROFILE", "INTERVIEW_PREP"))
    )


# ── unit tests (always run) ───────────────────────────────────────────────────


def test_detects_a_verbatim_run_shared_with_the_profile():
    profile = "## D. Experience\nShe rebuilt the quarterly planning process for the whole regional logistics team in six weeks."
    prompt = "- Rule\n- Mention that she rebuilt the quarterly planning process for the whole regional logistics team."
    user = _runs(_words(candidate_content(profile)))
    assert overlapping_lines(prompt, user) == [
        "- Mention that she rebuilt the quarterly planning process for the whole regional logistics team."
    ]


def test_ignores_short_shared_phrases():
    user = _runs(_words("include only when the JD asks for it and the profile allows it"))
    assert overlapping_lines("Include only when the JD asks for it.", user) == []


def test_engine_config_sections_are_not_compared():
    profile = (
        "## C. Narrative\nNarrative words are compared here as normal words in a sentence.\n"
        "## F. Generation Rules\nAlways open the summary with the plain combined title form every time.\n"
        "## D. Experience\nExperience text goes here."
    )
    kept = candidate_content(profile)
    assert "Narrative words" in kept and "Experience text" in kept
    assert "combined title form" not in kept


def test_known_open_entries_point_at_real_prompt_files():
    for path in _KNOWN_OPEN.values():
        assert (_ROOT / path).exists(), path


# ── real-data test (skipped without local user files) ────────────────────────


@pytest.mark.skipif(not _user_files(), reason="no local user files (clean clone)")
def test_prompts_share_no_long_run_of_words_with_user_files():
    user_runs: set[tuple[str, ...]] = set()
    for f in _user_files():
        user_runs |= _runs(_words(candidate_content(f.read_text(encoding="utf-8"))))

    problems: list[str] = []
    matched_known: set[str] = set()
    for pf in _prompt_files():
        rel = pf.relative_to(_ROOT).as_posix()
        for line in overlapping_lines(pf.read_text(encoding="utf-8"), user_runs):
            known = next((k for k, p in _KNOWN_OPEN.items() if k in line and p == rel), None)
            if known:
                matched_known.add(known)
            else:
                problems.append(f"{rel}: {line.strip()[:140]}")

    stale = sorted(set(_KNOWN_OPEN) - matched_known)
    assert not problems, (
        f"{len(problems)} prompt line(s) repeat {_RUN}+ words from a user file "
        "(see docs/delivery/PROMPT_EDITING_RULES.md, rule 1):\n" + "\n".join(problems)
    )
    assert not stale, f"stale _KNOWN_OPEN entries (no longer overlapping, remove them): {stale}"
