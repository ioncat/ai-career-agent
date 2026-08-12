"""
adapters/parser_adapter.py — async HTTP adapter for jd-parser service.

All calls to the job-board URL→Markdown parser go through this class.

Usage:
    adapter = ParserAdapter(base_url="http://jd-parser:8001")
    doc = await adapter.fetch_markdown("https://djinni.co/jobs/123/")
"""

import logging

import httpx

from contracts.parsed_document import ParsedDocument

log = logging.getLogger(__name__)

# Timeouts: connect fast, allow up to 30s for slow sites
_DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)


class ParserError(Exception):
    """Raised when jd-parser returns an error or is unreachable."""

    def __init__(self, message: str, url: str, status_code: int | None = None):
        super().__init__(message)
        self.url = url
        self.status_code = status_code


class ParserAdapter:
    """Async client for jd-parser HTTP service.

    Args:
        base_url: Base URL of jd-parser (e.g. "http://jd-parser:8001").
                  Read from PARSER_URL env var via config; injected here.
        timeout:  httpx Timeout object. Override in tests.
    """

    def __init__(
        self,
        base_url: str,
        timeout: httpx.Timeout = _DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def fetch_markdown(self, url: str) -> ParsedDocument:
        """Fetch and parse a URL via jd-parser.

        Args:
            url: Target page URL (Djinni/DOU job posting or any public URL).

        Returns:
            ParsedDocument with title, clean markdown, and source_url.

        Raises:
            ParserError: jd-parser unreachable, returned 5xx, or parse failed.
        """
        endpoint = f"{self._base_url}/parse"
        log.debug("ParserAdapter.fetch_markdown → POST %s body=%r", endpoint, url)

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(endpoint, json={"url": url})
        except httpx.TransportError as exc:
            raise ParserError(
                f"jd-parser unreachable: {exc}",
                url=url,
            ) from exc

        if resp.status_code != 200:
            detail = _extract_detail(resp)
            log.error(
                "ParserAdapter: POST /parse returned %d for %r — %s",
                resp.status_code, url, detail,
            )
            raise ParserError(
                f"jd-parser error {resp.status_code}: {detail}",
                url=url,
                status_code=resp.status_code,
            )

        doc = ParsedDocument.model_validate(resp.json())
        log.debug("ParserAdapter: parsed %r → title=%r, md_len=%d", url, doc.title, len(doc.markdown))
        return doc

    async def fetch_company_website(self, company_profile_url: str) -> str | None:
        """Fetch a company PROFILE page (not a vacancy) and return its public
        website link, or None if the page has no such field (a common,
        normal outcome — not an error).

        Called off the critical path (tools/cv_fetch_jd.py, fire-and-forget,
        only for companies not already cached — see
        db.database.get_company_website) — never awaited inline with the
        main JD fetch.

        Raises:
            ParserError: jd-parser unreachable or returned 5xx. A 200 with
            website=null is NOT an error — callers should treat that as
            "no website on file", same as any other missing field.
        """
        endpoint = f"{self._base_url}/company-website"
        log.debug("ParserAdapter.fetch_company_website → POST %s body=%r", endpoint, company_profile_url)

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(endpoint, json={"url": company_profile_url})
        except httpx.TransportError as exc:
            raise ParserError(
                f"jd-parser unreachable: {exc}",
                url=company_profile_url,
            ) from exc

        if resp.status_code != 200:
            detail = _extract_detail(resp)
            log.error(
                "ParserAdapter: POST /company-website returned %d for %r — %s",
                resp.status_code, company_profile_url, detail,
            )
            raise ParserError(
                f"jd-parser error {resp.status_code}: {detail}",
                url=company_profile_url,
                status_code=resp.status_code,
            )

        return resp.json().get("website")

    async def health(self) -> bool:
        """Check if jd-parser is alive. Returns True if healthy."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                resp = await client.get(f"{self._base_url}/health")
            return resp.status_code == 200
        except httpx.TransportError:
            return False


def _extract_detail(resp: httpx.Response) -> str:
    """Pull error detail string from JSON body or fall back to raw text."""
    try:
        body = resp.json()
        if isinstance(body, dict):
            return body.get("detail") or body.get("error") or str(body)
        return str(body)
    except Exception:
        return resp.text[:200]
