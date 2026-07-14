"""
core/translit.py — Cyrillic → Latin transliteration for filenames.

Document filenames must always be Latin ASCII, even for Ukrainian/Russian CVs
(Cyrillic filenames break on some filesystems, cloud sync, and email attachments).
The document *content* stays in its original language — only the filename is
transliterated.

Covers Ukrainian (КМУ 2010 style) + Russian. Unmapped characters are dropped.
"""

import re

# Ukrainian + Russian lowercase → Latin. Uppercase handled by capitalising.
_MAP: dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d",
    "е": "e", "є": "ie", "ж": "zh", "з": "z", "и": "y", "і": "i",
    "ї": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ь": "", "ю": "iu", "я": "ia",
    # Russian-specific
    "ё": "e", "ы": "y", "э": "e", "ъ": "",
}


def to_latin(text: str) -> str:
    """Transliterate Cyrillic to Latin, preserving case. Already-Latin text passes through."""
    out: list[str] = []
    for ch in text:
        lower = ch.lower()
        if lower in _MAP:
            latin = _MAP[lower]
            out.append(latin.capitalize() if ch.isupper() and latin else latin)
        else:
            out.append(ch)
    return "".join(out)


def safe_filename_stem(name: str) -> str:
    """Latin-only, filesystem-safe stem from a candidate name (any language).

    e.g. 'Олексій Бондаренко' → 'Oleksii_Bondarenko', 'Alex Bondarenko' → 'Alex_Bondarenko'.
    """
    latin = to_latin(name)
    stem = re.sub(r"[^\w\-]", "_", latin, flags=re.ASCII)  # ASCII flag: strip any residual non-latin
    stem = re.sub(r"_+", "_", stem).strip("_")
    return stem or "CV"
