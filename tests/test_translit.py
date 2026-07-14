"""tests/test_translit.py — Cyrillic → Latin filename transliteration."""

from core.translit import safe_filename_stem, to_latin


def test_ukrainian_name():
    assert to_latin("Олексій Бондаренко") == "Oleksii Bondarenko"


def test_russian_name():
    assert to_latin("Алексей") == "Aleksei"


def test_latin_passthrough():
    assert to_latin("Alex Bondarenko") == "Alex Bondarenko"


def test_case_preserved():
    assert to_latin("Іван") == "Ivan"
    assert to_latin("ІВАН").startswith("I")


def test_safe_filename_ukrainian():
    """Ukrainian name → Latin, filesystem-safe stem (spaces → underscore)."""
    assert safe_filename_stem("Олексій Бондаренко") == "Oleksii_Bondarenko"


def test_safe_filename_latin():
    assert safe_filename_stem("Alex Bondarenko") == "Alex_Bondarenko"


def test_safe_filename_no_cyrillic_leaks():
    """No Cyrillic character survives into a filename stem."""
    stem = safe_filename_stem("Олексій-Марія Бондаренко")
    assert stem.isascii()
    assert all(c.isalnum() or c in "_-" for c in stem)


def test_safe_filename_never_empty():
    assert safe_filename_stem("") == "CV"
    assert safe_filename_stem("!!!") == "CV"
