"""
core/rss_watcher.py — Background watcher: polls DB for queued vacancies, triggers cv_fetch_jd.

New vacancies arrive via POST /api/new-vacancy (from job-monitor service) which
inserts them into the DB with status='queued'. This watcher picks them up and
runs the fetch+parse pipeline.

Replaces the old file-polling approach (seen_jobs.json) with DB-based event delivery.

Lifecycle (in agent.py):
    watcher = RSSWatcher(deps, bot, poll_interval=30)
    await watcher.start()
    # ... bot runs ...
    await watcher.stop()
"""

import asyncio
import logging
import re
from contextlib import suppress
from dataclasses import dataclass

from core.deps import AgentDeps
from db import database

log = logging.getLogger(__name__)

# Salary extraction — matches DOU/Djinni RSS titles embedding salary in plain text.
# Examples: "$2000", "$1500–2500", "$1500-2500", "$1 500 – 2 500"
SALARY_RE = re.compile(r"\$\s*\d[\d\s]{0,4}(?:\s*[–—\-]\s*\d[\d\s]{0,4})?")


def _extract_salary(text: str) -> str:
    """Return salary string (e.g. '$2000–3200') if found in text, else empty string."""
    m = SALARY_RE.search(text)
    if not m:
        return ""
    return re.sub(r"\s+", "", m.group())  # collapse internal spaces: "$2 000" → "$2000"


@dataclass
class _Ctx:
    """Minimal RunContext[AgentDeps] stand-in for calling tools outside PydanticAI agent."""
    deps: AgentDeps


class RSSWatcher:
    """Polls DB for status='queued' vacancies and triggers cv_fetch_jd for each.

    Runs as a background asyncio.Task. Vacancies are inserted by the
    POST /api/new-vacancy endpoint (job-monitor webhook).
    """

    def __init__(
        self,
        deps: AgentDeps,
        telegram_bot: object,   # TelegramBot — avoids circular import
        poll_interval: int = 30,
    ) -> None:
        self._deps = deps
        self._bot = telegram_bot
        self._interval = poll_interval
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Launch background polling task."""
        self._task = asyncio.create_task(self._run(), name="rss-watcher")
        log.info(
            "RSSWatcher: started — polling DB for queued vacancies every %ds",
            self._interval,
        )

    async def stop(self) -> None:
        """Cancel the polling task and wait for it to exit cleanly."""
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            log.info("RSSWatcher: stopped")

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _run(self) -> None:
        """Polling loop — runs until cancelled."""
        while True:
            await asyncio.sleep(self._interval)
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("RSSWatcher: unexpected error in poll loop: %s", exc)

    async def _poll_once(self) -> None:
        """Query DB for queued vacancies and process all concurrently."""
        rows = await database.list_vacancies(
            status="queued",
            user_id=self._deps.user_id,
        )
        if not rows:
            return

        log.info("RSSWatcher: %d queued vacancy(s) found", len(rows))

        # Claim all first (sequential — avoid double-processing races)
        for row in rows:
            await database.update_vacancy_status(row["id"], "fetching")

        # Notify + fetch all concurrently
        results = await asyncio.gather(
            *[self._process(row["url"], rss_title=row["title"] or "") for row in rows],
            return_exceptions=True,
        )
        for row, exc in zip(rows, results):
            if isinstance(exc, Exception):
                log.error("RSSWatcher: failed %s: %s", row["url"], exc)

    @staticmethod
    def _source_label(url: str) -> str:
        from urllib.parse import urlparse
        netloc = urlparse(url).netloc.lower()
        if "djinni" in netloc:
            return "Djinni"
        if "dou.ua" in netloc:
            return "DOU.ua"
        if "linkedin" in netloc:
            return "LinkedIn"
        return netloc

    async def _process(self, url: str, rss_title: str = "") -> None:
        """Notify Telegram immediately, then fetch/parse the JD in background.

        Notification is always sent first — independent of parser availability.
        Parse failures are logged but not surfaced to the user (they already have the URL).
        """
        from tools.cv_fetch_jd import cv_fetch_jd  # local import to avoid circular

        source = self._source_label(url)
        display = rss_title or url
        salary = _extract_salary(rss_title) if rss_title else ""
        salary_line = f"💰 <b>{salary}</b>\n" if salary else ""

        # Notify FIRST — user sees the vacancy immediately
        await self._bot.send_message(  # type: ignore[union-attr]
            f"🆕 <b>Новая вакансия</b>\n"
            f"{salary_line}"
            f"🔍 {source}\n"
            f'📌 <a href="{url}">{display}</a>'
        )

        # Parse JD in background — vacancy is already in DB as 'fetching'
        log.info("RSSWatcher: fetching JD - %s", url)
        ctx = _Ctx(deps=self._deps)
        try:
            await cv_fetch_jd(ctx, url)  # type: ignore[arg-type]
        except Exception as exc:
            log.error("RSSWatcher: failed to fetch JD %s: %s", url, exc)
