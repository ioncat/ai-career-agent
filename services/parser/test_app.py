"""
services/parser/test_app.py — tests for _parse_html()'s requirements-sidebar merge.

Djinni renders a structured, unauthenticated requirements sidebar (years,
remote, countries, language levels, domain) as a SIBLING of content_selector
(.job-post__description), so it never reached JD.md before this fix
(found 2026-08-11, vacancy #1120 — see docs/delivery/BACKLOG.md). Distinct
from the personalized profile-match card, which only renders for a
logged-in session and is out of scope (never appears in our anonymous fetch).
"""

from app import _parse_html


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


def test_parse_html_djinni_merges_requirements_into_markdown():
    title, markdown, company = _parse_html(_DJINNI_HTML, "https://djinni.co/jobs/1/", "djinni.co")
    assert "## Vacancy Requirements" in markdown
    assert "Виключно від 4 років досвіду" in markdown
    assert "Англійська" in markdown
    assert "B1 – Середній" in markdown


def test_parse_html_djinni_strips_buttons_from_requirements():
    _, markdown, _ = _parse_html(_DJINNI_HTML, "https://djinni.co/jobs/1/", "djinni.co")
    assert "Відгукнутися на вакансію" not in markdown


def test_parse_html_djinni_requirements_come_after_jd_body():
    _, markdown, _ = _parse_html(_DJINNI_HTML, "https://djinni.co/jobs/1/", "djinni.co")
    body_idx = markdown.find("Looking for a Product Manager")
    req_idx = markdown.find("## Vacancy Requirements")
    assert body_idx != -1
    assert req_idx != -1
    assert body_idx < req_idx


def test_parse_html_djinni_missing_sidebar_does_not_crash():
    html_no_sidebar = _DJINNI_HTML.replace(
        '<div class="col-lg-4">', '<div class="col-lg-4" style="display:none">'
    ).split("<aside>")[0] + "</body></html>"
    title, markdown, company = _parse_html(html_no_sidebar, "https://djinni.co/jobs/1/", "djinni.co")
    assert "## Vacancy Requirements" not in markdown
    assert "Looking for a Product Manager" in markdown


def test_parse_html_dou_unaffected_no_requirements_selector():
    """DOU has no requirements_selector configured — no heading, no crash."""
    title, markdown, company = _parse_html(_DOU_HTML, "https://jobs.dou.ua/vacancies/1/", "jobs.dou.ua")
    assert "## Vacancy Requirements" not in markdown
    assert "Join our team" in markdown
