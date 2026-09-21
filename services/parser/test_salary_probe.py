"""
services/parser/test_salary_probe.py — tests for the Djinni hidden-salary
estimator (salary_probe.py).

All network access goes through crawler.fetch(), monkeypatched here to a
fake in-memory "Djinni" that returns the target vacancy id in its result
HTML only up to a fixed salary threshold — mirrors the real site's observed
behavior (confirmed live 2026-09-05: present at salary=3000, gone at
salary=8000 for vacancy 846686).

Identification is always via the posting company's own Djinni page
(2026-09-08 — simplified from an earlier two-strategy design after real
data showed every fetchable Djinni vacancy has a company/agency page behind
it; see salary_probe.py's module docstring). Every test below supplies a
company_profile_url — a real find_salary_ceiling() call always does too.
"""

from types import SimpleNamespace

import salary_probe


TARGET_ID = "846686"
TARGET_URL = f"https://djinni.co/jobs/{TARGET_ID}-glig-product-development-manager"
COMPANY_URL = "https://djinni.co/jobs/company-glig"


def _cards(ids: list[str]) -> str:
    return "".join(f'<a href="/jobs/{i}-x/">x</a>' for i in ids)


def _resp(html: str) -> SimpleNamespace:
    return SimpleNamespace(text=html)


def test_ceiling_found_at_exact_threshold(monkeypatch):
    """Vacancy present through salary=3000, gone at 3500+ — expect 3000."""
    threshold = 3000

    def fake_fetch(url: str):
        salary = int(url.split("salary=")[1].split("&")[0])
        return _resp(_cards([TARGET_ID] if salary <= threshold else []))

    monkeypatch.setattr(salary_probe, "fetch", fake_fetch)
    assert salary_probe.find_salary_ceiling(TARGET_URL, COMPANY_URL) == (threshold, None)


def test_category_narrows_a_busy_companys_page(monkeypatch):
    """Regression 2026-09-08: a busy agency's unfiltered company page can
    already fill page 1 with unrelated postings before the target ever
    appears (confirmed live: NDA Recruitment, 15 unrelated ids on an
    unfiltered page 1). *category* — Djinni's own field for this specific
    vacancy, never inferred from the title — narrows the same page down to
    just that category, same as the user's own manual filter."""
    other_ids = [str(1000 + i) for i in range(15)]  # a full, unrelated page 1

    def fake_fetch(url: str):
        if "primary_keyword=Business+Analyst" in url:
            salary = int(url.split("salary=")[1].split("&")[0])
            return _resp(_cards([TARGET_ID] if salary <= 3500 else []))
        # Unfiltered: a busy page full of other postings, target never on it.
        return _resp(_cards(other_ids))

    monkeypatch.setattr(salary_probe, "fetch", fake_fetch)
    assert salary_probe.find_salary_ceiling(TARGET_URL, COMPANY_URL, "Business Analyst") == (3500, None)


def test_no_category_falls_back_to_unfiltered_company_page(monkeypatch):
    """No category available (e.g. the vacancy page's JSON-LD didn't parse)
    — must still work exactly as before category support existed, not
    fail or silently drop the request."""
    threshold = 3000

    def fake_fetch(url: str):
        assert "primary_keyword" not in url
        salary = int(url.split("salary=")[1].split("&")[0])
        return _resp(_cards([TARGET_ID] if salary <= threshold else []))

    monkeypatch.setattr(salary_probe, "fetch", fake_fetch)
    assert salary_probe.find_salary_ceiling(TARGET_URL, COMPANY_URL, None) == (threshold, None)


def test_no_company_link_is_reported_explicitly(monkeypatch):
    """No company_profile_url at all — user's own assessment: this should
    essentially never happen (every vacancy belongs to some posting
    account's own page), so it gets its own explicit reason rather than a
    fuzzy fallback search."""
    calls = []
    monkeypatch.setattr(salary_probe, "fetch", lambda url: calls.append(url) or _resp(_cards([TARGET_ID])))
    assert salary_probe.find_salary_ceiling(TARGET_URL, None) == (None, salary_probe.REASON_NO_COMPANY_LINK)
    assert calls == []  # no point fetching anything without a company page


def test_not_on_company_page_when_absent_at_baseline(monkeypatch):
    """Company page found, but this vacancy isn't listed on its own
    role-filtered page — confirmed absence, not "couldn't tell"."""
    monkeypatch.setattr(salary_probe, "fetch", lambda url: _resp(_cards([])))
    assert salary_probe.find_salary_ceiling(TARGET_URL, COMPANY_URL) == (None, salary_probe.REASON_NOT_ON_COMPANY_PAGE)


def test_undeterminable_when_network_fails_at_baseline(monkeypatch):
    monkeypatch.setattr(salary_probe, "fetch", lambda url: None)
    assert salary_probe.find_salary_ceiling(TARGET_URL, COMPANY_URL) == (None, salary_probe.REASON_REQUEST_FAILED)


def test_network_failure_during_exponential_phase_returns_none_not_partial(monkeypatch):
    """Regression 2026-09-05, vacancy #1431: present through $3000, gone at
    $3500 (confirmed by the user's own manual method). A transient fetch
    failure exactly at the $3500 exponential-search check used to make the
    function return $1500 (the last *confirmed* value) as if it were the
    real ceiling — silently wrong, not "conservative". Must return None
    instead: an unconfirmed data point is undeterminable, not reportable."""
    threshold = 3000

    def fake_fetch(url: str):
        salary = int(url.split("salary=")[1].split("&")[0])
        if salary == 3500:
            return None  # exhausted retries inside crawler.fetch()
        return _resp(_cards([TARGET_ID] if salary <= threshold else []))

    monkeypatch.setattr(salary_probe, "fetch", fake_fetch)
    ceiling, reason = salary_probe.find_salary_ceiling(TARGET_URL, COMPANY_URL)
    assert ceiling is None
    assert reason == salary_probe.REASON_REQUEST_FAILED


def test_network_failure_during_binary_search_phase_returns_none_not_partial(monkeypatch):
    """Same failure mode, later in the search — after the exponential phase
    has already bracketed the answer, a failed probe inside the binary
    search must still discard the whole result, not settle for `lo`."""
    threshold = 3000
    fail_at = {3500: False, 2500: False, 3000: True}  # fail exactly the final narrowing check

    def fake_fetch(url: str):
        salary = int(url.split("salary=")[1].split("&")[0])
        if fail_at.get(salary):
            return None
        return _resp(_cards([TARGET_ID] if salary <= threshold else []))

    monkeypatch.setattr(salary_probe, "fetch", fake_fetch)
    ceiling, reason = salary_probe.find_salary_ceiling(TARGET_URL, COMPANY_URL)
    assert ceiling is None
    assert reason == salary_probe.REASON_REQUEST_FAILED


def test_company_page_never_requests_a_second_page(monkeypatch):
    """Regression 2026-09-07, vacancy #231 (Influence Pro Services, 4 total
    postings): Djinni's own pagination doesn't return an empty page once a
    company's real results run out — page 2 silently falls back to an
    unrelated "recommended jobs" listing instead (confirmed live: the same
    ~15 ids appeared on page 2 of an unrelated company AND an unrelated
    search). A non-empty page 1 that doesn't contain the target must be
    treated as definitive absence, not "too broad to tell" — and page 2
    must never even be requested."""
    threshold = 4500
    company_url = "https://djinni.co/jobs/company-influence-pro-services"
    other_company_vacancy_id = "846784"  # a real co-worker posting, always present

    def fake_fetch(url: str):
        if "&page=1" not in url:
            raise AssertionError(f"must always request page 1 explicitly: {url}")
        salary = int(url.split("salary=")[1].split("&")[0])
        ids = [other_company_vacancy_id]
        if salary <= threshold:
            ids.append(TARGET_ID)
        return _resp(_cards(ids))

    monkeypatch.setattr(salary_probe, "fetch", fake_fetch)
    assert salary_probe.find_salary_ceiling(TARGET_URL, company_url) == (threshold, None)


def test_invalid_url_returns_none_without_any_fetch(monkeypatch):
    calls = []
    monkeypatch.setattr(salary_probe, "fetch", lambda url: calls.append(url) or _resp(_cards([TARGET_ID])))
    assert salary_probe.find_salary_ceiling("https://djinni.co/not-a-job-url") == (None, salary_probe.REASON_NOT_FOUND)
    assert calls == []


def test_high_ceiling_uses_exponential_search_before_binary_search(monkeypatch):
    """Threshold above the first doubling step — exercises the exponential
    bracket-finding loop, not just the final binary-search narrowing."""
    threshold = 9000  # forces at least 3 doublings (500 -> 1000 -> 2000 -> 4000 -> ...)
    calls = {"count": 0}

    def fake_fetch(url: str):
        calls["count"] += 1
        salary = int(url.split("salary=")[1].split("&")[0])
        return _resp(_cards([TARGET_ID] if salary <= threshold else []))

    monkeypatch.setattr(salary_probe, "fetch", fake_fetch)
    assert salary_probe.find_salary_ceiling(TARGET_URL, COMPANY_URL) == (threshold, None)
    # Sanity bound on request volume — must stay far below a linear $500-step
    # walk to MAX_SALARY, proving the exponential phase ran.
    assert calls["count"] < 15


def test_still_present_at_ceiling_reported_as_high_salary(monkeypatch):
    """Regression 2026-09-08, vacancy #1504 (NDA Recruitment): the company-
    page, role-filtered search correctly narrowed to a handful of postings
    and found the target present at every salary level tested, unchanged
    all the way past the old $20,000 cap (confirmed live up to $100,000) —
    Djinni likely holds no real number for this listing at all, so raising
    the filter never excludes it. This is a *confirmed* result, distinct
    from "search never got far enough to tell"."""
    company_url = "https://djinni.co/jobs/company-nda-recruitment"

    def fake_fetch(url: str):
        if "&page=1" not in url:
            raise AssertionError(f"must never request page 2+: {url}")
        return _resp(_cards([TARGET_ID]))  # present at every salary level tested

    monkeypatch.setattr(salary_probe, "fetch", fake_fetch)
    result = salary_probe.find_salary_ceiling(TARGET_URL, company_url)
    assert result == (None, salary_probe.REASON_HIGH_SALARY)


def test_high_salary_boundary_does_not_misfire_for_a_threshold_just_under_the_cap(monkeypatch):
    """The exponential search's probe points must be capped AT MAX_SALARY,
    not merely checked against it after overshooting — otherwise a real
    threshold just under the cap could be skipped past without ever being
    tested, and wrongly reported as REASON_HIGH_SALARY instead of its real
    (lower) value."""
    threshold = salary_probe.MAX_SALARY - 1000

    def fake_fetch(url: str):
        salary = int(url.split("salary=")[1].split("&")[0])
        return _resp(_cards([TARGET_ID] if salary <= threshold else []))

    monkeypatch.setattr(salary_probe, "fetch", fake_fetch)
    assert salary_probe.find_salary_ceiling(TARGET_URL, COMPANY_URL) == (threshold, None)


# ── Shared per-vacancy request budget (2026-09-07) ──────────────────────────
# User feedback: a vacancy that's genuinely present but never narrows down
# could otherwise grind through dozens of throttled requests with no upper
# bound on time spent.

def test_budget_exhausted_mid_search_reports_budget_exhausted(monkeypatch):
    """Company page confirms presence at baseline (so it's not "absent"),
    but the search burns through the whole shared budget before ever
    pinning an exact threshold — must report REASON_BUDGET_EXHAUSTED, not
    silently hang or misreport an unconfirmed value."""
    small_budget = 5
    monkeypatch.setattr(salary_probe, "MAX_TOTAL_REQUESTS", small_budget)
    calls = {"count": 0}

    def fake_fetch(url: str):
        calls["count"] += 1
        return _resp(_cards([TARGET_ID]))  # always present, exponential search never stops on its own

    monkeypatch.setattr(salary_probe, "fetch", fake_fetch)
    result = salary_probe.find_salary_ceiling(TARGET_URL, COMPANY_URL)
    assert result == (None, salary_probe.REASON_BUDGET_EXHAUSTED)
    assert calls["count"] == small_budget
