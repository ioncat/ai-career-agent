"""Prompts are instructions to the agent, not a changelog.

A prompt carries directives (plus the short reason that helps in an edge case). It does not
carry where or when a rule was found: vacancy ids, dates, "found live", "confirmed on ...",
quotes from conversations, pointers to discovery docs. That history lives in
`docs/delivery/CHANGELOG.md` and `git log`. Such notes cost tokens on every run and push the
model toward the one case they describe.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"

_HISTORY_MARKERS = [
    (re.compile(r"vacanc(?:y|ies) #\d"), "vacancy id"),
    (re.compile(r"(?<![\w&])#\d{3,4}\b"), "#id"),
    (re.compile(r"\b20\d\d-\d\d-\d\d\b"), "date"),
    (re.compile(r"\b[Ff]ound (?:live|on|in|recurring|missing)\b"), "'found ...'"),
    (re.compile(r"\b[Cc]onfirmed (?:20|on )"), "'confirmed <date>'"),
    (re.compile(r"\b[Cc]larified\b"), "'clarified'"),
    (re.compile(r"\((?:added|tightened|introduced)\b"), "'(added ...)'"),
    (re.compile(r"docs/discovery"), "pointer to a discovery doc"),
]

# Prompt directories already cleaned. A directory joins this list when its cleanup is done.
_CLEANED_DIRS = ["pm", "generic"]
# Placeholder file, not a pipeline prompt: its header may point at the design doc.
_EXEMPT = {"onboarding_interview.md"}

_FILES = sorted(
    f for d in _CLEANED_DIRS for f in (_PROMPTS / d).glob("*.md") if f.name not in _EXEMPT
)


def _findings(text: str) -> list[str]:
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for pattern, label in _HISTORY_MARKERS:
            if pattern.search(line):
                out.append(f"line {lineno}: {label}")
    return out


def test_checker_flags_each_kind_of_history_note():
    assert _findings("Found live on vacancy #123: x")
    assert _findings("Added 2026-09-21 after a run")
    assert _findings("(confirmed 2026-09-23, see docs/discovery/x.md)")
    assert _findings("see `docs/discovery/Tokenomics.md`")
    assert not _findings("Score each requirement once. Use `&#35;` markers verbatim.")


@pytest.mark.parametrize("path", _FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_prompt_holds_directives_not_history(path):
    found = _findings(path.read_text(encoding="utf-8"))
    assert not found, f"{path.name} carries history notes (move them to CHANGELOG): {found[:5]}"
