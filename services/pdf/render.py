"""
services/pdf/render.py — CV/Cover Markdown → PDF rendering core.

Jinja2 HTML template + weasyprint. Replaces fpdf2 render_md.

Entry points:
    render_to_bytes(markdown_text: str) -> bytes   — for FastAPI /render endpoint
    md_to_pdf(md_path, pdf_path=None)             — for local CLI use
"""

import os
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
_template = _jinja_env.get_template("cv.html")

_FONT_CONFIG = FontConfiguration()


def render_to_bytes(markdown_text: str) -> bytes:
    """Render markdown CV/analysis to PDF bytes. Used by FastAPI /render endpoint."""
    content_html = md_lib.markdown(
        markdown_text,
        extensions=["tables", "extra"],
    )
    font_dir_uri = FONT_DIR.as_uri()
    full_html = _template.render(content=content_html, font_dir=font_dir_uri)
    return HTML(string=full_html).write_pdf(font_config=_FONT_CONFIG)


def md_to_pdf(md_path: str, pdf_path: str | None = None) -> str:
    """Render a markdown file to PDF on disk. Returns output PDF path."""
    if pdf_path is None:
        pdf_path = os.path.splitext(md_path)[0] + ".pdf"
    pdf_bytes = render_to_bytes(Path(md_path).read_text(encoding="utf-8"))
    Path(pdf_path).write_bytes(pdf_bytes)
    return pdf_path
