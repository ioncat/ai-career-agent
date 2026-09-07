"""
services/parser/test_salary_probe.py — tests for the Djinni hidden-salary
estimator (salary_probe.py).

All network access goes through crawler.fetch(), monkeypatched here to a
fake in-memory "Djinni" that returns the target vacancy id in its result
HTML only up to a fixed salary threshold — mirrors the real site's observed
behavior (confirmed live 2026-09-05: present at salary=3000, gone at
salary=8000 for vacancy 846686).
"""

from types import SimpleNamespace

import salary_probe


TARGET_ID = "846686"
TARGET_URL = f"https://djinni.co/jobs/{TARGET_ID}-glig-product-development-manager"


def _cards(ids: list[str]) -> str:
    return "".join(f'<a href="/jobs/{i}-x/">x</a>' for i in ids)


def _resp(html: str) -> SimpleNamespace:
    return SimpleNamespace(text=html)


def test_ceiling_found_at_exact_threshold(monkeypatch):
    """Vacancy present through salary=3000, gone at 3500+ — expect 3000."""
    threshold = 3000

    def fake_fetch(url: str):
        salary = int(url.split("salary=")[1].split("&")[0])
        page = int(url.split("page=")[1])
        if page > 1:
            return _resp(_cards([]))
        if salary <= threshold:
            return _resp(_cards([TARGET_ID]))
        return _resp(_cards([]))

    monkeypatch.setattr(salary_probe, "fetch", fake_fetch)
    assert salary_probe.find_salary_ceiling(TARGET_URL, "GLIG — Product Development Manager") == threshold


def test_undeterminable_when_absent_at_baseline(monkeypatch):
    """Expired listing / title mismatch — never present, even at salary=0."""
    monkeypatch.setattr(salary_probe, "fetch", lambda url: _resp(_cards([])))
    assert salary_probe.find_salary_ceiling(TARGET_URL, "Some Title") is None


def test_undeterminable_when_network_fails_at_baseline(monkeypatch):
    monkeypatch.setattr(salary_probe, "fetch", lambda url: None)
    assert salary_probe.find_salary_ceiling(TARGET_URL, "Some Title") is None


def test_generic_title_exceeding_page_cap_returns_none(monkeypatch):
    """Every page full of OTHER vacancies, target never appears, cap never
    exhausted (no empty page) — too generic to track, must not guess."""
    other_ids = [str(1000 + i) for i in range(15)]

    def fake_fetch(url: str):
        return _resp(_cards(other_ids))

    monkeypatch.setattr(salary_probe, "fetch", fake_fetch)
    assert salary_probe.find_salary_ceiling(TARGET_URL, "Product Manager") is None


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
        page = int(url.split("page=")[1])
        if page > 1:
            return _resp(_cards([]))
        if salary == 3500:
            return None  # exhausted retries inside crawler.fetch()
        return _resp(_cards([TARGET_ID] if salary <= threshold else []))

    monkeypatch.setattr(salary_probe, "fetch", fake_fetch)
    assert salary_probe.find_salary_ceiling(TARGET_URL, "Product Manager (web)") is None


def test_network_failure_during_binary_search_phase_returns_none_not_partial(monkeypatch):
    """Same failure mode, later in the search — after the exponential phase
    has already bracketed the answer, a failed probe inside the binary
    search must still discard the whole result, not settle for `lo`."""
    threshold = 3000
    fail_at = {3500: False, 2500: False, 3000: True}  # fail exactly the final narrowing check

    def fake_fetch(url: str):
        salary = int(url.split("salary=")[1].split("&")[0])
        page = int(url.split("page=")[1])
        if page > 1:
            return _resp(_cards([]))
        if fail_at.get(salary):
            return None
        return _resp(_cards([TARGET_ID] if salary <= threshold else []))

    monkeypatch.setattr(salary_probe, "fetch", fake_fetch)
    assert salary_probe.find_salary_ceiling(TARGET_URL, "Product Manager (web)") is None


def test_company_page_used_first_when_available(monkeypatch):
    """Company page identification (the user's own manual method) is tried
    before title-only search — a call the fake backend would refuse to
    resolve via title-only (bare "Product Manager", too many other matches)
    must still succeed via the company page."""
    threshold = 5000
    company_url = "https://djinni.co/jobs/company-twist-robotics"

    def fake_fetch(url: str):
        if not url.startswith(company_url):
            raise AssertionError(f"expected company-page URL, title-only fallback should not have been tried: {url}")
        salary = int(url.split("salary=")[1].split("&")[0])
        page = int(url.split("page=")[1])
        if page > 1:
            return _resp(_cards([]))
        return _resp(_cards([TARGET_ID] if salary <= threshold else []))

    monkeypatch.setattr(salary_probe, "fetch", fake_fetch)
    result = salary_probe.find_salary_ceiling(TARGET_URL, "Product Manager", company_url)
    assert result == threshold


def test_company_page_never_requests_a_second_page(monkeypatch):
    """Regression 2026-09-07, vacancy #231 (Influence Pro Services, 4 total
    postings): Djinni's own pagination doesn't return an empty page once a
    company's real results run out — page 2 silently falls back to an
    unrelated "recommended jobs" listing instead (confirmed live: the same
    ~15 ids appeared on page 2 of an unrelated company AND an unrelated
    title-only search). A non-empty page 1 that doesn't contain the target
    must be treated as definitive absence, not "too broad to tell" — and
    page 2 must never even be requested for this strategy."""
    threshold = 4500
    company_url = "https://djinni.co/jobs/company-influence-pro-services"
    other_company_vacancy_id = "846784"  # a real co-worker posting, always present

    def fake_fetch(url: str):
        page = int(url.split("page=")[1])
        if page > 1:
            raise AssertionError(f"company-page strategy must never request page 2+: {url}")
        salary = int(url.split("salary=")[1].split("&")[0])
        ids = [other_company_vacancy_id]
        if salary <= threshold:
            ids.append(TARGET_ID)
        return _resp(_cards(ids))

    monkeypatch.setattr(salary_probe, "fetch", fake_fetch)
    result = salary_probe.find_salary_ceiling(TARGET_URL, "Senior Product Manager", company_url)
    assert result == threshold


def test_falls_back_to_title_only_when_company_page_inconclusive(monkeypatch):
    """Company page never resolves (e.g. an agency page listing dozens of
    unrelated postings) — must fall back to title-only rather than giving
    up, and succeed there."""
    threshold = 3000
    company_url = "https://djinni.co/jobs/company-some-agency"
    other_ids = [str(1000 + i) for i in range(15)]

    def fake_fetch(url: str):
        if url.startswith(company_url):
            return _resp(_cards(other_ids))  # always "too broad", never resolves
        salary = int(url.split("salary=")[1].split("&")[0])
        page = int(url.split("page=")[1])
        if page > 1:
            return _resp(_cards([]))
        return _resp(_cards([TARGET_ID] if salary <= threshold else []))

    monkeypatch.setattr(salary_probe, "fetch", fake_fetch)
    result = salary_probe.find_salary_ceiling(TARGET_URL, "GLIG — Product Development Manager", company_url)
    assert result == threshold


def test_invalid_url_returns_none_without_any_fetch(monkeypatch):
    calls = []
    monkeypatch.setattr(salary_probe, "fetch", lambda url: calls.append(url) or _resp(_cards([TARGET_ID])))
    assert salary_probe.find_salary_ceiling("https://djinni.co/not-a-job-url", "Title") is None
    assert calls == []


def test_high_ceiling_uses_exponential_search_before_binary_search(monkeypatch):
    """Threshold above the first doubling step — exercises the exponential
    bracket-finding loop, not just the final binary-search narrowing."""
    threshold = 9000  # forces at least 3 doublings (500 -> 1000 -> 2000 -> 4000 -> ...)
    calls = {"count": 0}

    def fake_fetch(url: str):
        calls["count"] += 1
        salary = int(url.split("salary=")[1].split("&")[0])
        page = int(url.split("page=")[1])
        if page > 1:
            return _resp(_cards([]))
        return _resp(_cards([TARGET_ID] if salary <= threshold else []))

    monkeypatch.setattr(salary_probe, "fetch", fake_fetch)
    result = salary_probe.find_salary_ceiling(TARGET_URL, "Some Rare Title")
    assert result == threshold
    # Sanity bound on request volume — must stay far below a linear $500-step
    # walk to MAX_SALARY (40 requests), proving the exponential phase ran.
    assert calls["count"] < 15
