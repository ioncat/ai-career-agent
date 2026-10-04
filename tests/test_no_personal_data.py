"""Tracked files must not carry personal identifiers.

The repository is public. Real Telegram chat ids reached `.env.example` once (2026-09) and
stayed in history until a manual cleanup. This scans every git-tracked text file for the
identifier shapes that must never be committed: long numeric chat ids, e-mail addresses
outside a short list of fixture domains, and phone numbers. Person names are covered
separately (`tests/test_prompt_isolation.py` for the engine prompts).

Fixtures and examples use obviously fake values (6-digit chat ids, `a@b.com`, `example.org`).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent

# Real Telegram user ids have 8-10 digits; test fixtures here use 6.
_CHAT_ID = re.compile(r"chat_?id[\"' ]*[:=)\"' ]*-?\d{8,}", re.I)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})")
_PHONE = re.compile(r"(?<!\d)\+?\(?380\)?[ -]?\d{2}[ -]?\d{3}[ -]?\d{2}[ -]?\d{2}(?!\d)")

_FAKE_EMAIL_DOMAINS = {
    "example.com", "example.org", "example.net", "b.com", "bar.com", "y.com", "test.com",
    "users.noreply.github.com", "anthropic.com",
}

_SELF = Path(__file__).name
_TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini", ".env",
    ".example", ".sql", ".html", ".css", ".js", ".dart", ".sh", ".bat", ".ps1", ".gitignore",
}


def _tracked_text_files() -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"], cwd=_ROOT, capture_output=True, check=True,
        ).stdout.decode("utf-8", "replace")
    except (OSError, subprocess.CalledProcessError):
        return []
    files = []
    for rel in filter(None, out.split("\0")):
        path = _ROOT / rel
        if path.name == _SELF or not path.is_file():
            continue
        if path.suffix.lower() in _TEXT_SUFFIXES or path.name.startswith(".env"):
            files.append(path)
    return files


_FILES = _tracked_text_files()


def _findings(text: str) -> list[str]:
    found = [f"chat id: {m.group(0)}" for m in _CHAT_ID.finditer(text)]
    found += [
        f"email: {m.group(0)}" for m in _EMAIL.finditer(text)
        if m.group(1).lower() not in _FAKE_EMAIL_DOMAINS
    ]
    found += [f"phone: {m.group(0)}" for m in _PHONE.finditer(text)]
    return found


def test_scanner_flags_each_shape_and_ignores_fixtures():
    assert _findings("telegram_chat_id=1234567890")
    assert _findings("chat_id: 98765432")
    assert _findings("write to someone@real-company.io")
    assert _findings("call +380 50 123 45 67")
    assert not _findings("telegram_chat_id=123456 and a@b.com and me@example.org")


@pytest.mark.skipif(not _FILES, reason="not a git checkout")
def test_tracked_files_hold_no_personal_identifiers():
    leaks = {}
    for path in _FILES:
        hits = _findings(path.read_text(encoding="utf-8", errors="replace"))
        if hits:
            leaks[str(path.relative_to(_ROOT))] = hits[:3]
    assert not leaks, f"personal identifiers in tracked files: {leaks}"
