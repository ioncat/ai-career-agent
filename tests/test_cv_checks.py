"""Tests for scripts/cv_checks.py (one-command Phase 3.5 mechanical checks)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.cv_checks import build_report

_ROOT = Path(__file__).resolve().parent.parent

_JD = (
    "We need a Product Manager to own backlog prioritization and stakeholder "
    "alignment for a long-term client project. Scrum and Kanban required."
)
_CV = (
    "# Test Person\nProduct Manager\n\n## SUMMARY\n\n"
    "Product Manager who prioritized the backlog and aligned stakeholders.\n\n"
    "## EXPERIENCE\n\n### Product Manager\nAcme | 2020 - 2023\n\n"
    "Prioritized the backlog and aligned stakeholders across teams.\n"
)


def test_report_has_every_section():
    report = build_report(_CV, _JD)
    for heading in (
        "## Mechanical violations",
        "## Repeated terms",
        "## Repeated phrases",
        "## JD echo",
        "## Top-15 word frequency",
        "## Tools and technologies",
    ):
        assert heading in report


def test_report_flags_em_dash():
    report = build_report(_CV + "A claim — with a dash.\n", _JD)
    assert "em_dash" in report


def test_clean_cv_reports_clean():
    report = build_report(_CV, _JD)
    assert report.split("\n")[1] == "clean"


def test_frequency_table_is_jd_left_cv_right():
    report = build_report(_CV, _JD)
    assert "JD top-15" in report and "CV top-15" in report
    assert report.index("JD top-15") < report.index("CV top-15")


def test_cli_survives_non_utf8_console(tmp_path):
    """The tables contain emoji; a cp1252 console used to crash the old python -c calls."""
    cv = tmp_path / "cv.md"
    jd = tmp_path / "jd.md"
    cv.write_text(_CV, encoding="utf-8")
    jd.write_text(_JD, encoding="utf-8")
    env = {"PYTHONIOENCODING": "cp1252", "PATH": __import__("os").environ.get("PATH", ""),
           "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")}
    proc = subprocess.run(
        [sys.executable, str(_ROOT / "scripts" / "cv_checks.py"), "--cv", str(cv), "--jd", str(jd)],
        capture_output=True, env=env, cwd=_ROOT,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert b"Mechanical violations" in proc.stdout
