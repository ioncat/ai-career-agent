"""
core/vacancy_tags — keyword-based domain/segment classification for vacancies.

Classifies a JD's full text into zero or more market-segment tags (igaming,
deftech, mobile, outsourcing, b2b_saas, studio, fintech). Purely lexical —
no LLM call, cheap enough to run on every fetch.

Taxonomy locked 2026-08-28 after a retroactive analytics pass over the full
vacancy history (see session — "iGaming share" question). AI/ML product was
evaluated and deliberately excluded: too many companies bolt "AI-powered" on
as a trend buzzword, so a keyword match doesn't reliably mean the product
itself is AI. Revisit only with a tighter signal than plain text matching.

Tags here are ADDITIVE to the free-form `tags` column (schema.sql) — never
overwrite a manually-set tag (e.g. a user-assigned one-off label).
"""

import re

# Each pattern is matched case-insensitively against the lowercased JD text.
# \b-wrapped patterns guard against substring false positives (e.g. "ios"
# inside "portfolios").
_TAXONOMY: dict[str, list[str]] = {
    "igaming": [
        "igaming", "gembl", "gambling", "casino", "betting", "sportsbook",
        "crm retention",
    ],
    "deftech": [
        "deftech", "defence", "defense", "military", "miltech", "uav",
        "drone", "оборон", "дрон", "збройн",
    ],
    "mobile": [
        r"\bmobile app", r"\bmobile game", r"\bios\b", r"\bandroid\b",
        "мобільн", "мобильн",
    ],
    "outsourcing": [
        "outsourc", "outstaff", "staff augmentation", "software house",
        "аутсорс", "аутстаф", r"\bagency\b", "consulting firm",
        "client projects", "digital agency", "marketing agency",
        "creative agency", "агенці",
    ],
    "b2b_saas": [
        r"\bsaas\b",
    ],
    "studio": [
        "game studio", "games studio", "gamedev", "game development studio",
        "ігрову студію", "ігрова студія",
    ],
    "fintech": [
        "fintech", "neobank", "crypto exchange", "payment processing",
        "psp integrat", "banking product",
    ],
}

_COMPILED: dict[str, list[re.Pattern]] = {
    cat: [re.compile(p) for p in patterns] for cat, patterns in _TAXONOMY.items()
}

# Tags are non-exclusive by design (a vacancy can genuinely be both igaming
# and studio, or deftech and outsourcing) — see the analytics discussion this
# taxonomy came out of. For a single-owner view (a chart that needs to sum to
# 100%, not overlap), PRIORITY picks one "primary" tag per vacancy without
# discarding the underlying multi-tag data. Order: industry verticals
# (deftech/igaming/fintech/studio, ranked roughly rarest-to-commonest — a
# more specific vertical should win over a broader one) before form-factor
# tags (mobile/b2b_saas, which describe *how* a product is built, not what
# business it's in), with `outsourcing` last as a business-model fallback
# (only becomes primary when no domain vertical matched at all).
PRIORITY: list[str] = [
    "deftech", "igaming", "fintech", "studio", "mobile", "b2b_saas", "outsourcing",
]


def primary_tag(tags: list[str]) -> str | None:
    """Pick one tag from `tags` per PRIORITY order. None if tags is empty."""
    tag_set = set(tags)
    for cat in PRIORITY:
        if cat in tag_set:
            return cat
    return tags[0] if tags else None


def classify(jd_text: str) -> list[str]:
    """Return the list of taxonomy tags whose keywords appear in jd_text.

    jd_text: full JD markdown/plain text, any case. Empty/None input → [].
    """
    if not jd_text:
        return []
    text = jd_text.lower()
    return [cat for cat, patterns in _COMPILED.items() if any(p.search(text) for p in patterns)]


def merge_tags(existing: str | None, auto_tags: list[str]) -> str:
    """Merge auto-classified tags into an existing comma-separated tags string.

    Preserves existing tags (manual or previously auto-assigned) and their
    order; appends any new auto tags not already present. Case-insensitive
    dedup, output keeps first-seen casing.
    """
    current = [t.strip() for t in (existing or "").split(",") if t.strip()]
    current_lower = {t.lower() for t in current}
    for tag in auto_tags:
        if tag.lower() not in current_lower:
            current.append(tag)
            current_lower.add(tag.lower())
    return ",".join(current)
