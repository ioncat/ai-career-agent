"""
services/parser/app.py — Job board URL → Markdown parser service.

Stripped from knowledge-mirror-parser/api.py: title updated, imports cleaned.
HTTP contract identical: POST /parse → ParsedDocument JSON.

Run:
    uvicorn app:app --host 0.0.0.0 --port 8001
"""

import logging
import re
from urllib.parse import urljoin, urlparse

import html2text
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from config import SITES
from crawler import fetch

log = logging.getLogger(__name__)

app = FastAPI(title="career-agent parser", version="1.0.0")


# ── Contracts ─────────────────────────────────────────────────────────────────

class ParseRequest(BaseModel):
    url: str


class CompanyWebsiteRequest(BaseModel):
    url: str  # company profile page URL, not a vacancy URL


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
