"""
adapters/djinni_salary_adapter.py — async HTTP adapter for jd-parser's
Djinni hidden-salary estimator (services/parser/salary_probe.py).

Usage:
    adapter = DjinniSalaryAdapter(base_url="http://jd-parser:8001")
    ceiling, reason = await adapter.find_salary_ceiling("https://djinni.co/jobs/123-x")
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

    async def find_salary_ceiling(self, vacancy_url: str) -> tuple[int | None, str | None]:
        """Estimate a Djinni vacancy's real salary via its public search
        filter.

        Returns (ceiling, reason). ceiling is None on any failure or
        undeterminable result — callers should leave a real, already-set
        salary untouched regardless of what comes back here. reason is one
        of services/parser/salary_probe.py's REASON_* strings when ceiling
        is None (so a caller can leave a short explanatory note instead of
        silence), or None when this adapter itself couldn't even reach
        jd-parser or get a well-formed response — a genuine unknown, not one
        of the probe's own classified outcomes.
        """
        endpoint = f"{self._base_url}/djinni-salary-ceiling"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(endpoint, json={"url": vacancy_url})
        except httpx.TransportError as exc:
            log.warning("DjinniSalaryAdapter: jd-parser unreachable for %r: %s", vacancy_url, exc)
            return None, None

        if resp.status_code != 200:
            log.warning(
                "DjinniSalaryAdapter: POST /djinni-salary-ceiling returned %d for %r",
                resp.status_code, vacancy_url,
            )
            return None, None

        body = resp.json()
        return body.get("ceiling"), body.get("reason")
