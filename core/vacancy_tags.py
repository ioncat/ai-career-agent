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
    # Split strong/weak (2026-08-31, see _DEFTECH_CSR_BOILERPLATE below) —
    # unlike every other category here, deftech keywords collide hard with a
    # boilerplate paragraph that's near-universal in Ukrainian job postings
    # right now regardless of the company's actual business ("we support the
    # armed forces", "we hire military veterans", "we collect drones for
    # charity"). Found live: 5 of 10 vacancies auto-tagged deftech in one
    # applied-history audit were CSR/DEI filler, not actual defense-tech
    # companies (Kiss My Apps — ed-tech, Peiko/Mycredit — volunteering
    # blurbs, 2x Ciklum — "military veterans" hiring statement). A follow-up
    # full-DB audit (2026-08-31, external review) found the fix only closed
    # one of several false-positive classes — 30 of 51 deftech-tagged
    # vacancies were STILL wrong: English HR/EEO boilerplate ("military
    # leave policy", "veterans and active military personnel"), "defense"
    # as a cybersecurity homonym ("cyber defense solutions"), and
    # recruiting/outsourcing agencies naming deftech/miltech as one of
    # several client verticals or a Brave1 hackathon partnership, not their
    # own business. "miltech" moved to weak here — found live as a
    # candidate's listed past-experience domain ("nice to have: experience
    # in the miltech domain") and as a recruiting agency's placement niche,
    # neither describing the posting company's own product.
    "deftech": [
        "deftech", "uav",
    ],
    "mobile": [
        r"\bmobile app", r"\bmobile game", r"\bios\b", r"\bandroid\b",
        "мобільн", "мобильн",
    ],
    # "outsourc"/bare agency excluded here — see _OUTSOURCING_AMBIGUOUS below,
    # 2026-08-30. The multi-word agency phrases here (digital/marketing/
    # creative agency) are specific enough to keep as always-on signals.
    "outsourcing": [
        "outstaff", "staff augmentation", "software house",
        "аутсорс", "аутстаф", "consulting firm",
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

# deftech-only: ambiguous terms that DO describe a real defense-tech product
# when they appear on their own, but are exactly the words the ubiquitous
# CSR/DEI boilerplate paragraph also uses (see _DEFTECH_CSR_BOILERPLATE).
# Counted only when that boilerplate isn't the sole source of the match —
# see classify().
_DEFTECH_WEAK: list[str] = [
    # \b-guarded — "drone" bare matches inside "DroneDeploy" (a construction-
    # tech product name), found live 2026-08-31.
    "defence", "defense", "military", "miltech", r"\bdrone\b", "оборон", "дрон", "збройн",
]

# Every non-deftech context found to trigger the weak list, across two audit
# passes (2026-08-30 internal, 2026-08-31 external review — the first fix
# only closed the first bullet below, leaving 30 of 51 deftech-tagged
# vacancies still wrong). A genuine defense-tech company still matches via
# the _TAXONOMY strong list above, or via a weak keyword used elsewhere in
# the JD outside all of these contexts.
_DEFTECH_CSR_BOILERPLATE = re.compile(
    # Ukrainian charity/CSR paragraph ("we support the armed forces", "we
    # collect drones for charity") — near-universal in current UA postings.
    # Noun-stem patterns (сил\w*, збройн\w*, збира\w*, допомага\w*) absorb
    # Ukrainian case declension (сили/силам, збройні/збройних, etc.) instead
    # of listing every grammatical form.
    r"сил\w*\s*оборони|збройн\w*\s*сил\w*|"
    r"збира\w*.{0,10}дрон|допомага\w*.{0,15}(?:зсу|сил\w*\s*оборони)|"
    r"\bзсу\b|волонтер|"
    # English HR/EEO/DEI boilerplate (military-service employee benefits,
    # non-discrimination clauses, corporate donations) — says nothing about
    # the company's domain.
    r"military veterans?|veterans? and (?:active )?military personnel|"
    r"military (?:leave|reservation|teammates)|committed to our veterans?|"
    r"veteran career|veteran or military status|ukrainian defenders|"
    r"support(?:ing|s)? the military\b|(?:employees?\s+)?serving in the military|"
    r"our military\b|donors? to ukraine'?s? defen[cs]e|the defen[cs]e forces|"
    # "defense"/"defence" as a cybersecurity homonym or a business idiom
    # ("put the client's defense ahead", "a defence against them") — not
    # defense industry at all.
    r"cyber defen[cs]e|defen[cs]e.in.depth|defen[cs]e of (?:concepts|ideas)|"
    r"client'?s? defen[cs]e|defen[cs]e against|"
    # Construction/industrial drone use (site surveying), not a weapons
    # platform.
    r"drone scans?|lidar.{0,20}drone|"
    # Recruiting/outsourcing agency naming deftech/miltech as one of several
    # client verticals, a hackathon partnership, or a candidate's past-
    # experience nice-to-have — not the posting company's own product or
    # this specific role's actual work (contrast: a role actually describing
    # defense-tech client work, e.g. "агенція в MilTech" that then goes on
    # to describe a real defense-tech client's product, still matches).
    r"хакатон\w*[^.]{0,80}brave1|brave1[^.]{0,40}(?:хакатон|об'?єднанн)|"
    r"defensetech об'?єднанн\w*|"
    r"(?:healthcare|telecom|logistics|fintech|edtech)(?:[,\s]+\w+){0,3},?\s+and\s+defen[cs]e|"
    r"(?:the )?miltech domain",
)

_COMPILED: dict[str, list[re.Pattern]] = {
    cat: [re.compile(p) for p in patterns] for cat, patterns in _TAXONOMY.items()
}
_DEFTECH_WEAK_COMPILED: list[re.Pattern] = [re.compile(p) for p in _DEFTECH_WEAK]

# outsourcing-only: bare "agency"/"outsourc" collide with two unrelated
# contexts — a JD contrasting ITSELF against agency/outsourcing work
# ("product company background, vs agency/outsource", "not agency or client
# delivery projects"), and a client-side/vendor mention that says nothing
# about the hiring company itself ("budget buried in agency fees", "law
# agency support through our partner law agency" as an employee benefit).
# Found live 2026-08-30: 6 of 162 outsourcing-tagged vacancies were false
# positives from exactly this. Same strip-then-recheck approach as deftech
# above — a genuine agency/outsourcing company elsewhere in the same text
# still counts.
_OUTSOURCING_AMBIGUOUS = [r"\bagency\b", "outsourc"]
_OUTSOURCING_AMBIGUOUS_COMPILED = [re.compile(p) for p in _OUTSOURCING_AMBIGUOUS]
_OUTSOURCING_FALSE_CONTEXT = re.compile(
    r"(?:\bvs\.?|\bnot\b|instead of|rather than|unlike)\s*[\w/]*\s*"
    r"(?:agency|outsourc\w*)|agency fees|partner\w*\s+\w*\s*agency|"
    r"law agency",
)

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
    # Normalize curly apostrophes (’, U+2019 — common in professionally
    # typeset JD text) to straight ones so every "'?" in the patterns below
    # matches both. Found live 2026-08-31: "client's defense ahead" and
    # "Ukraine's defense forces" silently failed to strip because the
    # exclusion patterns only spelled the ASCII apostrophe.
    text = text.replace("’", "'")
    tags = [cat for cat, patterns in _COMPILED.items() if any(p.search(text) for p in patterns)]
    if "deftech" not in tags:
        # Strong deftech keywords (_TAXONOMY) found nothing — check the weak
        # list, but only against text with the CSR boilerplate stripped out,
        # so that boilerplate alone can never be the reason a vacancy gets
        # tagged deftech.
        stripped = _DEFTECH_CSR_BOILERPLATE.sub(" ", text)
        if any(p.search(stripped) for p in _DEFTECH_WEAK_COMPILED):
            tags.append("deftech")
    if "outsourcing" not in tags:
        # Specific outsourcing phrases (_TAXONOMY) found nothing — check the
        # ambiguous "agency"/"outsourc" keywords, but only against text with
        # the known negation/client-mention contexts stripped out.
        stripped = _OUTSOURCING_FALSE_CONTEXT.sub(" ", text)
        if any(p.search(stripped) for p in _OUTSOURCING_AMBIGUOUS_COMPILED):
            tags.append("outsourcing")
    return tags


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
