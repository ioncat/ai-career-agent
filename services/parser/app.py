"""
services/parser/app.py — Job board URL → Markdown parser service.

Stripped from knowledge-mirror-parser/api.py: title updated, imports cleaned.
HTTP contract identical: POST /parse → ParsedDocument JSON.

Run:
    uvicorn app:app --host 0.0.0.0 --port 8001
"""

import json
import logging
import re
from urllib.parse import urljoin, urlparse

import html2text
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import salary_probe
from config import SITES
from crawler import fetch
from salary_probe import find_salary_ceiling

log = logging.getLogger(__name__)

app = FastAPI(title="career-agent parser", version="1.0.0")


# ── Contracts ─────────────────────────────────────────────────────────────────

class ParseRequest(BaseModel):
    url: str


class CompanyWebsiteRequest(BaseModel):
    url: str  # company profile page URL, not a vacancy URL


class DjinniSalaryCeilingRequest(BaseModel):
    url: str  # vacancy URL — Djinni only, caller's responsibility to check site


class ParsedDocument(BaseModel):
    title: str
    markdown: str
    source_url: str
    company: str | None = None
    # Company profile page URL (e.g. "/jobs/company-{slug}/" on Djinni,
    # "/companies/{slug}/" on DOU) — a SEPARATE page from the vacancy itself.
    # Fetched later, off the critical path (see fetch_company_website below
    # and tools/cv_fetch_jd.py) — never fetched inline with /parse.
    company_profile_url: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _match_site_key(url: str) -> str | None:
    netloc = urlparse(url).netloc.lstrip("www.")
    for key in SITES:
        if netloc == key or netloc.endswith("." + key):
            return key
    return None


def _to_markdown(html_str: str) -> str:
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.body_width = 0
    h.unicode_snob = True
    h.escape_snob = True
    return h.handle(html_str)


def _extract_company(url: str, soup: BeautifulSoup, site_key: str | None, title: str) -> str | None:
    """Extract employer/company name from page. Returns None if unavailable."""
    # DOU: company slug always present in URL path /companies/{slug}/vacancies/...
    if site_key == "jobs.dou.ua":
        m = re.search(r"/companies/([^/]+)/", url)
        if m:
            return m.group(1).replace("-", " ").title()

    # Djinni: page <title> is either "Job Title — Company | Джинні"
    # or (Ukrainian locale) "Job Title в Company – Djinni"
    if site_key == "djinni.co":
        title_tag = soup.find("title")
        if title_tag:
            page_title = title_tag.get_text(strip=True)
            # Strip trailing "| Djinni" / "— Djinni" / "– Djinni" (with or without pipe/dash)
            page_title = re.sub(r"\s*[|\-–—]?\s*(Джинні|Djinni)\s*$", "", page_title, flags=re.IGNORECASE).strip()
            # If page title starts with job title, the remainder is the company
            if title and page_title.lower().startswith(title.lower()):
                rest = page_title[len(title):].strip()
                rest = re.sub(r"^[\s\-—|]+", "", rest).strip()
                # Ukrainian/Russian preposition "в"/"у" ("at <company>")
                rest = re.sub(r"^(?:в|у)\s+", "", rest, flags=re.IGNORECASE).strip()
                if rest:
                    return rest

    return None


def _extract_company_profile_url(url: str, soup: BeautifulSoup, site_key: str | None) -> str | None:
    """Return the company profile page URL (a SEPARATE page from the
    vacancy) — fetched later, off the critical path, never inline here.

    DOU encodes the company slug in the vacancy URL itself
    (/companies/{slug}/vacancies/{id}) — no DOM lookup needed.
    Djinni requires following a DOM link (company_link_selector).
    """
    if site_key == "jobs.dou.ua":
        m = re.match(r"^(https?://[^/]+/companies/[^/]+/)", url)
        return m.group(1) if m else None

    if site_key == "djinni.co":
        cfg = SITES.get(site_key, {})
        selector = cfg.get("company_link_selector")
        if selector:
            link = soup.select_one(selector)
            if link and link.get("href"):
                return urljoin(cfg.get("base_url", url), link["href"])

    return None


def _extract_djinni_category(soup: BeautifulSoup) -> str | None:
    """Djinni's own `primary_keyword` category for this specific vacancy
    (e.g. "Product Manager", "Business Analyst") — read straight from its
    schema.org JobPosting JSON-LD block (standard SEO markup, confirmed
    present with a clean single-string `category` field on 15/15 vacancies
    sampled live 2026-09-08), never inferred from the title. A hardcoded
    guess here (an earlier version filtered every company page by
    "Product Owner"/"Product Manager" only) silently broke the moment the
    feed started ingesting any other role — this reads Djinni's actual
    answer instead, so it stays correct for any category without a mapping
    table to maintain. Returns None if the block is missing or malformed —
    salary_probe then searches the company page unfiltered rather than
    guessing.
    """
    script = soup.find("script", type="application/ld+json")
    if not script or not script.string:
        return None
    try:
        data = json.loads(script.string)
    except (json.JSONDecodeError, TypeError):
        return None
    category = data.get("category") if isinstance(data, dict) else None
    return category if isinstance(category, str) and category.strip() else None


def _extract_company_website(soup: BeautifulSoup, site_key: str | None) -> str | None:
    """Extract the external website link from a company PROFILE page
    (not a vacancy page) — a public, unauthenticated field on both sites.

    Djinni reuses the same `data-analytics="company_page"` attribute on
    multiple unrelated nav links (href="#") alongside the real website link
    — found live on Gypsy Collective's profile page, `select_one` picked the
    first (wrong, "#") match. Filters to the first match with a real http(s)
    href instead of trusting selector-match order.
    """
    if not site_key or site_key not in SITES:
        return None
    selector = SITES[site_key].get("company_website_selector")
    if not selector:
        return None
    for link in soup.select(selector):
        href = link.get("href", "").strip()
        if href.startswith("http"):
            return href
    return None
    return None


def _parse_html(html: str, url: str, site_key: str | None) -> tuple[str, str, str | None, str | None]:
    soup = BeautifulSoup(html, "lxml")

    h1 = soup.find("h1")
    title_tag = soup.find("title")
    title = (
        h1.get_text(strip=True) if h1
        else title_tag.get_text(strip=True) if title_tag
        else "Untitled"
    )

    company = _extract_company(url, soup, site_key, title)
    company_profile_url = _extract_company_profile_url(url, soup, site_key)

    requirements_markdown = ""
    if site_key and site_key in SITES:
        cfg = SITES[site_key]
        content = soup.select_one(cfg["content_selector"])
        if content is None:
            log.warning("content_selector %r not found on %s — falling back to <body>",
                        cfg["content_selector"], url)
            content = soup.find("body") or soup
        for sel in cfg.get("garbage_selectors", []):
            for el in content.select(sel):
                el.decompose()

        req_selector = cfg.get("requirements_selector")
        if req_selector:
            req_el = soup.select_one(req_selector)
            if req_el is not None:
                for sel in cfg.get("requirements_garbage_selectors", []):
                    for el in req_el.select(sel):
                        el.decompose()
                requirements_markdown = _to_markdown(str(req_el)).strip()
    else:
        log.info("No site config for %r — generic extraction", urlparse(url).netloc)
        content = soup.find("body") or soup
        for sel in ["nav", "header", "footer", "script", "style", "iframe"]:
            for el in content.select(sel):
                el.decompose()

    markdown = _to_markdown(str(content)).strip()
    if requirements_markdown:
        markdown = f"{markdown}\n\n## Vacancy Requirements\n\n{requirements_markdown}"
    return title, markdown, company, company_profile_url


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/parse", response_model=ParsedDocument)
def parse(req: ParseRequest) -> ParsedDocument:
    """Fetch URL and return clean Markdown with title."""
    resp = fetch(req.url)
    if resp is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "fetch_failed", "url": req.url},
        )

    site_key = _match_site_key(req.url)
    title, markdown, company, company_profile_url = _parse_html(resp.text, req.url, site_key)

    if not markdown:
        raise HTTPException(
            status_code=503,
            detail={"error": "parse_failed", "url": req.url},
        )

    return ParsedDocument(
        title=title, markdown=markdown, source_url=req.url, company=company,
        company_profile_url=company_profile_url,
    )


@app.post("/company-website")
def company_website(req: CompanyWebsiteRequest) -> dict:
    """Fetch a company PROFILE page (not a vacancy) and extract its public
    website link. Deliberately separate from /parse — called later, off the
    critical path, only for companies not already cached (see
    tools/cv_fetch_jd.py, db.database.get_company_website).

    Returns {"website": str | None} — None (not a 404/503) when the page
    fetches fine but has no website field, since that's a normal, common
    outcome (agencies without a direct client site), not an error.
    """
    resp = fetch(req.url)
    if resp is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "fetch_failed", "url": req.url},
        )

    site_key = _match_site_key(req.url)
    soup = BeautifulSoup(resp.text, "lxml")
    return {"website": _extract_company_website(soup, site_key)}


@app.post("/djinni-salary-ceiling")
def djinni_salary_ceiling(req: DjinniSalaryCeilingRequest) -> dict:
    """Estimate a Djinni vacancy's real (possibly undisclosed) salary by
    probing Djinni's own public search filter (see salary_probe.py) —
    NOT the personalized login-gated profile-match panel, which this
    service never fetches.

    Fetches the vacancy page once before starting the probe, so an
    already-expired listing is caught in a single request rather than after
    a wasted salary-search sequence. Extracts the company's own Djinni page
    URL (`company_link_selector`) — the only identification method
    (2026-09-08, simplified from an earlier two-strategy design): every
    vacancy belongs to some posting account's own page, same technique the
    user does by hand — open the vacancy, follow the link to the company's
    page, apply the salary filter there. No title-based fallback — the job
    title plays no role in identification at all, only the internal job ID
    matched against the company page's HTML. Also extracts Djinni's own
    `category` for this vacancy (`_extract_djinni_category` — schema.org
    JSON-LD, e.g. "Product Manager"/"Business Analyst") to narrow a busy
    employer's page, when present — read from Djinni's own data, never
    inferred from the title.

    Returns {"ceiling": int | None, "reason": str | None}. reason is always
    None when ceiling is found; otherwise one of salary_probe.REASON_* —
    lets the caller leave a short explanatory note instead of silence.
    Never a guess. Slow by design (multiple polite, rate-limited requests
    inside salary_probe's exponential+binary search) — call off the
    critical path.
    """
    resp = fetch(req.url)
    if resp is None:
        return {"ceiling": None, "reason": salary_probe.REASON_REQUEST_FAILED}

    m = re.search(r"/jobs/(\d+)-", req.url)
    if not m:
        return {"ceiling": None, "reason": salary_probe.REASON_NOT_FOUND}

    soup = BeautifulSoup(resp.text, "lxml")
    if not soup.find("h1"):
        # Doesn't look like a real vacancy page (e.g. an expired listing
        # redirected elsewhere) — nothing to identify a company page from.
        return {"ceiling": None, "reason": salary_probe.REASON_NOT_FOUND}

    site_key = _match_site_key(req.url)
    company_profile_url = _extract_company_profile_url(req.url, soup, site_key)
    category = _extract_djinni_category(soup) if site_key == "djinni.co" else None

    ceiling, reason = find_salary_ceiling(req.url, company_profile_url, category)
    return {"ceiling": ceiling, "reason": reason}
