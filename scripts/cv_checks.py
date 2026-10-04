"""Run every mechanical Phase 3.5 check on a CV draft in one command.

    python scripts/cv_checks.py --cv "<path to CV.md>" --jd "<path to JD.md>"

Wraps the functions in core/cv_metrics.py so local `/analyze` runs do not have
to hand-roll one `python -c` per check. Output is forced to UTF-8 (the tables
contain emoji and crash a Windows cp1252 console) and the two frequency lists
are always passed to format_freq_table in (jd, cv) order.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.cv_metrics import (  # noqa: E402
    detect_jd_echo,
    detect_mechanical_violations,
    detect_phrase_repetition,
    detect_repetition,
    format_freq_table,
    format_tools_table,
    scan_tools,
    top_n_words,
)


def build_report(cv_text: str, jd_text: str) -> str:
    """Return the full plain-text report for one CV draft against its JD."""
    mech = detect_mechanical_violations(cv_text)
    mech_hits = {k: v for k, v in mech.items() if v}
    lines: list[str] = []

    lines.append("## Mechanical violations (em-dash, banned phrases)")
    lines.append(str(mech_hits) if mech_hits else "clean")

    lines.append("")
    lines.append("## Repeated terms (3+ occurrences)")
    lines.append(", ".join(detect_repetition(cv_text)) or "none")

    lines.append("")
    lines.append("## Repeated phrases (2+ occurrences)")
    phrases = detect_phrase_repetition(cv_text)
    lines.append("\n".join(f"{p!r} x{n}" for p, n in phrases) if phrases else "none")

    lines.append("")
    lines.append("## JD echo (CV phrases lifted from the JD)")
    echo = detect_jd_echo(cv_text, jd_text)
    lines.append(", ".join(echo) if echo else "none")

    lines.append("")
    lines.append("## Top-15 word frequency")
    lines.append(format_freq_table(top_n_words(jd_text), top_n_words(cv_text)))

    lines.append("")
    lines.append("## Tools and technologies")
    lines.append(format_tools_table(scan_tools(jd_text, cv_text)))

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cv", required=True, help="path to the CV draft (.md)")
    parser.add_argument("--jd", required=True, help="path to the vacancy JD.md")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    cv_text = Path(args.cv).read_text(encoding="utf-8")
    jd_text = Path(args.jd).read_text(encoding="utf-8")
    print(build_report(cv_text, jd_text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
