"""
services/parser/app.py — Job board URL → Markdown parser service.

Stripped from knowledge-mirror-parser/api.py: title updated, imports cleaned.
HTTP contract identical: POST /parse → ParsedDocument JSON.

Run:
    uvicorn app:app --host 0.0.0.0 --port 8001
"""

import logging
import re
from urllib.parse import urlparse

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


class ParsedDocument(BaseModel):
    title: str
    markdown: str
    source_url: str
    company: str | None = None


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

    # Djinni: page <title> is typically "Job Title — Company | Джинні"
    if site_key == "djinni.co":
        title_tag = soup.find("title")
        if title_tag:
            page_title = title_tag.get_text(strip=True)
            # Strip "| Джинні" / "| Djinni" suffix
            page_title = re.sub(r"\s*\|\s*(Джинні|Djinni)\s*$", "", page_title, flags=re.IGNORECASE).strip()
            # If page title starts with job title, the remainder is the company
            if title and page_title.lower().startswith(title.lower()):
                rest = page_title[len(title):].strip()
                rest = re.sub(r"^[\s\-—|]+", "", rest).strip()
                if rest:
                    return rest

    return None


def _parse_html(html: str, url: str, site_key: str | None) -> tuple[str, str, str | None]:
    soup = BeautifulSoup(html, "lxml")

    h1 = soup.find("h1")
    title_tag = soup.find("title")
    title = (
        h1.get_text(strip=True) if h1
        else title_tag.get_text(strip=True) if title_tag
        else "Untitled"
    )

    company = _extract_company(url, soup, site_key, title)

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
    else:
        log.info("No site config for %r — generic extraction", urlparse(url).netloc)
        content = soup.find("body") or soup
        for sel in ["nav", "header", "footer", "script", "style", "iframe"]:
            for el in content.select(sel):
                el.decompose()

    markdown = _to_markdown(str(content)).strip()
    return title, markdown, company


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
    title, markdown, company = _parse_html(resp.text, req.url, site_key)

    if not markdown:
        raise HTTPException(
            status_code=503,
            detail={"error": "parse_failed", "url": req.url},
        )

    return ParsedDocument(title=title, markdown=markdown, source_url=req.url, company=company)
