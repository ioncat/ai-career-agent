"""The prompt-editing gate hook: blocks the first prompt edit of a session, passes everything else."""
from __future__ import annotations

import pytest

from scripts import prompt_rules_gate as gate


def _edit(path: str, tool: str = "Edit") -> dict:
    return {"tool_name": tool, "tool_input": {"file_path": path}, "session_id": "s1"}


def _shell(cmd: str, tool: str = "Bash") -> dict:
    return {"tool_name": tool, "tool_input": {"command": cmd}, "session_id": "s1"}


@pytest.mark.parametrize(
    "path",
    [
        r"E:\proj\prompts\pm\phase3_cv_draft.md",
        "E:/proj/prompts/pm/phase1_analysis.md",
        "prompts/pm/phase4_cover.md",
        "skill/SKILL.md",
        r"E:\proj\skill\SKILL.md",
        ".claude/commands/analyze.md",
    ],
)
def test_file_edits_to_protected_paths_are_gated(path):
    assert gate.targets_protected_path(_edit(path))
    assert gate.targets_protected_path(_edit(path, tool="Write"))


@pytest.mark.parametrize(
    "path",
    [
        "core/llm_client.py",
        "docs/delivery/CHANGELOG.md",
        "tests/test_prompts_directives_only.py",
        "skill/users/1/PROFILE.md",
        "skill/SKILL_TYPES.md",
    ],
)
def test_other_files_pass(path):
    assert not gate.targets_protected_path(_edit(path))


@pytest.mark.parametrize(
    "cmd",
    [
        "python -c \"import pathlib; pathlib.Path('prompts/pm/x.md').write_bytes(b'')\"",
        "sed -i 's/a/b/' prompts/pm/phase2_fit.md",
        "echo hi >> prompts/pm/phase2_fit.md",
        "cp new.md skill/SKILL.md",
        "git checkout -- prompts/pm",
    ],
)
def test_shell_writes_to_protected_paths_are_gated(cmd):
    assert gate.targets_protected_path(_shell(cmd))
    assert gate.targets_protected_path(_shell(cmd, tool="PowerShell"))


@pytest.mark.parametrize(
    "cmd",
    [
        "grep -n rule prompts/pm/phase3_cv_draft.md",
        "python -m pytest tests/test_prompts_directives_only.py 2>&1 | tail -3",
        "cat skill/SKILL.md",
        "echo hi > notes.txt",
    ],
)
def test_read_only_or_unrelated_shell_commands_pass(cmd):
    assert not gate.targets_protected_path(_shell(cmd))


def test_unrelated_tools_pass():
    assert not gate.targets_protected_path({"tool_name": "Read", "tool_input": {"file_path": "prompts/pm/x.md"}})


def test_first_protected_edit_is_blocked_with_the_rules_and_the_retry_passes(tmp_path):
    marker = tmp_path / "marker"
    code, message = gate.decide(_edit("prompts/pm/phase3_cv_draft.md"), marker)
    assert code == 2
    assert "No candidate content" in message  # the rules text from PROMPT_EDITING_RULES.md
    assert marker.exists()

    code2, message2 = gate.decide(_edit("prompts/pm/phase3_cv_draft.md"), marker)
    assert (code2, message2) == (0, "")


def test_unrelated_call_neither_blocks_nor_burns_the_marker(tmp_path):
    marker = tmp_path / "marker"
    assert gate.decide(_edit("core/llm_client.py"), marker) == (0, "")
    assert not marker.exists()


def test_marker_is_per_session():
    assert gate._marker("a") != gate._marker("b")
