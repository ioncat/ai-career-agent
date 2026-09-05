"""
adapters/djinni_salary_adapter.py — async HTTP adapter for jd-parser's
Djinni hidden-salary estimator (services/parser/salary_probe.py).

Usage:
    adapter = DjinniSalaryAdapter(base_url="http://jd-parser:8001")
    ceiling = await adapter.find_salary_ceiling("https://djinni.co/jobs/123-x")
"""

import logging

import httpx

log = logging.getLogger(__name__)

# The probe runs several sequential, deliberately-throttled requests inside
# jd-parser (exponential + binary search, each with a 2-5s polite delay) —
# a single call here can legitimately take a minute or more. Same reasoning
# as ParserAdapter's timeout, just longer for this specific endpoint.
_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=5.0, pool=5.0)


class DjinniSalaryAdapter:
    """Async client for jd-parser's /djinni-salary-ceiling endpoint.

    Args:
        base_url: Base URL of jd-parser (e.g. "http://jd-parser:8001").
    """

    def __init__(self, base_url: str, timeout: httpx.Timeout = _TIMEOUT) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def find_salary_ceiling(self, vacancy_url: str) -> int | None:
        """Estimate a Djinni vacancy's real salary via its public search
        filter. Returns None on any failure or undeterminable result —
        callers should leave the existing salary field untouched, never
        treat None as an error to surface to the user (see docstring on the
        service endpoint for the full list of legitimate None cases).
        """
        endpoint = f"{self._base_url}/djinni-salary-ceiling"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(endpoint, json={"url": vacancy_url})
        except httpx.TransportError as exc:
            log.warning("DjinniSalaryAdapter: jd-parser unreachable for %r: %s", vacancy_url, exc)
            return None

        if resp.status_code != 200:
            log.warning(
                "DjinniSalaryAdapter: POST /djinni-salary-ceiling returned %d for %r",
                resp.status_code, vacancy_url,
            )
            return None

        return resp.json().get("ceiling")
