"""Claude Code PreToolUse hook: show the prompt editing rules before the first prompt edit of a session.

Wiring (local settings file, not tracked): a PreToolUse hook on Edit|Write|MultiEdit|NotebookEdit|Bash|PowerShell
running `python <repo>/scripts/prompt_rules_gate.py`.

Behaviour: when a tool call is about to write to `prompts/`, `skill/SKILL.md` or `.claude/commands/`,
the first such call in a session is blocked (exit 2) and the rules from
`docs/delivery/PROMPT_EDITING_RULES.md` are printed to stderr, which Claude Code hands to the model.
A marker file records that the rules were shown; the retry passes. Anything else passes silently.
Never fails the tool call because of its own error.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_RULES = _ROOT / "docs" / "delivery" / "PROMPT_EDITING_RULES.md"

_FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
_SHELL_TOOLS = {"Bash", "PowerShell"}

_PROTECTED = re.compile(
    r"(^|[/\\])(prompts[/\\]|skill[/\\]SKILL\.md$|\.claude[/\\]commands[/\\])", re.I
)
# A shell command counts only if it names a protected path AND looks like a write.
_PROTECTED_IN_COMMAND = re.compile(r"(prompts[/\\]|skill[/\\]SKILL\.md|\.claude[/\\]commands[/\\])", re.I)
_WRITE_HINT = re.compile(
    r"write_bytes|write_text|open\s*\([^)]*['\"][wa]|\bsed\s+-i|\bperl\s+-i|(?<![\d&-])>{1,2}\s*(?![&=])\S|\btee\b|Set-Content|Add-Content"
    r"|Out-File|\bcp\b|\bmv\b|Copy-Item|Move-Item|Remove-Item|\brm\b|git\s+(checkout|restore|apply|stash)",
    re.I,
)


def targets_protected_path(payload: dict) -> bool:
    """True when the tool call is about to write to a prompt file."""
    tool = payload.get("tool_name", "")
    data = payload.get("tool_input") or {}
    if tool in _FILE_TOOLS:
        path = data.get("file_path") or data.get("notebook_path") or ""
        return bool(_PROTECTED.search(str(path)))
    if tool in _SHELL_TOOLS:
        cmd = str(data.get("command", ""))
        return bool(_PROTECTED_IN_COMMAND.search(cmd) and _WRITE_HINT.search(cmd))
    return False


def _marker(session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "nosession")
    return Path(tempfile.gettempdir()) / f"career_agent_prompt_rules_shown_{safe}"


def decide(payload: dict, marker: Path) -> tuple[int, str]:
    """(exit_code, stderr_message). Exit 2 blocks the call and shows the message to the model."""
    if not targets_protected_path(payload):
        return 0, ""
    if marker.exists():
        return 0, ""
    marker.write_text("shown", encoding="utf-8")
    try:
        rules = _RULES.read_text(encoding="utf-8")
    except OSError:
        rules = f"(rules file missing: {_RULES})"
    return 2, (
        "BLOCKED ONCE: you are about to edit a prompt file. Read the rules below, check your planned wording "
        "against them (rule 1: no candidate content, even reworded; rule 2: no examples drawn from a profile), "
        "then repeat the same call.\n\n" + rules
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        code, message = decide(payload, _marker(str(payload.get("session_id", ""))))
    except Exception:  # never break the tool call because of the gate itself
        return 0
    if message:
        sys.stderr.buffer.write(message.encode("utf-8"))
        sys.stderr.buffer.flush()
    return code


if __name__ == "__main__":
    sys.exit(main())
