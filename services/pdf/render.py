"""
services/pdf/render.py — CV/Cover Markdown → PDF rendering core.

Jinja2 HTML template + weasyprint. Replaces fpdf2 render_md.

Entry points:
    render_to_bytes(markdown_text: str) -> bytes   — for FastAPI /render endpoint
    md_to_pdf(md_path, pdf_path=None)             — for local CLI use

Template selection (auto-detected from content):
    cv.html    — markdown contains "## " (CV section headers)
    cover.html — no "## " (cover letter). Splits at first <hr> into letterhead + body.
                 Cover markdown structure:
                     # Name
                     Headline
                     contacts line
                     ---
                     Dear ... / Hi!
                     [body paragraphs]
                     Name
"""

import os
import re
from pathlib import Path

import markdown as md_lib
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
from weasyprint.text.fonts import FontConfiguration

_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env", override=False)
except ImportError:
    pass

_env_fonts = os.environ.get("CAREER_AGENT_FONTS")
FONT_DIR = Path(_env_fonts.rstrip("/\\")) if _env_fonts else _PROJECT_ROOT / "fonts"

_TEMPLATES_DIR = _SCRIPT_DIR / "templates"
_jinja_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=False)
_cv_template = _jinja_env.get_template("cv.html")
_cover_template = _jinja_env.get_template("cover.html")

_FONT_CONFIG = FontConfiguration()

_HR_RE = re.compile(r"<hr\s*/?>", re.IGNORECASE)

# Header is always: "# Name\nHeadline\ncontacts line\n\n---". Without a blank
# line between headline and contacts, python-markdown merges them into one
# <p> (it only breaks paragraphs on blank lines, not single newlines), so the
# contacts line collapses onto the headline instead of rendering on its own
# line. Confirmed live 2026-09-24, vacancy #1704 — every CV/cover generated
# from a header written without that blank line has this bug. Fixed here
# defensively so it self-heals regardless of whether the source markdown
# remembers the blank line.
_HEADER_GAP_RE = re.compile(r"\A(# .+\n)([^\n]+)\n([^\n]+\n)")


def _ensure_header_blank_line(markdown_text: str) -> str:
    """Insert a blank line between the headline and contacts line under the
    leading H1, if missing, so they render as separate paragraphs."""
    return _HEADER_GAP_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}\n\n{m.group(3)}", markdown_text, count=1)


def _is_cover(markdown_text: str) -> bool:
    return "## " not in markdown_text


def render_to_bytes(markdown_text: str) -> bytes:
    """Render markdown CV/cover/analysis to PDF bytes. Used by FastAPI /render endpoint."""
    markdown_text = _ensure_header_blank_line(markdown_text)
    content_html = md_lib.markdown(markdown_text, extensions=["tables", "extra"])
    font_dir_uri = FONT_DIR.as_uri()

    if _is_cover(markdown_text):
        parts = _HR_RE.split(content_html, maxsplit=1)
        letterhead = parts[0].strip() if len(parts) > 1 else ""
        body = parts[1].strip() if len(parts) > 1 else content_html.strip()
        full_html = _cover_template.render(
            letterhead=letterhead, body=body, font_dir=font_dir_uri
        )
    else:
        full_html = _cv_template.render(content=content_html, font_dir=font_dir_uri)

    return HTML(string=full_html).write_pdf(font_config=_FONT_CONFIG)


def md_to_pdf(md_path: str, pdf_path: str | None = None) -> str:
    """Render a markdown file to PDF on disk. Returns output PDF path."""
    if pdf_path is None:
        pdf_path = os.path.splitext(md_path)[0] + ".pdf"
    pdf_bytes = render_to_bytes(Path(md_path).read_text(encoding="utf-8"))
    Path(pdf_path).write_bytes(pdf_bytes)
    return pdf_path
