"""
tests/test_no_local_paths.py - no absolute path of anybody's machine in a tracked file.

A script once carried the owner's own drive path as a default. The repo is public, so tracked code, tests and
config must use paths relative to the repo (resolved from `__file__`) or an environment variable. Documents
are checked by the project's personal-data test.
"""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# a drive path into a user folder or the owner's workspace; assembled from pieces so this file does not match itself
_DRIVE = "[A-Za-z]:"
_PATH = re.compile(_DRIVE + r"[\\/]+(?:Users|users|My files|Documents and Settings)\b")
_CODE_SUFFIXES = {".py", ".dart", ".yaml", ".yml", ".json", ".toml", ".sql", ".sh", ".bat", ".ps1", ".ini", ".cfg"}


def _tracked_files():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, check=True, text=True,
                             encoding="utf-8").stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout (a clean export has no tracked-file list)")
    return [ROOT / line for line in out.splitlines() if line.strip()]


def test_no_tracked_code_or_config_file_holds_an_absolute_local_path():
    offenders = []
    for path in _tracked_files():
        if path.suffix not in _CODE_SUFFIXES or path.name == Path(__file__).name or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if _PATH.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{number}")
    assert offenders == []


def _load_import_seen_jobs(monkeypatch, env_value):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: None)     # the machine's own .env must not leak in
    if env_value is None:
        monkeypatch.delenv("JOB_BOARD_MONITOR_SEEN_JOBS", raising=False)
    else:
        monkeypatch.setenv("JOB_BOARD_MONITOR_SEEN_JOBS", env_value)
    spec = importlib.util.spec_from_file_location("import_seen_jobs_under_test", ROOT / "scripts" / "import_seen_jobs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_seen_jobs_default_is_the_sibling_folder_of_the_repo(monkeypatch):
    module = _load_import_seen_jobs(monkeypatch, None)

    assert module._DEFAULT_SEEN_JOBS == ROOT.parent / "job-board-monitor" / "seen_jobs.json"


def test_the_seen_jobs_path_can_come_from_the_environment(monkeypatch, tmp_path):
    custom = tmp_path / "seen_jobs.json"

    module = _load_import_seen_jobs(monkeypatch, str(custom))

    assert module._DEFAULT_SEEN_JOBS == custom
