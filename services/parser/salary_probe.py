"""
salary_probe.py — Estimate a Djinni vacancy's real (possibly undisclosed)
salary via its own public `salary=N` search filter.

Djinni's salary filter narrows results against the poster's actual number
even for postings whose JD/sidebar shows "not disclosed" — confirmed live
2026-09-05 (GLIG — Product Development Manager, vacancy 846686: present at
salary=3000, gone at salary=8000). This is the user's own manual technique
(raise the filter until the vacancy drops out, the last value it's still
visible at is the real number) turned into code. No login required — unlike
the personalized profile-match panel (see config.py's comment on that one),
this filter is public and anonymous.

Two identification strategies, tried in order:

1. **Company page** (primary) — the user's own actual method: open the
   vacancy, follow its link to the company's own Djinni page
   (`/jobs/company-{slug}/`), apply the salary filter there — also scoped to
   the same PM/PO category feeds.json already ingests on (`_ROLE_FILTER`),
   same as the user's own filter, for a company with postings across many
   unrelated categories. Scoped structurally to that one employer's PM/PO
   postings, so results stay tiny (often a single vacancy) regardless of how
   generic the job title is — confirmed live 2026-09-05 on vacancy #1393
   (bare "Product Manager", Twist Robotics): the company page shows exactly
   1 result at $5000, 0 at $5500. Not foolproof — a large multi-product
   company (Kiss My Apps, vacancy #1431) still exceeded the page cap even
   role-filtered; that vacancy's estimate was confirmed and recorded by
   hand instead. Capped at 1 page regardless — see _COMPANY_PAGE_MAX_PAGES.
2. **Title-only search** (fallback, used when no company profile URL is
   available — e.g. some recruiting-agency postings) — `search_type=title-
   only` keeps result pages small for any reasonably specific title. A bare
   category search returns 200+ results at low salary thresholds, which
   would need dozens of page-fetches per probe just to confirm presence;
   title-only stays within a page or two across the whole salary range.

A query still unresolved within MAX_PAGES_PER_CHECK pages under BOTH
strategies is treated as undeterminable — never guessed from a partial page
scan. `find_salary_ceiling()` also enforces one shared request budget across
BOTH strategies for a single vacancy (2026-09-07, user request) — without it
a vacancy that's genuinely present but never narrows down (a large employer,
or a title landing in that same ambiguous zone under both strategies) could
grind through dozens of throttled requests with no upper bound on time
spent. When the budget runs out — or nothing was ever found at all, or a
request failed outright — the caller gets back a *reason* string alongside
the (then-None) ceiling, so it can leave a short explanatory note instead of
silence (see REASON_* constants).

Every request goes through crawler.fetch(), so it carries the same polite
delay (REQUEST_DELAY_RANGE), retry/backoff, and randomized headers as the
regular JD parser — this was the explicit point of reusing it rather than
writing a separate, unthrottled client for this feature.
"""

import logging
import re
from typing import Callable
from urllib.parse import quote

from crawler import fetch

log = logging.getLogger(__name__)

# User-confirmed experimentally (2026-09-05) — Djinni's own filter snaps to
# $500 increments; anything finer would just re-discover the same steps.
STEP = 500
# Past this, either the vacancy pays unusually well for the PM/PO market or
# something's off — bail rather than hammer the site chasing an outlier.
MAX_SALARY = 20000
# ~45 results (15/page observed). A query still unresolved past this many
# pages is too generic/broad to track reliably — every further page just
# costs a request without moving us closer to a trustworthy answer.
MAX_PAGES_PER_CHECK = 3
# Company pages only ever get 1 page (not MAX_PAGES_PER_CHECK) — found live
# 2026-09-07, vacancy #231 (Influence Pro Services, 4 total postings):
# Djinni's own pagination doesn't return an EMPTY page once a company's real
# results run out — page 2+ silently falls back to an unrelated "recommended
# jobs" listing instead (confirmed: the exact same ~15 job ids appeared on
# page 2 of this company's page AND on page 2 of an unrelated title-only
# search, regardless of query or filter). `_present_at`'s "non-empty page ⇒
# keep paginating" logic can't tell that fallback apart from genuine
# results, so it burned through the whole page cap without ever seeing an
# empty page, discarding an otherwise-correct answer (present at $4500, the
# real ceiling). A company page realistically never has enough PM/PO
# postings to need a second page in the first place, so the safe fix is
# simply never asking Djinni for one. Title-only search shares the same
# underlying site quirk in theory, but its result counts vary widely enough
# that a blanket 1-page cap would cost real recall — flagged as a follow-up,
# not fixed here (BACKLOG).
_COMPANY_PAGE_MAX_PAGES = 1
# Shared across BOTH strategies for one vacancy (2026-09-07) — company-page
# typically resolves in ~8-10 requests (1 baseline + ~4 exponential + ~3-4
# binary, 1 page each); title-only can cost up to 3x that per check since it
# isn't page-capped at 1. 30 covers a realistic full run of company-page
# THEN title-only without either being cut off mid-resolution, while still
# bounding the worst case (a search that never narrows down could otherwise
# run unbounded) to roughly 1-2.5 minutes of throttled requests.
MAX_TOTAL_REQUESTS = 30

# Why find_salary_ceiling() gave up, when it did — lets the caller leave a
# short, honest note instead of silence. Deliberately coarse (3 buckets, not
# one per internal code path) — a caller-facing reason should explain
# roughly *what happened*, not retrace the search's own internals.
REASON_NOT_FOUND = "not_found"
REASON_TOO_MANY_MATCHES = "too_many_matches"
REASON_REQUEST_FAILED = "request_failed"

_SEARCH_URL = "https://djinni.co/jobs/"
# Same category scope feeds.json already ingests on — narrows the company
# page for an employer with postings across many unrelated categories, same
# as the user's own manual filter (confirmed live 2026-09-05: no change for
# a small company, but keeps a large one's page count within our page cap).
_ROLE_FILTER = "primary_keyword=Product+Owner&primary_keyword=Product+Manager"


def _job_ids_on_page(html: str) -> set[str]:
    return set(re.findall(r'/jobs/(\d+)-', html))


class _Budget:
    """Mutable request counter + outcome tracking, shared by reference
    across both identification strategies for one find_salary_ceiling()
    call — see module docstring for why this needs to be shared rather than
    per-strategy.
    """
    __slots__ = ("remaining", "found_anywhere", "had_network_error", "hit_ambiguous_cap")

    def __init__(self, total: int) -> None:
        self.remaining = total
        self.found_anywhere = False
        self.had_network_error = False
        # Set whenever a present() check ran out of budget or page cap
        # WITHOUT ever confirming absence (an empty page) — distinct from
        # found_anywhere=False by itself, which could otherwise wrongly look
        # like "genuinely never found" when the search simply never got far
        # enough to tell either way (found live 2026-09-07: a budget cut-off
        # on the very first check, before ever seeing the target, isn't the
        # same claim as "this listing doesn't exist").
        self.hit_ambiguous_cap = False


def _present_at(
    url_for_page: Callable[[int], str], target_id: str, max_pages: int, exhaustive: bool, budget: _Budget,
) -> bool | None:
    """Is *target_id* present, scanning up to *max_pages* pages via
    *url_for_page*(page)?

    True/False if determinable within max_pages (and the shared budget),
    None otherwise. What happens at the page cap depends on *exhaustive*:
    company pages never have a genuine second page (Djinni falls back to an
    unrelated "recommended jobs" listing past the real end instead of an
    empty page — found live 2026-09-07, vacancy #231 — so max_pages=1 there
    IS the whole result set) — a non-empty-but-absent last page is
    definitive False, not "too broad to tell". Title-only search has no
    such guarantee (a genuinely large match count can span real pages
    beyond the cap), so the same situation there stays None — "don't trust
    this data point".
    """
    for page in range(1, max_pages + 1):
        if budget.remaining <= 0:
            budget.hit_ambiguous_cap = True
            return None
        budget.remaining -= 1
        resp = fetch(url_for_page(page))
        if resp is None:
            budget.had_network_error = True
            return None
        ids = _job_ids_on_page(resp.text)
        if target_id in ids:
            budget.found_anywhere = True
            return True
        if not ids:
            return False  # ran out of real pages before the cap
    if exhaustive:
        return False
    budget.hit_ambiguous_cap = True
    return None


def _find_ceiling(
    build_url: Callable[[int, int], str], target_id: str, vacancy_url: str,
    max_pages: int, exhaustive: bool, budget: _Budget,
) -> int | None:
    """Exponential-then-binary search for the salary threshold at which
    *target_id* disappears, using *build_url*(salary, page) for one
    particular identification strategy — see find_salary_ceiling() for the
    two strategies this gets called with.
    """
    def present(salary: int) -> bool | None:
        return _present_at(lambda page: build_url(salary, page), target_id, max_pages, exhaustive, budget)

    if present(0) is not True:
        return None

    # Exponential search for an upper bracket where the vacancy has
    # disappeared, then binary search within it at STEP resolution — far
    # fewer requests than walking up by STEP alone for a high salary.
    lo, increment = 0, STEP
    hi = STEP
    while True:
        found = present(hi)
        if found is None:
            # A mid-search failure here silently produced a wrong-but-
            # confident-looking result before (found live 2026-09-05,
            # vacancy #1431: returned $1500 as if confirmed, real value was
            # $3000, user's own manual check caught it) — returning `lo`
            # looked "conservative" but reported a number the search never
            # actually confirmed as the ceiling. Same philosophy as the
            # baseline check: an unconfirmed data point is undeterminable,
            # not a value to report.
            log.info("salary_probe: %s — request failed mid-search at %d, discarding partial result", vacancy_url, hi)
            return None
        if not found:
            break
        lo = hi
        increment *= 2
        hi = lo + increment
        if hi > MAX_SALARY:
            log.info("salary_probe: %s still present past %d — giving up", vacancy_url, MAX_SALARY)
            return None

    while hi - lo > STEP:
        mid = lo + ((hi - lo) // 2 // STEP) * STEP
        if mid == lo:
            break
        found = present(mid)
        if found is None:
            log.info("salary_probe: %s — request failed mid-search at %d, discarding partial result", vacancy_url, mid)
            return None
        if found:
            lo = mid
        else:
            hi = mid

    return lo


def find_salary_ceiling(
    vacancy_url: str,
    title: str,
    company_profile_url: str | None = None,
) -> tuple[int | None, str | None]:
    """Binary search for the salary threshold at which *vacancy_url*
    disappears from Djinni's own salary-filtered search.

    Tries the company page first (precise, tiny result sets — the user's own
    manual method), falling back to a title-only search when no company
    profile URL is available or the company page didn't resolve it. Both
    strategies share one request budget (MAX_TOTAL_REQUESTS) — see module
    docstring.

    Returns (ceiling, reason): ceiling is the last value (a multiple of
    STEP) the vacancy is still present at, or None if undeterminable. reason
    is always None when ceiling is found; otherwise one of REASON_NOT_FOUND
    (never located under either strategy — likely expired/removed),
    REASON_TOO_MANY_MATCHES (found, but the result set never narrowed down
    enough to pin a threshold — a generic title or a large employer), or
    REASON_REQUEST_FAILED (a request to Djinni itself failed). Never a
    guess — every non-None ceiling was actually confirmed present/absent at
    that boundary.
    """
    m = re.search(r'/jobs/(\d+)-', vacancy_url)
    if not m:
        return None, REASON_NOT_FOUND
    target_id = m.group(1)
    budget = _Budget(MAX_TOTAL_REQUESTS)

    if company_profile_url:
        base = company_profile_url.rstrip("/")
        result = _find_ceiling(
            lambda salary, page: f"{base}/?{_ROLE_FILTER}&salary={salary}&page={page}",
            target_id, vacancy_url, max_pages=_COMPANY_PAGE_MAX_PAGES, exhaustive=True, budget=budget,
        )
        if result is not None:
            return result, None
        log.info("salary_probe: %s — company-page identification failed, falling back to title-only search", vacancy_url)

    result = _find_ceiling(
        lambda salary, page: (
            f"{_SEARCH_URL}?search_type=title-only&all_keywords={quote(title)}&salary={salary}&page={page}"
        ),
        target_id, vacancy_url, max_pages=MAX_PAGES_PER_CHECK, exhaustive=False, budget=budget,
    )
    if result is not None:
        return result, None

    if budget.had_network_error:
        reason = REASON_REQUEST_FAILED
    elif budget.found_anywhere or budget.hit_ambiguous_cap:
        # Either we saw the target and then lost track of it, or the search
        # never got far enough (page cap or budget) to rule it out either
        # way — both mean "might well exist, we just couldn't pin it down",
        # not "confirmed absent".
        reason = REASON_TOO_MANY_MATCHES
    else:
        reason = REASON_NOT_FOUND
    log.info("salary_probe: undeterminable for %s (reason=%s)", vacancy_url, reason)
    return None, reason
