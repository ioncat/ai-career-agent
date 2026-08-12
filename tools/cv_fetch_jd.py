"""
tools/cv_fetch_jd — fetch and save a job description from a URL.

Pipeline step 0: URL → jd-parser → JD.md on disk + vacancy row in SQLite.

Public API:
  fetch_jd(deps, url) -> int          — core logic; returns vacancy_id; raises FetchError
  cv_fetch_jd(ctx, url) -> str        — PydanticAI tool wrapper (formats result for agent)

fetch_jd() is called by:
  - cv_fetch_jd (PydanticAI tool, via agent)
  - auto-pipeline orchestrator (RSS watcher, no agent involved)

Folder layout:
    vacancies/inbox/{user_id}/{id} — {role} — {company}/JD.md
"""

import asyncio
import hashlib
import logging
import re
import time
from urllib.parse import urlparse

from pydantic_ai import RunContext

from adapters.parser_adapter import ParserError
from core.deps import AgentDeps
from db import database

log = logging.getLogger(__name__)


class FetchError(Exception):
    """JD fetch failed — network, parser, or filesystem error."""


async def fetch_jd(deps: AgentDeps, url: str) -> int:
    """Fetch JD from URL, save to disk + DB. Returns vacancy_id.

    If URL already in DB (status not queued/fetching), returns its id immediately
    — no re-fetch. Callers (auto-pipeline) can still run analysis on it.

    If URL is queued or not in DB, fetches from jd-parser, saves JD.md,
    updates vacancy record.

    Args:
        deps: AgentDeps (user_id, parser_adapter, vacancies_path).
        url:  Full job posting URL.

    Returns:
        vacancy_id (int) — existing or newly inserted.

    Raises:
        FetchError: Parser failure, empty page, or filesystem error.
    """
    url = url.strip()
    log.info("fetch_jd: url=%r", url)

    # ── Duplicate / queued check ──────────────────────────────────────────────
    existing = await database.get_vacancy_by_url(url)
    if existing and existing["status"] not in ("queued", "fetching"):
        log.info("fetch_jd: already in DB id=%d status=%s", existing["id"], existing["status"])
        return existing["id"]

    # ── Fetch via jd-parser ───────────────────────────────────────────────────
    t0 = time.monotonic()
    try:
        doc = await deps.parser_adapter.fetch_markdown(url)
        log.info("fetch_jd: fetch done — %.1fs title=%r", time.monotonic() - t0, doc.title)
    except ParserError as exc:
        log.error("fetch_jd: ParserError after %.1fs: %s", time.monotonic() - t0, exc)
        raise FetchError(f"Не удалось получить вакансию:\n{exc}") from exc

    if doc.is_empty:
        raise FetchError("Страница получена, но не удалось извлечь текст. Попробуй другой URL.")

    site = _detect_site(url)

    # ── Get or create vacancy_id ──────────────────────────────────────────────
    if existing and existing["status"] in ("queued", "fetching"):
        vacancy_id = existing["id"]
        log.info("fetch_jd: updating queued vacancy_id=%d", vacancy_id)
    else:
        try:
            vacancy_id = await database.insert_vacancy(
                url=url,
                title=doc.title,
                site=site,
                user_id=deps.user_id,
                # Explicit — the schema default is 'fetched'. Without this, a
                # row inserted here is already "done" in the DB the instant it
                # exists, even though markdown_path is still NULL; any failure
                # below (dedup lookup, etc.) then leaves it permanently
                # orphaned — no retry mechanism ever revisits a 'fetched' row
                # (only 'fetching'/'queued' are covered by RSSWatcher's retry
                # loop and reset_stuck_statuses()). Found live 2026-08-11,
                # vacancy #106 stuck this way for a full day.
                status="fetching",
            )
        except Exception as exc:
            log.warning("fetch_jd: insert failed (%s), refetching existing", exc)
            row = await database.get_vacancy_by_url(url)
            if not row:
                raise FetchError(f"Не удалось сохранить вакансию в БД: {exc}") from exc
            vacancy_id = row["id"]

    # ── Build filesystem path ─────────────────────────────────────────────────
    company = doc.company
    if company and doc.title and company.lower() not in doc.title.lower():
        display_name = f"{doc.title} — {company}"
    else:
        display_name = doc.title or _url_slug(url)

    id_prefix = f"{vacancy_id} — " if vacancy_id else ""
    folder_name = _safe_folder_name(f"{id_prefix}{display_name}")

    vacancy_dir = deps.vacancies_path / "inbox" / str(deps.user_id) / folder_name
    try:
        vacancy_dir.mkdir(parents=True, exist_ok=True)
        jd_path = vacancy_dir / "JD.md"
        jd_path.write_text(
            f"# {doc.title}\n\nSource: {doc.source_url}\n\n---\n\n{doc.markdown}",
            encoding="utf-8",
        )
    except OSError as exc:
        raise FetchError(f"Не удалось записать JD.md: {exc}") from exc

    log.info("fetch_jd: saved JD.md → %s", jd_path)

    # ── Update DB with final path and parsed fields ───────────────────────────
    # Done BEFORE duplicate detection (below) on purpose: the file is already
    # on disk at this point, so the DB should reflect that immediately. If
    # dedup lookup then fails, the vacancy is still fully usable (JD openable,
    # status transitions to 'fetched' below) instead of silently orphaned.
    markdown_path = str(jd_path)
    if existing and existing["status"] in ("queued", "fetching"):
        await database.update_vacancy_fields(
            vacancy_id, title=doc.title, site=site, markdown_path=markdown_path,
            company=doc.company,
        )
    else:
        await database.update_vacancy_fields(vacancy_id, markdown_path=markdown_path)

    # ── EPIC-26: content hash + duplicate detection ───────────────────────────
    # Non-fatal — a dedup failure shouldn't undo the successful fetch above.
    try:
        _norm_text = re.sub(r"\s+", " ", doc.markdown.lower())
        content_hash = hashlib.sha256(_norm_text.encode()).hexdigest()
        original_id = await database.find_duplicate(
            deps.user_id,
            content_hash,
            database._normalize_title(doc.title or "", doc.company),
            doc.company or "",
            exclude_id=vacancy_id,
        )
        if original_id is not None:
            log.info("fetch_jd: duplicate of v#%d — marking v#%d", original_id, vacancy_id)
            await database.set_duplicate_of(vacancy_id, original_id)
        await database.set_content_hash(vacancy_id, content_hash)
    except Exception as exc:
        log.warning("fetch_jd: dedup step failed for v#%d (non-fatal): %s", vacancy_id, exc)

    await database.update_vacancy_status(vacancy_id, "fetched")

    # Company website — fire-and-forget, off the critical path (2026-08-12,
    # see BACKLOG.md). Never awaited here: the vacancy is already saved and
    # visible to the user by this point, and the website field is a nice-to-
    # have, not something anything downstream depends on.
    if doc.company and doc.company_profile_url:
        asyncio.create_task(
            _enrich_company_website(deps, vacancy_id, doc.company, doc.company_profile_url)
        )

    log.info("fetch_jd: done vacancy_id=%d title=%r", vacancy_id, doc.title)
    return vacancy_id


async def _enrich_company_website(
    deps: AgentDeps, vacancy_id: int, company: str, company_profile_url: str,
) -> None:
    """Background enrichment: cache-check first (companies post multiple
    vacancies over time, so most calls skip the fetch entirely), else fetch
    the company's separate profile page and persist its website.

    Fail-open — never raises. This is a nice-to-have field, not something
    the pipeline depends on; any error just logs.
    """
    try:
        cached = await database.get_company_website(company, deps.user_id)
        if cached:
            await database.update_vacancy_fields(vacancy_id, company_website=cached)
            log.info("fetch_jd: company_website cache hit for v#%d (%s)", vacancy_id, company)
            return
        website = await deps.parser_adapter.fetch_company_website(company_profile_url)
        if website:
            await database.update_vacancy_fields(vacancy_id, company_website=website)
            log.info("fetch_jd: company_website fetched for v#%d: %s", vacancy_id, website)
    except Exception as exc:
        log.warning("fetch_jd: company_website enrichment failed for v#%d (non-fatal): %s", vacancy_id, exc)


async def cv_fetch_jd(ctx: RunContext[AgentDeps], url: str) -> str:
    """Fetch and parse a job description from a Djinni, DOU, or LinkedIn URL.

    Saves the parsed markdown to disk as JD.md and registers the vacancy
    in the database. Call this first before running any analysis.

    Args:
        url: Full URL of the job posting (e.g. https://djinni.co/jobs/123/).

    Returns:
        Confirmation message with vacancy title and saved path.
    """
    url = url.strip()

    # ── Show "already in DB" message without re-fetching ─────────────────────
    existing = await database.get_vacancy_by_url(url)
    if existing and existing["status"] not in ("queued", "fetching"):
        log.info(
            "cv_fetch_jd: already in DB id=%d status=%s",
            existing["id"], existing["status"],
        )
        return (
            f"ℹ️ Вакансия уже в базе.\n"
            f"<b>{existing['title'] or 'Без названия'}</b>\n"
            f"Статус: {existing['status']}"
        )

    # ── Fetch ─────────────────────────────────────────────────────────────────
    try:
        vacancy_id = await fetch_jd(ctx.deps, url)
    except FetchError as exc:
        return f"⚠️ {exc}"

    # ── Format success message ────────────────────────────────────────────────
    vacancy = await database.get_vacancy_by_id(vacancy_id)
    if not vacancy:
        return f"✅ Вакансия #{vacancy_id} сохранена."

    return (
        f"✅ Вакансия сохранена!\n\n"
        f"<b>{vacancy['title'] or 'Без названия'}</b>\n"
        f"Сайт: {vacancy['site'] or '?'} · ID: {vacancy_id}\n"
        f"Файл: <code>{vacancy['markdown_path'] or '?'}</code>\n\n"
        f"Запускаем анализ?"
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _detect_site(url: str) -> str:
    """Classify URL into known site key."""
    netloc = urlparse(url).netloc.lower()
    if "djinni" in netloc:
        return "djinni"
    if "dou.ua" in netloc:
        return "dou"
    if "linkedin" in netloc:
        return "linkedin"
    return "other"


def _safe_folder_name(title: str) -> str:
    """Convert parsed JD title to a filesystem-safe folder name.

    Keeps spaces, dashes, dots, Cyrillic/Latin letters — removes only characters
    forbidden on Windows filesystems (< > : " / \\ | ? *) and trims to 80 chars.
    Falls back to 'vacancy' if result is empty.
    """
    safe = re.sub(r'[<>:"/\\|?*]', "", title)
    safe = safe.strip(". ").strip()[:80]
    safe = safe.strip(". ").strip()
    return safe or "vacancy"


def _url_slug(url: str) -> str:
    """Extract a filesystem-safe slug from the URL path (fallback when title unavailable)."""
    path = urlparse(url).path.rstrip("/")
    last_segment = path.split("/")[-1] if path else "vacancy"
    slug = re.sub(r"[^a-z0-9-]", "-", last_segment.lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return (slug or "vacancy")[:60]
