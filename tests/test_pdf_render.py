"""
tests/test_pdf_render.py — unit tests for services/pdf/render.py's header-gap fix.

Regression test for a bug found live 2026-09-24 (vacancy #1704): the standard
CV/cover header ("# Name\nHeadline\ncontacts line\n\n---") merges the headline
and contacts line into one <p> when there's no blank line between them, since
python-markdown only breaks paragraphs on blank lines, not single newlines.
The contacts line then visually collapses onto the headline in the rendered
PDF instead of appearing on its own line.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "pdf"))

from render import _ensure_header_blank_line, render_to_bytes  # noqa: E402


def test_inserts_blank_line_when_missing():
    text = "# Alex Bondarenko\nProduct Owner\n[Email](mailto:a@b.com)\n\n---\n\n## SUMMARY\n"
    result = _ensure_header_blank_line(text)
    assert result == "# Alex Bondarenko\nProduct Owner\n\n[Email](mailto:a@b.com)\n\n---\n\n## SUMMARY\n"


def test_idempotent_when_blank_line_already_present():
    text = "# Alex Bondarenko\nProduct Owner\n\n[Email](mailto:a@b.com)\n\n---\n\n## SUMMARY\n"
    assert _ensure_header_blank_line(text) == text


def test_does_not_touch_text_without_header_pattern():
    text = "Just some text\nwith no heading\n"
    assert _ensure_header_blank_line(text) == text


def test_only_fixes_the_leading_header_not_later_occurrences():
    text = (
        "# Alex Bondarenko\nProduct Owner\n[Email](mailto:a@b.com)\n\n---\n\n"
        "## EXPERIENCE\n\n### Role\nCompany\nJanuary 2020 - Present\n\nDid things.\n"
    )
    result = _ensure_header_blank_line(text)
    assert result.startswith(
        "# Alex Bondarenko\nProduct Owner\n\n[Email](mailto:a@b.com)\n\n---\n"
    )
    # The EXPERIENCE role block's own two-line "Company\nDates" pattern must be untouched.
    assert "### Role\nCompany\nJanuary 2020 - Present\n\nDid things.\n" in result


def test_headline_and_contacts_render_as_separate_paragraphs_after_fix():
    """End-to-end: the actual bug — contacts collapsing onto the headline — must not occur."""
    text = "# Alex Bondarenko\nProduct Owner\n[Email](mailto:a@b.com)\n\n---\n\n## SUMMARY\n\nSome summary text.\n"
    pdf_bytes = render_to_bytes(text)
    assert pdf_bytes[:4] == b"%PDF"
    assert len(pdf_bytes) > 0


# ── CAREER_AGENT_FONTS: a relative value must not break the render ────────────

@pytest.fixture()
def reload_render():
    """Reload render.py after the env var is set; reload again with the env restored."""
    import importlib
    import render

    def _reload():
        return importlib.reload(render)

    yield _reload


def test_relative_fonts_env_becomes_an_absolute_path(monkeypatch, reload_render):
    """The documented command sets CAREER_AGENT_FONTS=fonts/; Path.as_uri() rejects a relative path."""
    monkeypatch.setenv("CAREER_AGENT_FONTS", "fonts/")
    try:
        module = reload_render()
        assert module.FONT_DIR.is_absolute()
        assert module.FONT_DIR.as_uri().startswith("file:///")
    finally:
        monkeypatch.delenv("CAREER_AGENT_FONTS", raising=False)
        reload_render()


def test_default_fonts_dir_is_unchanged_without_the_env_var(monkeypatch, reload_render):
    monkeypatch.delenv("CAREER_AGENT_FONTS", raising=False)
    module = reload_render()
    assert module.FONT_DIR == module._PROJECT_ROOT / "fonts"


def test_render_works_with_a_relative_fonts_env(monkeypatch, reload_render):
    """End to end: the exact command from SKILL.md produces a PDF instead of raising."""
    monkeypatch.setenv("CAREER_AGENT_FONTS", "fonts/")
    monkeypatch.chdir(Path(__file__).parent.parent)
    try:
        module = reload_render()
        pdf = module.render_to_bytes("# Name\nHeadline\n\ncontacts\n\n---\n\n## SUMMARY\n\nText.\n")
        assert pdf.startswith(b"%PDF")
    finally:
        monkeypatch.delenv("CAREER_AGENT_FONTS", raising=False)
        reload_render()
