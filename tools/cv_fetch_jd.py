"""
tools/cv_fetch_jd.py — fetch and save a job description from a URL.

Pipeline step 0: URL → jd-parser → JD.md on disk + vacancy row in SQLite.

Tool registered in agent.py via ToolRegistry.
Receives shared dependencies via RunContext[AgentDeps].

Folder layout:
    vacancies/inbox/{user_id}/{slug}/JD.md   ← staging area until analyzed
    vacancies/{user_id}/{Role — Company}/     ← final location after analysis

Usage (by PydanticAI Agent, not called directly):
    # user sends URL → router calls this tool automatically
"""

import logging
import re
import time
from urllib.parse import urlparse

from pydantic_ai import RunContext

from adapters.parser_adapter import ParserError
from core.deps import AgentDeps
from db import database

log = logging.getLogger(__name__)


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
    log.info("cv_fetch_jd: url=%r", url)

    # ── Duplicate check ───────────────────────────────────────────────────────
    existing = await database.get_vacancy_by_url(url)
    if existing and existing["status"] not in ("queued", "fetching"):
        log.info("cv_fetch_jd: vacancy already in DB id=%d status=%s", existing["id"], existing["status"])
        return (
            f"ℹ️ Вакансия уже в базе.\n"
            f"<b>{existing['title'] or 'Без названия'}</b>\n"
            f"Статус: {existing['status']}"
        )
    # status='queued'/'fetching' → continue to fetch and fill it

    # ── Fetch via jd-parser ───────────────────────────────────────────────────
    t0 = time.monotonic()
    try:
        doc = await ctx.deps.parser_adapter.fetch_markdown(url)
        log.info("cv_fetch_jd: fetch done — elapsed=%.1fs title=%r", time.monotonic() - t0, doc.title)
    except ParserError as exc:
        log.error("cv_fetch_jd: ParserError after %.1fs: %s", time.monotonic() - t0, exc)
        return f"⚠️ Не удалось получить вакансию:\n{exc}"

    if doc.is_empty:
        return "⚠️ Страница получена, но не удалось извлечь текст. Попробуй другой URL."

    site = _detect_site(url)

    # ── Get vacancy_id before folder creation (needed for folder name) ────────
    if existing and existing["status"] in ("queued", "fetching"):
        vacancy_id = existing["id"]
        log.info("cv_fetch_jd: updating queued vacancy_id=%d", vacancy_id)
    else:
        try:
            vacancy_id = await database.insert_vacancy(
                url=url,
                title=doc.title,
                site=site,
                user_id=ctx.deps.user_id,
            )
        except Exception as exc:
            log.warning("cv_fetch_jd: insert failed (%s), fetching existing", exc)
            existing = await database.get_vacancy_by_url(url)
            vacancy_id = existing["id"] if existing else None

    # ── Build filesystem path ─────────────────────────────────────────────────
    company = doc.company
    if company and doc.title and company.lower() not in doc.title.lower():
        display_name = f"{doc.title} — {company}"
    else:
        display_name = doc.title or _url_slug(url)

    id_prefix = f"{vacancy_id} — " if vacancy_id else ""
    folder_name = _safe_folder_name(f"{id_prefix}{display_name}")

    vacancy_dir = ctx.deps.vacancies_path / "inbox" / str(ctx.deps.user_id) / folder_name
    vacancy_dir.mkdir(parents=True, exist_ok=True)
    jd_path = vacancy_dir / "JD.md"

    jd_path.write_text(
        f"# {doc.title}\n\nSource: {doc.source_url}\n\n---\n\n{doc.markdown}",
        encoding="utf-8",
    )
    log.info("cv_fetch_jd: saved JD.md → %s", jd_path)

    # ── Update DB with final path and parsed fields ───────────────────────────
    markdown_path = str(jd_path)
    if existing and existing["status"] in ("queued", "fetching"):
        await database.update_vacancy_fields(
            vacancy_id, title=doc.title, site=site, markdown_path=markdown_path,
        )
    else:
        await database.update_vacancy_fields(vacancy_id, markdown_path=markdown_path)

    log.info("cv_fetch_jd: vacancy_id=%s title=%r company=%r", vacancy_id, doc.title, company)

    return (
        f"✅ Вакансия сохранена!\n\n"
        f"<b>{doc.title}</b>\n"
        f"Сайт: {site} · ID: {vacancy_id}\n"
        f"Файл: <code>{jd_path}</code>\n\n"
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
    safe = safe.strip(". ").strip()
    return (safe or "vacancy")[:80]


def _url_slug(url: str) -> str:
    """Extract a filesystem-safe slug from the URL path (fallback when title unavailable)."""
    path = urlparse(url).path.rstrip("/")
    last_segment = path.split("/")[-1] if path else "vacancy"
    slug = re.sub(r"[^a-z0-9-]", "-", last_segment.lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return (slug or "vacancy")[:60]
