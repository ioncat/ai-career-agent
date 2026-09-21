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

**Identification: company page, ID-based, always** (2026-09-08 — simplified
from an earlier two-strategy design, see below). Every Djinni vacancy is
published by some user account, and that account's own page lists every
vacancy it ever posted — there is no such thing as an "orphan" posting with
no company/agency page behind it. So the method is always the same, exactly
the user's own manual technique: open the vacancy, follow its link to the
poster's own Djinni page (`/jobs/company-{slug}/`), apply the salary filter
there — optionally narrowed by *category*, when the caller has one.

*category* is never guessed from the title (2026-09-08, twice-revised): a
hardcoded "Product Owner"/"Product Manager" filter here originally broke as
soon as the feed started ingesting other roles (found live, vacancy #1505,
Phenomenon Studio, a Business Analyst posting — present on the company page
with no filter, absent under the old PM/PO-only one) — removing the filter
fixed that, but reopened a different real risk for a busy employer/agency
with many unrelated postings (confirmed live: NDA Recruitment's own page,
unfiltered, already fills page 1 with 15 postings across many categories
before even reaching page 2 — the exact page-cap risk this filter exists to
avoid). The fix isn't inferring a category from the job title (that would
just reintroduce the same brittleness under a new name) — Djinni's own
vacancy pages carry the *real* answer as standard structured data: every
page checked (15/15 in a live sample) has a schema.org `JobPosting`
JSON-LD block with a plain `category` field ("Product Manager", "Product
Owner", "Business Analyst", ...) — Djinni's own canonical assignment for
that specific posting, read directly, never inferred. The caller (the
`/djinni-salary-ceiling` endpoint) extracts it and passes it in; when it's
missing (should be rare, given the sample above) this module simply
searches the company page unfiltered instead of guessing.

Confirmed live 2026-09-05 on vacancy #1393 (bare "Product Manager", Twist
Robotics): the company page shows exactly 1 result at $5000, 0 at $5500.
The page is never paginated past page 1 — Djinni's own pagination doesn't
return an EMPTY page once a company's real results run out (found live
2026-09-07, vacancy #231, Influence Pro Services): page 2+ silently falls
back to an unrelated "recommended jobs" listing instead of confirming
absence, so asking for a second page would corrupt the answer rather than
refine it. With *category* available, a company realistically never has
more than a handful of postings in one narrow professional field, so page 1
usually IS the whole result set; without it (or for a genuinely saturated
single category at one employer), page 1 could still fall short — which
surfaces as an honest REASON_NOT_ON_COMPANY_PAGE rather than a guess.

Only the internal job ID (regex-extracted from the page HTML) is ever
matched against — the human-readable title plays no role in the algorithm
at all; it exists only for a person reading the page, never for this code
(2026-09-08, user's own point: the ID-based, company-scoped lookup never
needed a text/title search as a fallback in the first place — an earlier
"title-only search" fallback strategy for when no company link was found
was removed once real data showed that case essentially never happens: a
25-vacancy live sample found a company link on every single fetchable page).

No silent workaround when identification itself is inconclusive — both of
the (expected to be rare) failure shapes get their own explicit reason
instead of a fuzzy fallback search: REASON_NO_COMPANY_LINK (couldn't find a
company link on the vacancy page at all — user's own assessment: this
should never really happen) and REASON_NOT_ON_COMPANY_PAGE (found the
company, but this vacancy isn't listed on its own page — user confirmed
having seen this once, attributed to a possible Djinni-internal indexing
quirk, or a large employer's page exceeding the single-page cap; too rare
to justify a second search strategy, just worth a short, honest note
pointing the user at it).

`find_salary_ceiling()` also enforces a request budget (MAX_TOTAL_REQUESTS,
2026-09-07) — without it a vacancy that's genuinely present but never
narrows down (e.g. a company page search that keeps flip-flopping across
retries) could otherwise grind through requests with no upper bound on time
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
from urllib.parse import quote_plus

from crawler import fetch

log = logging.getLogger(__name__)

# User-confirmed experimentally (2026-09-05) — Djinni's own filter snaps to
# $500 increments; anything finer would just re-discover the same steps.
STEP = 500
# Past this, either the vacancy genuinely pays that well or Djinni simply
# has no real number on file for it (some postings never disappear from the
# filtered search no matter how high it's raised — confirmed live 2026-09-08,
# vacancy #1504, present up to $100,000 with the same 3-listing result set
# unchanged) — either way, not worth chasing further automatically.
MAX_SALARY = 10000
# Company pages only ever get 1 page — found live 2026-09-07, vacancy #231
# (Influence Pro Services, 4 total postings): Djinni's own pagination
# doesn't return an EMPTY page once a company's real results run out — page
# 2+ silently falls back to an unrelated "recommended jobs" listing instead
# (confirmed: the exact same ~15 job ids appeared on page 2 of this
# company's page as on page 2 of an unrelated search, regardless of query or
# filter). A non-empty-but-absent page 1 is definitive False, not "too
# broad to tell" — a company realistically never has enough PM/PO postings
# to need a second page in the first place, so the safe fix is simply never
# asking Djinni for one.
MAX_TOTAL_REQUESTS = 30

# Why find_salary_ceiling() gave up, when it did — lets the caller leave a
# short, honest note instead of silence. Deliberately coarse — a
# caller-facing reason should explain roughly *what happened*, not retrace
# the search's own internals.
REASON_NOT_FOUND = "not_found"
# The shared budget ran out (or a present() check hit an internal cap)
# after already confirming the vacancy IS on its company page, but before
# pinning an exact salary threshold — a genuinely rare edge case now that
# identification is a single, small, company-scoped page (renamed from the
# old "too_many_matches" 2026-09-08, which described a different, now-
# removed title-only-search failure mode).
REASON_BUDGET_EXHAUSTED = "budget_exhausted"
REASON_REQUEST_FAILED = "request_failed"
# Still present at MAX_SALARY itself — a *confirmed* data point (unlike
# REASON_BUDGET_EXHAUSTED, which means the search never got far enough to
# tell either way), distinct enough to say something more useful than "too
# many matches": either the pay genuinely is that high, or — just as likely
# — Djinni has no real number on file for this posting at all, so raising
# the filter never excludes it (confirmed live 2026-09-08, vacancy #1504:
# present unchanged from $0 through $100,000, same 3-listing result set).
REASON_HIGH_SALARY = "high_salary"
# No company/agency link found on the vacancy page at all (2026-09-08).
# User's own assessment: structurally, this should never happen — every
# vacancy belongs to some posting account's own page — so this reason exists
# to surface an unexpected case explicitly rather than silently guess at an
# alternative.
REASON_NO_COMPANY_LINK = "no_company_link"
# Company page found, but this vacancy isn't listed on its own page
# (2026-09-08). Was originally expected to mean a Djinni-internal category
# mismatch against a hardcoded role filter — that filter has since been
# removed entirely (see below) after it turned out to be the actual, common
# cause rather than a rare edge case. What's left as a genuine reason here:
# a large employer with postings spanning many unrelated departments
# exceeding the single-page cap. User has seen an occurrence of this reason
# once before Rare enough that it isn't worth a second search strategy —
# just an honest, visible note.
REASON_NOT_ON_COMPANY_PAGE = "not_on_company_page"

# No role/category filter on the company page (removed 2026-09-08 — was
# hardcoded to "Product Owner"/"Product Manager" only). This code has no
# business deciding what category a vacancy belongs to — it only needs to
# find one specific ID on its own poster's page, and the page itself is
# already the real scoping (one employer). The hardcoded filter broke as
# soon as the feed started ingesting a role outside PM/PO: found live,
# vacancy #1505 (Phenomenon Studio, Business Analyst) — 2 total postings on
# the company page with no filter (target present), 0 with the old PM/PO
# filter, would have broken again for every future category the feed
# expands to.


def _job_ids_on_page(html: str) -> set[str]:
    return set(re.findall(r'/jobs/(\d+)-', html))


class _Budget:
    """Mutable request counter + outcome tracking for one
    find_salary_ceiling() call.
    """
    __slots__ = ("remaining", "found_anywhere", "had_network_error", "hit_ambiguous_cap", "exceeded_ceiling")

    def __init__(self, total: int) -> None:
        self.remaining = total
        self.found_anywhere = False
        self.had_network_error = False
        # Set whenever a present() check ran out of budget WITHOUT ever
        # confirming absence — distinct from found_anywhere=False by itself,
        # which could otherwise wrongly look like "genuinely never found"
        # when the search simply never got far enough to tell either way.
        self.hit_ambiguous_cap = False
        # Set specifically when the target was CONFIRMED still present at
        # MAX_SALARY itself (2026-09-08) — a definite result, unlike
        # hit_ambiguous_cap above (which means we never got far enough to
        # confirm anything). Distinguishing the two lets the caller report
        # "still present at the ceiling" instead of the vaguer "ran out of
        # steps" when that's specifically what happened.
        self.exceeded_ceiling = False


def _present_at(url: str, target_id: str, budget: _Budget) -> bool | None:
    """Is *target_id* present on the company's page at this salary? Single
    page only — see module docstring for why a second page
    is never requested: page 1 IS the whole result set, so a non-empty-but-
    absent page is definitive False, not "too broad to tell".

    True/False if the request succeeds, None on network failure or an
    exhausted budget (don't trust this data point either way).
    """
    if budget.remaining <= 0:
        budget.hit_ambiguous_cap = True
        return None
    budget.remaining -= 1
    resp = fetch(url)
    if resp is None:
        budget.had_network_error = True
        return None
    if target_id in _job_ids_on_page(resp.text):
        budget.found_anywhere = True
        return True
    return False


def _find_ceiling(
    build_url: Callable[[int], str], target_id: str, vacancy_url: str, budget: _Budget,
) -> int | None:
    """Exponential-then-binary search for the salary threshold at which
    *target_id* disappears, using *build_url*(salary) for the company's
    page.
    """
    def present(salary: int) -> bool | None:
        return _present_at(build_url(salary), target_id, budget)

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
        if lo >= MAX_SALARY:
            # Confirmed present AT the ceiling itself — a definite result,
            # not a search that merely ran out of runway (found live
            # 2026-09-08, vacancy #1504 — see REASON_HIGH_SALARY).
            log.info("salary_probe: %s still present at the %d ceiling", vacancy_url, MAX_SALARY)
            budget.exceeded_ceiling = True
            return None
        increment *= 2
        # Capped at MAX_SALARY itself (2026-09-08) — testing exactly at the
        # ceiling instead of jumping past it lets a real threshold just
        # under the cap (e.g. $9000 with a $10000 ceiling) still resolve
        # normally instead of being mistaken for "exceeds the ceiling".
        hi = min(lo + increment, MAX_SALARY)

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
    company_profile_url: str | None = None,
    category: str | None = None,
) -> tuple[int | None, str | None]:
    """Binary search for the salary threshold at which *vacancy_url*
    disappears from its posting company's own Djinni page.

    *category* — when given, Djinni's own `primary_keyword` filter value
    (e.g. "Product Manager", "Business Analyst") for this specific vacancy,
    narrowing the company page for a busy employer/agency. Always read from
    the vacancy's own schema.org JSON-LD `category` field by the caller —
    never inferred from the title here. Omitted (or unresolvable) simply
    means searching the company page unfiltered instead of guessing.

    Returns (ceiling, reason): ceiling is the last value (a multiple of
    STEP) the vacancy is still present at, or None if undeterminable. reason
    is always None when ceiling is found; otherwise one of:
    - REASON_NOT_FOUND: *vacancy_url* isn't a valid Djinni job link at all.
    - REASON_NO_COMPANY_LINK: no company/agency page found for this
      vacancy — expected to essentially never happen.
    - REASON_NOT_ON_COMPANY_PAGE: the company page was found, but this
      vacancy isn't listed on its own page.
    - REASON_HIGH_SALARY: confirmed still present at MAX_SALARY itself —
      either it genuinely pays that well, or Djinni has no real number on
      file for this posting at all.
    - REASON_BUDGET_EXHAUSTED: confirmed present, but the search never got
      far enough to pin an exact threshold before running out of budget.
    - REASON_REQUEST_FAILED: a request to Djinni itself failed.
    Never a guess — every non-None ceiling was actually confirmed
    present/absent at that boundary.
    """
    m = re.search(r'/jobs/(\d+)-', vacancy_url)
    if not m:
        return None, REASON_NOT_FOUND
    target_id = m.group(1)

    if not company_profile_url:
        log.info("salary_probe: %s — no company page found", vacancy_url)
        return None, REASON_NO_COMPANY_LINK

    base = company_profile_url.rstrip("/")
    role_filter = f"primary_keyword={quote_plus(category)}&" if category else ""
    budget = _Budget(MAX_TOTAL_REQUESTS)
    result = _find_ceiling(
        lambda salary: f"{base}/?{role_filter}salary={salary}&page=1",
        target_id, vacancy_url, budget,
    )
    if result is not None:
        return result, None
    if budget.exceeded_ceiling:
        return None, REASON_HIGH_SALARY
    if budget.had_network_error:
        return None, REASON_REQUEST_FAILED
    if budget.found_anywhere or budget.hit_ambiguous_cap:
        # Confirmed present at baseline (or the budget ran dry before ever
        # confirming absence) — the search just never pinned an exact
        # threshold, not "this vacancy isn't there".
        reason = REASON_BUDGET_EXHAUSTED
    else:
        reason = REASON_NOT_ON_COMPANY_PAGE
    log.info("salary_probe: undeterminable for %s (reason=%s)", vacancy_url, reason)
    return None, reason
