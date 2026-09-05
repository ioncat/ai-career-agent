"""
tools/cv_prefilter.py — Critical Blocker pre-filter (EPIC-27).

Runs right after a vacancy is fetched, before Phase 1+2. Cheap, advisory-only check:
does the JD contain an explicit hard requirement conflicting with the candidate's
## Critical Blockers (PROFILE.md)? Never blocks the pipeline — just flags the
vacancy so the user can decide whether to bother reviewing it.

Fail-open: any error (LLM unreachable, timeout, unparseable output) is treated as
"no blockers found" and logged, never surfaced as a false blocker.

Tool registered in agent.py via ToolRegistry.
Receives shared dependencies via RunContext[AgentDeps].
"""

import asyncio
import logging
import re
import time
from pathlib import Path

from pydantic_ai import RunContext

from core.deps import AgentDeps
from core.llm_client import LLMUnavailableError
from core.vacancy_tags import classify as classify_tags
from db import database

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

_BLOCKED_RE = re.compile(r"(?im)^BLOCKED:\s*(yes|no)\s*$")
_REASON_RE = re.compile(r"(?m)^-\s*(.+)$")

# Mirrors the fit-list in PROFILE.md's `title:` Critical Blockers line. Kept
# here (not read from PROFILE.md) because this is a deterministic code path,
# not a prompt — see docs/discovery/prefilter-local-model-selection.md
# (2026-07-23): letting an LLM judge a literal substring match against ~9
# known terms produced errors an LLM should never make ("Product Owner Lead"
# flagged despite containing "Product Owner") because the title verdict got
# blended with unrelated JD-body signal (domain, seniority) in the same call.
_TITLE_ALLOWLIST = [
    "product manager",
    "product owner",
    "project manager",
    "delivery manager",
    "program manager",
    "business analyst",
    "operations manager",
    "technical product manager",
    "technical project manager",
]

# A word immediately BEFORE a matched allowlist term that changes the actual
# function of the role, not just its domain/platform — "Growth Product
# Manager" contains "Product Manager" as a literal substring but is a
# distinct discipline (growth marketing), same reason the candidate flagged
# it as its own denylist item before the allowlist rewrite. Found 2026-07-23
# via a 50-vacancy audit (#779 "Growth Product Manager (iGaming)" — real
# mismatch, wrongly passed by substring-only matching). A word AFTER the
# term (iGaming, Mobile, Adtech, in parens or after a dash) is a domain
# modifier, not a function modifier — #776 "Product Manager (iGaming)" is a
# genuine fit, iGaming there says nothing about the role's function.
_TITLE_PREFIX_DENYLIST = {
    "growth", "crm", "retention", "marketing", "sales", "bizdev",
    "risk", "compliance", "antifraud", "gamification", "community", "smm",
    "vip", "payment", "payments", "ppc",
}

_WORD_RE = re.compile(r"[a-z]+")


def _check_title_allowlist(title: str) -> str | None:
    """Deterministic pre-check: does the vacancy title contain one of the
    candidate's fit-list terms, without a function-changing prefix directly
    in front of it? Returns None if it fits (proceed to the LLM content
    check), or a reason string if it's a mismatch (short-circuit, never call
    the LLM).
    """
    if not title:
        return None
    low = title.lower()
    for term in _TITLE_ALLOWLIST:
        idx = low.find(term)
        if idx == -1:
            continue
        preceding_words = _WORD_RE.findall(low[:idx])
        if preceding_words and preceding_words[-1] in _TITLE_PREFIX_DENYLIST:
            continue  # substring matched, but a function-changing prefix sits right before it — keep scanning other terms
        return None
    return f'title: "{title.strip()}" does not contain a fitting role term (Product Manager/Owner, Project/Delivery/Program Manager, Business Analyst, Operations Manager, Technical Product/Project Manager)'


# Fast-path for the `domain`/`igaming` Critical Blockers — NOT a new blocker
# category, same verdict the LLM would reach reading the JD body, caught
# earlier (and for free) on the ~common cases where the title names the
# domain outright (usually a parenthetical suffix: "Product Manager
# (iGaming)", "Product Manager (Mobile Apps)"). Kept deliberately small per
# user's explicit call (2026-07-23) — not meant to replace the LLM's JD-body
# read for domain signal, just skip the round-trip when the title already
# gives it away. Unlike `title:`, `domain`/`igaming` stay in what the LLM
# sees too (`_extract_critical_blockers` doesn't strip them) — a title
# without the domain in it still needs the LLM to catch it from the body.
_TITLE_DOMAIN_DENYLIST = {
    "igaming": "igaming",
    "gambling": "igaming",
    "betting": "igaming",
    "casino": "igaming",
    "mobile": "domain",
}


def _check_title_domain_signals(title: str) -> str | None:
    """Deterministic pre-check: does the title itself name a blocked domain
    (iGaming, Mobile)? Returns None if clean (or ambiguous — let the LLM
    decide from the JD body), or a reason string to short-circuit on.
    """
    if not title:
        return None
    low = title.lower()
    for term, category in _TITLE_DOMAIN_DENYLIST.items():
        if term in low:
            return f'{category}: title "{title.strip()}" names the domain directly'
    return None


# Djinni's own "Vacancy Requirements" sidebar (structured, poster-set,
# unauthenticated — merged into JD.md by services/parser as of 2026-08-11,
# see BACKLOG.md) states the required English level in a consistent format
# ("Англійська B1 – Середній" / "English B1 – Intermediate") regardless of
# whether the JD body prose ever mentions it at all — confirmed on vacancy
# #1120, whose body had zero occurrences of "English" despite structurally
# requiring B1. Scoped to search ONLY the merged "## Vacancy Requirements"
# section (not the whole JD) so a casual JD-body mention ("English-speaking
# clients") can never trigger a false blocker — only Djinni's own configured
# hard requirement field can.
_CEFR_ORDER = ["A1", "A2", "B1", "B2", "C1", "C2"]
_CEFR_RANK = {level: i for i, level in enumerate(_CEFR_ORDER)}

# Mirrors PROFILE.md's Critical Blockers `english:` line ("... required
# (mine: B2/Upper-Intermediate)") — hardcoded here rather than parsed from
# PROFILE.md at runtime, same rationale as _TITLE_ALLOWLIST above: this is a
# deterministic code path, not a prompt for an LLM to read.
_CANDIDATE_ENGLISH_LEVEL = "B2"

_REQUIREMENTS_SECTION_RE = re.compile(r"##\s*Vacancy Requirements")
_LANGUAGE_LEVEL_RE = re.compile(
    r"(?:Англійська|English)\D{0,20}?\b(A1|A2|B1|B2|C1|C2)\b", re.IGNORECASE
)


def _check_english_level_sidebar(jd_text: str) -> str | None:
    """Deterministic pre-check: does Djinni's structured requirements sidebar
    (merged into JD.md under "## Vacancy Requirements") require an English
    level above the candidate's? Returns None if clean, absent, or unparseable
    (fail-open — never a false blocker), or a reason string to short-circuit on.
    """
    m = _REQUIREMENTS_SECTION_RE.search(jd_text)
    if not m:
        return None
    section = jd_text[m.end():]
    level_match = _LANGUAGE_LEVEL_RE.search(section)
    if not level_match:
        return None
    required = level_match.group(1).upper()
    if required not in _CEFR_RANK:
        return None
    if _CEFR_RANK[required] <= _CEFR_RANK[_CANDIDATE_ENGLISH_LEVEL]:
        return None
    return f"english: JD requires {required}, candidate is {_CANDIDATE_ENGLISH_LEVEL}"


# Body-prose English-level check (2026-09-04) — extends the Djinni-sidebar-only
# check above to non-Djinni sources (DOU never has a "## Vacancy Requirements"
# sidebar at all — confirmed missing on vacancy #1461, "English at Advanced
# (C1) level or higher" sat only in the JD body, and Stage 2 (LLM) had
# already run on that same vacancy and missed it too — same
# unreliable-on-explicit-text pattern documented for the mobile domain check
# above).
#
# docs/discovery/prefilter-content-stage-regex-idea.md (2026-07-25) flagged
# `english` as "borderline" for a naive regex — real risk demonstrated
# 2026-07-23 (CHANGELOG) was a Responsibilities-bullet ("run A/B tests") being
# misread as a Requirements-bullet ("hands-on A/B testing required"). Solved
# here with a section-boundary parser (the exact deterministic fix that
# discovery doc says the LLM-only categories still need): only text between a
# "Requirements"-shaped heading and the next heading is scanned, so a language
# mention anywhere else in the JD (Responsibilities, About Us, Nice to Have)
# can never match. A soft-requirement word on the same line ("plus", "nice to
# have", "ideally", "буде плюсом") still excludes it even inside that section,
# since "Requirements" sections sometimes end with a soft ask.
_REQUIREMENTS_HEADING_RE = re.compile(
    r"(?im)^#{1,6}\s*(?:requirements?|must.?have|what (?:you.ll need|we.re looking for)|"
    r"вимоги|необхідні? навички|необхідно|обов.язков\w*|требовани\w*)\s*$"
)
_NEXT_HEADING_RE = re.compile(r"(?m)^#{1,6}\s+\S")
_ENGLISH_WORD_RE = re.compile(r"english|англ[іi]йськ\w*|английск\w*", re.IGNORECASE)
_SOFT_REQUIREMENT_RE = re.compile(
    r"\bplus\b|nice.to.have|\bbonus\b|preferred|advantage|desirable|ideally|"
    r"would be an?\b|перевагою|буде плюсом|бажано|приветствується|приветствуется|"
    r"преимуществом",
    re.IGNORECASE,
)
_LEVEL_WORD_TO_CEFR = {
    "native": "C2",
    "fluent": "C2",
    # "proficient"/"proficiency" deliberately excluded (2026-09-04) — too
    # ambiguous, confirmed live: #658 "Working proficiency in English" and
    # #1287 "English proficiency at Intermediate level or higher" both use
    # the word to describe a level well BELOW C2 ("working"/"intermediate"
    # qualifies it down), the opposite of what the bare word suggests.
    "advanced": "C1",
    "upper-intermediate": "B2",
    "upper intermediate": "B2",
}
_LEVEL_WORD_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in _LEVEL_WORD_TO_CEFR) + r")\b", re.IGNORECASE
)


def _extract_requirements_section(jd_text: str) -> str | None:
    """Return the text between a Requirements-shaped heading and the next
    markdown heading, or None if no such heading is found — the same
    section-boundary technique that fixed the LLM's Responsibilities-vs-
    Requirements confusion (2026-07-23 CHANGELOG), applied deterministically.
    """
    m = _REQUIREMENTS_HEADING_RE.search(jd_text)
    if not m:
        return None
    start = m.end()
    next_m = _NEXT_HEADING_RE.search(jd_text, start)
    end = next_m.start() if next_m else len(jd_text)
    return jd_text[start:end]


def _check_english_level_body(jd_text: str) -> str | None:
    """Deterministic pre-check: does the JD body's own Requirements section
    (not Djinni's structured sidebar) state an English level above the
    candidate's? Scoped to that section only, and to lines free of a
    soft-requirement word — see module comment above for why. Returns None if
    clean, absent, or unparseable (fail-open), or a reason string to flag.
    """
    section = _extract_requirements_section(jd_text)
    if not section:
        return None
    for line in section.splitlines():
        if not _ENGLISH_WORD_RE.search(line):
            continue
        if _SOFT_REQUIREMENT_RE.search(line):
            continue
        code_match = re.search(r"\b(A1|A2|B1|B2|C1|C2)\b", line)
        if code_match:
            required = code_match.group(1).upper()
        else:
            word_match = _LEVEL_WORD_RE.search(line)
            if not word_match:
                continue
            required = _LEVEL_WORD_TO_CEFR[word_match.group(1).lower()]
        if _CEFR_RANK[required] <= _CEFR_RANK[_CANDIDATE_ENGLISH_LEVEL]:
            continue
        snippet = line.strip()[:100]
        return f"english: JD Requirements section requires {required} ({snippet!r}), candidate is {_CANDIDATE_ENGLISH_LEVEL}"
    return None


def _check_english_level(jd_text: str) -> str | None:
    """Combined deterministic English-level check — Djinni sidebar first
    (highest confidence, poster-configured field), then the JD body's own
    Requirements section as a fallback for sources without a sidebar (DOU).
    """
    return _check_english_level_sidebar(jd_text) or _check_english_level_body(jd_text)


# Same structured sidebar as _check_english_level above, different field:
# the country-list line always sits directly before Djinni's
# "Країни, де розглядаємо кандидатів" / "Countries where we consider
# candidates" label (confirmed across a corpus scan of fetched JD.md files,
# 2026-08-25 — values seen: "Весь світ" / "Весь мир" (no restriction),
# "Україна", "Країни Європи та Україна" (both include the candidate),
# "Країни ЄС", "Канада" (both exclude the candidate — this is the exact case
# that slipped through on vacancy #1060, though that specific vacancy
# predates the sidebar-merge feature entirely, 2026-08-12, so it never had
# this section to check in the first place). Same fail-open contract as
# _check_english_level: absent/unparseable/no-restriction all return None.
_COUNTRY_LIST_RE = re.compile(
    r"\*\*\s*([^*]+?)\s*\*\*\s*\n+\s*"
    r"(?:Країни, де розглядаємо кандидатів|Countries where we consider candidates)",
    re.IGNORECASE,
)
# No-restriction phrasing seen in the wild — checked before requiring an
# explicit Ukraine/Україна mention, so "Весь світ" doesn't false-positive.
_NO_RESTRICTION_WORDS = ("світ", "world", "anywhere")

# Mirrors PROFILE.md's Critical Blockers `location:` line ("must reside in
# EU/Poland/Romania/etc. (I'm in Ukraine)") — hardcoded here for the same
# reason _CANDIDATE_ENGLISH_LEVEL is: deterministic code path, not a prompt.
_CANDIDATE_COUNTRY_WORDS = ("україна", "ukraine")


# Same section, the field one level up from the country line (both are
# nested bullets right before the country label — see _COUNTRY_LIST_RE).
# Observed values (corpus scan, 2026-08-25): "Тільки віддалено" (69 of 84
# samples) is the clean case; the rest list Office and/or Hybrid alongside
# Remote ("Офіс, Віддалена робота, Гібридний формат роботи", "Офіс або
# віддалено", ...). Deliberately simple binary per explicit user instruction
# — anything that isn't bare remote-only is a signal, no attempt yet to rank
# "remote is one of three options" vs "office-or-remote" by severity.
_REMOTE_FORMAT_RE = re.compile(
    r"\*\*\s*([^*]+?)\s*\*\*\s*\n+\s*\*\s*\*\*\s*[^*]+?\s*\*\*\s*\n+\s*"
    r"(?:Країни, де розглядаємо кандидатів|Countries where we consider candidates)",
    re.IGNORECASE,
)
_REMOTE_ONLY_WORDS = ("тільки віддалено", "full remote", "remote only", "fully remote")


def _check_remote_format(jd_text: str) -> str | None:
    """Deterministic pre-check: does Djinni's structured requirements sidebar
    list anything other than remote-only (Office, Hybrid)? Returns None if
    clean, absent, or unparseable (fail-open), or a reason string to flag —
    advisory only, same as the other structured-sidebar checks, not a hard
    decline.
    """
    m = _REQUIREMENTS_SECTION_RE.search(jd_text)
    if not m:
        return None
    section = jd_text[m.end():]
    fmt_match = _REMOTE_FORMAT_RE.search(section)
    if not fmt_match:
        return None
    fmt = fmt_match.group(1).strip()
    low = fmt.lower()
    if any(phrase in low for phrase in _REMOTE_ONLY_WORDS):
        return None
    return f"remote_format: JD lists {fmt!r} (not remote-only)"


def _check_country(jd_text: str) -> str | None:
    """Deterministic pre-check: does Djinni's structured requirements sidebar
    list countries that exclude Ukraine? Returns None if clean, absent, or
    unparseable (fail-open — never a false blocker), or a reason string to
    short-circuit on.
    """
    m = _REQUIREMENTS_SECTION_RE.search(jd_text)
    if not m:
        return None
    section = jd_text[m.end():]
    country_match = _COUNTRY_LIST_RE.search(section)
    if not country_match:
        return None
    countries = country_match.group(1).strip()
    low = countries.lower()
    if any(word in low for word in _NO_RESTRICTION_WORDS):
        return None
    if any(word in low for word in _CANDIDATE_COUNTRY_WORDS):
        return None
    return f"location: JD only considers candidates from {countries!r}, candidate is in Ukraine"


def _parse_prefilter_output(text: str) -> tuple[bool, list[str], bool]:
    """Parse the BLOCKED:/REASONS: format.

    Returns (blocked, reasons, format_ok). format_ok=False means either the
    model's output didn't contain a recognizable "BLOCKED: yes|no" line at all
    — distinct from format_ok=True + blocked=False, which means the model
    correctly followed the format and explicitly said no blocker. Collapsing
    these two into one "no blocker" result is exactly what hid the real bug on
    vacancy #716 (2026-07-17): a small model rambled instead of following the
    format, and the caller had no way to tell "checked, clean" from "couldn't
    parse what it said".

    format_ok is ALSO False when MULTIPLE "BLOCKED:" lines appear — a sign the
    model leaked self-correction into the final output instead of keeping it
    to the hidden reasoning channel (found 2026-07-23, vacancy #725: model
    wrote "BLOCKED: yes" ... "Wait — ... No title conflict" ... "BLOCKED: no").
    The LAST match is used as the verdict (the self-corrected answer is more
    likely the model's real final judgment), but the anomaly is still flagged
    rather than silently treated as a clean run — same principle as the
    single-match case above.
    """
    matches = list(_BLOCKED_RE.finditer(text))
    if not matches:
        return False, [], False
    clean_format = len(matches) == 1
    last = matches[-1]
    if last.group(1).lower() != "yes":
        return False, [], clean_format
    reasons = [r.strip() for r in _REASON_RE.findall(text[last.end():])]
    if not reasons:
        # some models put REASONS before the final BLOCKED line — fall back
        # to scanning the whole text rather than reporting an empty list.
        reasons = [r.strip() for r in _REASON_RE.findall(text)]
    return True, reasons[:5], clean_format


async def apply_title_stage(vacancy_id: int, title: str) -> bool:
    """Run the deterministic title/domain check (Stage 1 — no LLM) and write
    a blocker immediately if it fails. Returns True if a blocker was set.

    Called automatically on vacancy ingestion (RSSWatcher, import-jd) when
    the "Auto-check title" setting is on — see db.database.get_auto_check_title().
    Free and instant, so unlike Stage 2 (the LLM content check, still manual-
    trigger-only) there's no cost/reliability reason to gate it behind a
    per-vacancy button; the setting exists only so the user can turn the
    write off entirely, not to control cost.

    Safe to call again later — `cv_prefilter()` re-runs the same check first
    and short-circuits identically, so there's no risk of a mismatched verdict
    between the automatic write and a later manual "Check blockers" run.
    """
    reason = _check_title_domain_signals(title) or _check_title_allowlist(title)
    if reason is None:
        return False
    log.info("apply_title_stage: v#%d flagged at ingestion (no LLM call): %s", vacancy_id, reason)
    await database.set_vacancy_blocker(
        vacancy_id, True, [reason],
        raw_output=f"BLOCKED: yes\n- {reason}\n(deterministic title check — no LLM call)",
        stage="title",
    )
    return True


async def apply_language_stage(vacancy_id: int, jd_text: str) -> bool:
    """Run the deterministic English-level check (Stage 1 — no LLM) against
    Djinni's structured requirements sidebar and write a blocker if it fails.
    Returns True if a blocker was set.

    Called automatically on vacancy ingestion (RSSWatcher) alongside
    apply_title_stage, only when that check passed clean — same short-circuit
    precedent as cv_prefilter()'s own title-then-content ordering, so a
    blocker write is never overwritten by a second, unrelated deterministic
    check firing right after it.
    """
    reason = _check_english_level(jd_text)
    if reason is None:
        return False
    log.info("apply_language_stage: v#%d flagged at ingestion (no LLM call): %s", vacancy_id, reason)
    await database.set_vacancy_blocker(
        vacancy_id, True, [reason],
        raw_output=f"BLOCKED: yes\n- {reason}\n(deterministic language check — no LLM call)",
        stage="title",
    )
    return True


async def apply_location_stage(vacancy_id: int, jd_text: str) -> bool:
    """Run the deterministic country + remote-format checks (Stage 1 — no
    LLM) against Djinni's structured requirements sidebar and write a blocker
    if either fails. Returns True if a blocker was set.

    Both checks read the same "## Vacancy Requirements" section — bundled
    into one stage/one write (not two separate apply_*_stage calls) so a
    vacancy failing both doesn't have the first write overwritten by the
    second, the same short-circuit concern apply_title_stage's docstring
    describes for title-then-language.

    Called automatically on vacancy ingestion (RSSWatcher) alongside
    apply_title_stage/apply_language_stage, only when neither of those
    already flagged it.
    """
    reasons = [r for r in (_check_country(jd_text), _check_remote_format(jd_text)) if r is not None]
    if not reasons:
        return False
    log.info("apply_location_stage: v#%d flagged at ingestion (no LLM call): %s", vacancy_id, reasons)
    await database.set_vacancy_blocker(
        vacancy_id, True, reasons,
        raw_output="BLOCKED: yes\n" + "\n".join(f"- {r}" for r in reasons)
        + "\n(deterministic location check — no LLM call)",
        stage="title",
    )
    return True


_MOBILE_EXPERIENCE_RE = re.compile(
    r"(?:experience|hands-on|proficiency|background)\w*[^.\n]{0,40}"
    r"(?:mobile app\w*|mobile game\w*|\bios\b|\bandroid\b|мобільн\w*|мобильн\w*)"
    r"|"
    r"(?:mobile app\w*|mobile game\w*|\bios\b|\bandroid\b|мобільн\w*|мобильн\w*)"
    r"[^.\n]{0,40}(?:experience|hands-on)\w*"
    r"|"
    r"досвід\w*[^.\n]{0,40}мобільн\w*|мобільн\w*[^.\n]{0,40}досвід\w*"
    r"|"
    r"опыт\w*[^.\n]{0,40}мобильн\w*|мобильн\w*[^.\n]{0,40}опыт\w*",
    re.IGNORECASE,
)

# Bold-text pseudo-headings ("**Bonus points:**") are just as common as real
# ATX (`#`) headings in fetched JDs, but _REQUIREMENTS_HEADING_RE above only
# recognizes the latter. Found live 2026-09-05, vacancy #1441 (the exact
# vacancy that originally motivated _MOBILE_EXPERIENCE_RE): "Hands-on
# experience with mobile apps for iOS and/or Android" sits under
# "**Bonus points:**", two sections below "**Requirements for a
# Candidate:**" — a real optional nice-to-have the deterministic check
# blocked on anyway, since it never looked at section context at all. The
# matched line itself carries no soft-requirement word (unlike the English
# check's same-line _SOFT_REQUIREMENT_RE scan) — only the heading two lines
# above marks it optional — so this needs an actual nearest-heading lookup.
_ANY_HEADING_RE = re.compile(r"(?im)^(?:#{1,6}\s*(.+?)|\*\*([^*\n]+?)\*\*\s*:?)\s*$")
_BONUS_SECTION_HEADING_RE = re.compile(
    r"bonus|nice.to.have|would be an?\s+(?:advantage|plus)|good to have|optional|"
    r"перевагою|буде\s*плюсом|бажано|додатков\w*|необов.язков\w*|"
    r"будет плюсом|приветствуется|желательно",
    re.IGNORECASE,
)


def _in_bonus_section(text: str, pos: int) -> bool:
    """Does the nearest heading-like line before *pos* (ATX or bold-text
    pseudo-heading — real JDs mix both styles) read as optional/bonus rather
    than a hard requirement? No heading at all before *pos* means don't
    exclude — most of a JD's body sits above its first heading or between
    unrelated ones, and false-negative risk (missing a real requirement)
    matters more here than the reverse.
    """
    heading = None
    for m in _ANY_HEADING_RE.finditer(text, 0, pos):
        heading = m.group(1) or m.group(2)
    return heading is not None and bool(_BONUS_SECTION_HEADING_RE.search(heading))


def _mobile_requirement_match(jd_text: str) -> re.Match | None:
    """_MOBILE_EXPERIENCE_RE match, excluding one that falls under a
    Bonus/Nice-to-have-shaped section — same "check the actual section, not
    just nearby words" principle _check_english_level_body already applies.
    """
    m = _MOBILE_EXPERIENCE_RE.search(jd_text)
    if m and _in_bonus_section(jd_text, m.start()):
        return None
    return m


async def apply_domain_stage(vacancy_id: int, jd_text: str) -> bool:
    """Run the deterministic mobile-domain check (Stage 1 — no LLM) and write
    a blocker if the JD phrases mobile as an actual experience requirement.
    Returns True if a blocker was set.

    PROFILE.md's Critical Blockers list requires mobile app product
    experience the candidate doesn't have ("mobile: mobile app product
    experience required (none)"). Stage 2 (LLM content check) proved
    unreliable at catching this from JD body text — found live 2026-09-02: 2
    of 3 checked mobile-tagged vacancies were misses (#1441: "hands-on
    experience with mobile apps for iOS and/or Android" said BLOCKED: no;
    #725: "практичний досвід роботи з мобільними застосунками" also said
    BLOCKED: no).

    Uses core/vacancy_tags.py's classify() (the same function driving the
    auto-tagging system) as a cheap first gate, but does NOT block on that
    alone — its `ios`/`android` keywords are deliberately unconditional
    (no false-positive context found for the *tag*, see 2026-09-02 cleanup),
    which is fine for "does this company touch mobile" but too broad for
    "does this role require mobile experience": #844 (MacPaw/Setapp) is
    tagged mobile purely from "develops software for macOS and iOS" —
    company-description, not a requirement — and correctly stayed unblocked
    under Stage 2's judgment; blindly reusing the tag as the blocker trigger
    would have wrongly blocked it. `_MOBILE_EXPERIENCE_RE` requires an
    experience/hands-on/proficiency word near the mobile keyword (or the
    Ukrainian/Russian "досвід"/"опыт" equivalents) — present in both real
    misses, absent from #844.

    2026-09-05: `_mobile_requirement_match()` additionally excludes a match
    sitting under a Bonus/Nice-to-have-shaped section — found live on #1441
    itself (the vacancy that motivated this whole check): its mobile mention
    turned out to sit under "**Bonus points:**", not the Requirements
    section, a real optional nice-to-have that had been wrongly blocking it.

    Called automatically on vacancy ingestion (RSSWatcher) alongside
    apply_title_stage/apply_language_stage/apply_location_stage, only when
    none of those already flagged it.
    """
    if "mobile" not in classify_tags(jd_text):
        return False
    text = jd_text.replace("’", "'")
    if not _mobile_requirement_match(text):
        return False
    reason = "mobile: JD requires mobile app product experience (candidate has none)"
    log.info("apply_domain_stage: v#%d flagged at ingestion (no LLM call): %s", vacancy_id, reason)
    await database.set_vacancy_blocker(
        vacancy_id, True, [reason],
        raw_output=f"BLOCKED: yes\n- {reason}\n(deterministic domain check — no LLM call)",
        stage="title",
    )
    return True


async def cv_prefilter(ctx: RunContext[AgentDeps], vacancy_id: int) -> dict:
    """Run the critical blocker pre-filter on a freshly-fetched vacancy.

    Never raises — always returns a result dict describing what happened:
        {"ok": bool, "blocked": bool, "reasons": list[str],
         "raw_output": str | None, "format_ok": bool, "error": str | None,
         "provider_unavailable": bool}
    "ok" distinguishes "we actually got and parsed a real answer" from any
    failure (LLM unreachable, model not found, parse mismatch) — callers that
    want fail-open automatic behavior can just ignore "ok"/"error" and treat
    blocked=False as "don't flag it"; callers debugging the pipeline (the manual
    trigger endpoint) can surface the distinction instead of a misleading "no
    blockers" for a call that never actually ran.
    "provider_unavailable" flags the specific case of "the LLM service itself
    couldn't be reached" (Ollama not running, Claude API down/rate-limited,
    `claude` CLI missing) — every provider already raises the same
    core.llm_client.LLMUnavailableError for this, regardless of which one is
    configured. Distinguishing it from other failures (bad prompt, parse
    mismatch, vacancy not found) lets the UI say something actionable
    ("provider unavailable — check it's running") instead of a generic
    "something went wrong" (found missing 2026-07-17: Ollama being down looked
    identical to any other error).
    """
    log.info("cv_prefilter: vacancy_id=%d", vacancy_id)

    def _fail(error: str, raw_output: str | None = None, provider_unavailable: bool = False) -> dict:
        return {"ok": False, "blocked": False, "reasons": [], "raw_output": raw_output,
                "format_ok": False, "error": error, "provider_unavailable": provider_unavailable}

    vacancy = await database.get_vacancy_by_id(vacancy_id)
    if not vacancy or not vacancy["markdown_path"]:
        log.warning("cv_prefilter: vacancy_id=%d not found or no JD.md — skipping", vacancy_id)
        return _fail("Vacancy not found or has no JD.md")

    jd_path = Path(vacancy["markdown_path"])
    if not jd_path.exists():
        log.warning("cv_prefilter: JD.md not found at %s — skipping", jd_path)
        return _fail(f"JD.md not found at {jd_path}")

    run_id = await database.insert_pipeline_run(vacancy_id, phase="prefilter")

    jd_text = jd_path.read_text(encoding="utf-8")

    title = vacancy["title"] or ""
    check_kind = "title"
    deterministic_reason = _check_title_domain_signals(title) or _check_title_allowlist(title)
    if (
        deterministic_reason is None
        and "mobile" in classify_tags(jd_text)
        and _mobile_requirement_match(jd_text.replace("’", "'"))
    ):
        deterministic_reason = "mobile: JD requires mobile app product experience (candidate has none)"
        check_kind = "domain"
    if deterministic_reason is not None:
        log.info("cv_prefilter: v#%d deterministic match (no LLM call): %s", vacancy_id, deterministic_reason)
        await database.set_vacancy_blocker(
            vacancy_id, True, [deterministic_reason],
            raw_output=f"BLOCKED: yes\n- {deterministic_reason}\n(deterministic {check_kind} check — no LLM call)",
            stage="title",
        )
        await database.update_pipeline_run(run_id, status="done")
        return {
            "ok": True,
            "blocked": True,
            "reasons": [deterministic_reason],
            "raw_output": None,
            "format_ok": True,
            "error": None,
            "provider_unavailable": False,
        }

    skill_dir = _PROMPTS_DIR / ctx.deps.skill_type
    prompt_path = skill_dir / "prefilter.md"
    if not prompt_path.exists():
        prompt_path = _PROMPTS_DIR / "generic" / "prefilter.md"
    prefilter_prompt = prompt_path.read_text(encoding="utf-8")

    await database.update_pipeline_run(run_id, status="running")

    try:
        t0 = time.monotonic()
        llm = await ctx.deps.get_llm("prefilter")
        output = await llm.complete(jd_text, system=prefilter_prompt)
        log.info("cv_prefilter: done — vacancy_id=%d elapsed=%.1fs", vacancy_id, time.monotonic() - t0)
        if u := llm.last_call_usage:
            await database.insert_llm_usage(phase="prefilter", vacancy_id=vacancy_id, user_id=ctx.deps.user_id, **u)
    except asyncio.CancelledError:
        # BaseException, not Exception (Python 3.8+) — `except Exception` below
        # never catches it. Happens when the client disconnects mid-request
        # (closed the app, navigated away) — found the hard way on vacancy #716
        # (2026-07-17): the row sat at status='running' for 3+ hours, forever,
        # because nothing ever recorded the interruption. Record it, then
        # re-raise — swallowing cancellation silently breaks asyncio semantics.
        log.warning("cv_prefilter: cancelled v#%d (client disconnected?)", vacancy_id)
        await database.update_pipeline_run(run_id, status="error", error_message="Cancelled — client disconnected or request interrupted")
        raise
    except LLMUnavailableError as exc:
        # Every provider (Ollama/Claude API/claude CLI) raises this SAME class
        # for "the service itself couldn't be reached" — Ollama not running,
        # Claude API down/rate-limited, claude CLI missing. Distinguished from
        # generic errors so the UI can say something actionable instead of a
        # bare "some error happened" (gap found 2026-07-17).
        err = str(exc)[:500]
        log.warning("cv_prefilter: provider unavailable v#%d: %s", vacancy_id, err)
        await database.update_pipeline_run(run_id, status="error", error_message=err)
        return _fail(err, provider_unavailable=True)
    except Exception as exc:
        # Fail-open for the caller's blocker decision (never a false blocker), but
        # the failure itself is NOT hidden — recorded on pipeline_runs and returned.
        err = str(exc)[:500]
        log.warning("cv_prefilter: failed v#%d (fail-open, no blocker recorded): %s", vacancy_id, err)
        await database.update_pipeline_run(run_id, status="error", error_message=err)
        return _fail(err)

    blocked, reasons, format_ok = _parse_prefilter_output(output)
    await database.set_vacancy_blocker(vacancy_id, blocked, reasons, raw_output=output, stage="content")
    await database.update_pipeline_run(
        run_id,
        status="done" if format_ok else "error",
        error_message=None if format_ok else "Model output didn't match the expected BLOCKED: format",
    )
    log.info(
        "cv_prefilter: v#%d blocked=%s reasons=%d format_ok=%s",
        vacancy_id, blocked, len(reasons), format_ok,
    )
    return {
        "ok": format_ok,
        "blocked": blocked,
        "reasons": reasons,
        "raw_output": output,
        "format_ok": format_ok,
        "error": None if format_ok else "Model output didn't match the expected BLOCKED: format",
        "provider_unavailable": False,
    }
