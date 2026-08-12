"""
services/parser/test_app.py — tests for _parse_html()'s requirements-sidebar merge
and company website extraction.

Djinni renders a structured, unauthenticated requirements sidebar (years,
remote, countries, language levels, domain) as a SIBLING of content_selector
(.job-post__description), so it never reached JD.md before this fix
(found 2026-08-11, vacancy #1120 — see docs/delivery/BACKLOG.md). Distinct
from the personalized profile-match card, which only renders for a
logged-in session and is out of scope (never appears in our anonymous fetch).

Company website (2026-08-12): the vacancy page links to a SEPARATE company
profile page (fetched later, off the critical path — see cv_fetch_jd.py),
which has a public "Веб-сайт:"/".site a" field. Distinct from Djinni's
ATS-connected inline "Company website:" block, which is login-gated and
out of scope entirely (confirmed by the user).
"""

from bs4 import BeautifulSoup

from app import _extract_company_profile_url, _extract_company_website, _parse_html


_DJINNI_HTML = """
<html>
<head><title>Product Manager (IGaming) в Gypsy Collective – Djinni</title></head>
<body>
  <div class="job-post__description">
    <h1>Product Manager (IGaming)</h1>
    <p>We're Gypsy Collective. Looking for a Product Manager.</p>
  </div>
  <div class="col-lg-4">
    <aside>
      <div class="card card-body">
        <ul class="list-unstyled">
          <li><strong>Виключно від 4 років досвіду</strong></li>
          <li><strong>Тільки віддалено</strong></li>
          <li><span class="csc__primary">Англійська</span><span class="csc__secondary">B1 – Середній</span></li>
        </ul>
        <a class="btn" href="/apply">Відгукнутися на вакансію</a>
      </div>
    </aside>
  </div>
  <a href="/jobs/company-gypsy-collective/">Gypsy Collective</a>
</body>
</html>
"""

_DOU_HTML = """
<html>
<head><title>Product Manager — Company</title></head>
<body>
  <div class="b-typo vacancy-section">
    <h1>Product Manager</h1>
    <p>Join our team.</p>
  </div>
</body>
</html>
"""

_DJINNI_COMPANY_PAGE_HTML = """
<html><body>
  <div class="d-flex mt-3 align-items-center">
    <div class="me-2">Веб-сайт:</div>
    <a href="https://www.gypsy.co/" target="_blank" class="d-flex js-analytics-event"
       data-analytics="company_page">gypsy.co</a>
  </div>
</body></html>
"""

_DOU_COMPANY_PAGE_HTML = """
<html><body>
  <div class="company-info">
    <div class="site"><a href="https://paybis.com" target="_blank">paybis.com</a></div>
  </div>
</body></html>
"""


def test_parse_html_djinni_merges_requirements_into_markdown():
    title, markdown, company, company_profile_url = _parse_html(
        _DJINNI_HTML, "https://djinni.co/jobs/1/", "djinni.co"
    )
    assert "## Vacancy Requirements" in markdown
    assert "Виключно від 4 років досвіду" in markdown
    assert "Англійська" in markdown
    assert "B1 – Середній" in markdown


def test_parse_html_djinni_strips_buttons_from_requirements():
    _, markdown, _, _ = _parse_html(_DJINNI_HTML, "https://djinni.co/jobs/1/", "djinni.co")
    assert "Відгукнутися на вакансію" not in markdown


def test_parse_html_djinni_requirements_come_after_jd_body():
    _, markdown, _, _ = _parse_html(_DJINNI_HTML, "https://djinni.co/jobs/1/", "djinni.co")
    body_idx = markdown.find("Looking for a Product Manager")
    req_idx = markdown.find("## Vacancy Requirements")
    assert body_idx != -1
    assert req_idx != -1
    assert body_idx < req_idx


def test_parse_html_djinni_missing_sidebar_does_not_crash():
    html_no_sidebar = _DJINNI_HTML.replace(
        '<div class="col-lg-4">', '<div class="col-lg-4" style="display:none">'
    ).split("<aside>")[0] + "</body></html>"
    title, markdown, company, company_profile_url = _parse_html(
        html_no_sidebar, "https://djinni.co/jobs/1/", "djinni.co"
    )
    assert "## Vacancy Requirements" not in markdown
    assert "Looking for a Product Manager" in markdown


def test_parse_html_dou_unaffected_no_requirements_selector():
    """DOU has no requirements_selector configured — no heading, no crash."""
    title, markdown, company, company_profile_url = _parse_html(
        _DOU_HTML, "https://jobs.dou.ua/vacancies/1/", "jobs.dou.ua"
    )
    assert "## Vacancy Requirements" not in markdown
    assert "Join our team" in markdown


# ── company_profile_url extraction (2026-08-12) ─────────────────────────────

def test_parse_html_djinni_extracts_company_profile_url():
    _, _, _, company_profile_url = _parse_html(_DJINNI_HTML, "https://djinni.co/jobs/1/", "djinni.co")
    assert company_profile_url == "https://djinni.co/jobs/company-gypsy-collective/"


def test_parse_html_djinni_no_company_link_returns_none():
    html = _DJINNI_HTML.replace('<a href="/jobs/company-gypsy-collective/">Gypsy Collective</a>', "")
    _, _, _, company_profile_url = _parse_html(html, "https://djinni.co/jobs/1/", "djinni.co")
    assert company_profile_url is None


def test_parse_html_dou_derives_company_profile_url_from_vacancy_url():
    """DOU needs no DOM lookup — the company slug is already in the vacancy URL."""
    _, _, _, company_profile_url = _parse_html(
        _DOU_HTML, "https://jobs.dou.ua/companies/paybis-com/vacancies/369276/", "jobs.dou.ua"
    )
    assert company_profile_url == "https://jobs.dou.ua/companies/paybis-com/"


def test_extract_company_profile_url_unknown_site_returns_none():
    soup = BeautifulSoup(_DJINNI_HTML, "lxml")
    assert _extract_company_profile_url("https://example.com/jobs/1/", soup, None) is None


# ── _extract_company_website (2026-08-12) ───────────────────────────────────

def test_extract_company_website_djinni():
    soup = BeautifulSoup(_DJINNI_COMPANY_PAGE_HTML, "lxml")
    assert _extract_company_website(soup, "djinni.co") == "https://www.gypsy.co/"


def test_extract_company_website_dou():
    soup = BeautifulSoup(_DOU_COMPANY_PAGE_HTML, "lxml")
    assert _extract_company_website(soup, "jobs.dou.ua") == "https://paybis.com"


def test_extract_company_website_no_field_returns_none():
    """A company with no website filled in (e.g. an agency) — not an error,
    just absent."""
    soup = BeautifulSoup("<html><body><div>No website here</div></body></html>", "lxml")
    assert _extract_company_website(soup, "djinni.co") is None


def test_extract_company_website_unknown_site_returns_none():
    soup = BeautifulSoup(_DJINNI_COMPANY_PAGE_HTML, "lxml")
    assert _extract_company_website(soup, None) is None


def test_extract_company_website_djinni_skips_unrelated_nav_links_same_attribute():
    """Regression: Djinni reuses data-analytics="company_page" on multiple nav
    links (href="#") alongside the real website link — found live on Gypsy
    Collective's profile page. select_one() (selector-order) picked the
    wrong "#" match; must filter to the first real http(s) href instead."""
    html = """
    <html><body>
      <a data-analytics="company_page" class="nav-link js-company-jobs-link" href="#">Jobs</a>
      <a data-analytics="company_page" class="nav-link js-company-about-link" href="#">About</a>
      <div class="d-flex mt-3 align-items-center">
        <div class="me-2">Веб-сайт:</div>
        <a href="https://www.gypsy.co/" data-analytics="company_page" class="d-flex">gypsy.co</a>
      </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    assert _extract_company_website(soup, "djinni.co") == "https://www.gypsy.co/"
