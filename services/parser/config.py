"""
config.py — Job board site configurations for career-agent parser service.

Stripped from knowledge-mirror-parser: only djinni.co + jobs.dou.ua retained.
Sitemap config, batch processing, and knowledge-mirror sites removed.
"""

# ── Scraper safety settings ───────────────────────────────────────────────────

REQUEST_DELAY_RANGE = (2, 5)   # seconds (min, max)
MAX_RETRIES = 3
RETRY_BACKOFF = 2              # exponential back-off multiplier

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]

# ── Job board site configs ────────────────────────────────────────────────────

SITES: dict = {
    "djinni.co": {
        "base_url": "https://djinni.co",
        "content_selector": ".job-post__description",
        "garbage_selectors": [
            "nav",
            "header",
            ".site-footer",
            ".fixed-bottom",
            ".modal-content",
            ".salaries-info-link",
            "script",
            "style",
            "iframe",
        ],
        # Structured poster-set criteria (years, remote, countries, language
        # levels, domain, employment type) — rendered unauthenticated, but a
        # sibling of content_selector, not nested inside it, so it was never
        # reaching JD.md (found 2026-08-11). Distinct from the *personalized*
        # profile-match card (also `.card.card-body`, extra `.mb-1` class) —
        # that one only renders for a logged-in session and never appears in
        # our always-anonymous fetch, so the broader selector below can't
        # collide with it in practice.
        "requirements_selector": "aside .card.card-body",
        "requirements_garbage_selectors": [
            "a",
            "button",
            ".btn",
            "script",
            "style",
        ],
        # Company profile page ("/jobs/company-{slug}/") link on the vacancy
        # page — a SEPARATE request from the vacancy page, only followed
        # later (2026-08-12, see BACKLOG.md — fetched off the critical path,
        # cached per company). Its public "Веб-сайт:" field is a distinct
        # thing from the ATS-connected "Company website:" block Djinni shows
        # some logged-in users directly on the vacancy page — that one is
        # login-gated and out of scope entirely.
        "company_link_selector": 'a[href*="/jobs/company-"]',
        "company_website_selector": 'a[data-analytics="company_page"]',
    },

    "jobs.dou.ua": {
        "base_url": "https://jobs.dou.ua",
        "content_selector": ".b-typo.vacancy-section",
        "garbage_selectors": [
            ".b-content-menu",
            ".b-jobs-search",
            ".b-dou-vacancies",
            "nav",
            "header",
            "footer",
            "script",
            "style",
            "iframe",
        ],
        # DOU's company profile URL is derivable directly from the vacancy
        # URL (strip the /vacancies/{id} suffix) — no DOM lookup needed on
        # the vacancy page itself, unlike Djinni's company_link_selector.
        "company_website_selector": ".company-info .site a",
    },
}


def get_site_cfg(site_key: str) -> dict:
    """Return config for a site key. Raises KeyError if unknown."""
    if site_key not in SITES:
        raise KeyError(f"No configuration for site: {site_key!r}")
    return SITES[site_key]
