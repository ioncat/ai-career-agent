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

from adapters.djinni_salary_adapter import DjinniSalaryAdapter
from adapters.parser_adapter import ParserError
from core.deps import AgentDeps
from core.dedup import profile_key as company_profile_key
from core.vacancy_tags import classify as classify_tags
from core.vacancy_tags import merge_tags
from db import database

log = logging.getLogger(__name__)


class FetchError(Exception):
    """JD fetch failed — network, parser, or filesystem error."""


# Djinni's own structured "Vacancy Requirements" sidebar (merged into JD.md by
# services/parser, 2026-08-11 — same field cv_prefilter.py reads for the
# English/remote/country deterministic checks) lists a salary range as a bold
# bullet ("**$2000-3000**") right after the experience-requirement line, when
# the poster filled in Djinni's own salary field. Djinni's RSS feed never
# embeds salary in the item title or description (unlike DOU: "..., $1400–
# 1700, Київ") — job-monitor's salary extraction only ever reads the RSS
# title, so for Djinni this left `salary` NULL even though the poster's own
# value was sitting right there in the fetched page. Found live 2026-09-01,
# vacancy #1379 ("до $3000" / "$2000-3000" on the live page, JD.md already
# had it in the merged sidebar, `salary` column NULL).
_REQUIREMENTS_HEADING_RE = re.compile(r"##\s*Vacancy Requirements")
_SALARY_BULLET_RE = re.compile(r"\*\*\s*(\$\s*[\d,]+(?:\s*[-–—]\s*[\d,]+)?)\s*\*\*")
# Search window capped to the first 300 chars after the heading — the
# structured bullet cluster (experience/salary/remote/country) is a few short
# lines; anything past that is JD body prose that could contain an unrelated
# dollar figure (budget, revenue, another number).
_SALARY_SEARCH_WINDOW = 300


def _extract_salary_from_sidebar(jd_text: str) -> str | None:
    """Deterministic pre-check: does Djinni's structured requirements sidebar
    list a salary range? Returns None if absent or unparseable — never
    guesses from JD body prose.
    """
    m = _REQUIREMENTS_HEADING_RE.search(jd_text)
    if not m:
        return None
    window = jd_text[m.end():m.end() + _SALARY_SEARCH_WINDOW]
    salary_match = _SALARY_BULLET_RE.search(window)
    if not salary_match:
        return None
    return re.sub(r"\s+", "", salary_match.group(1))


# Fallback for postings with no structured sidebar (LinkedIn imports, older
# Djinni fetches predating the 2026-08-11 sidebar merge, or DOU — which never
# has one at all): a salary explicitly labeled in the JD body's benefits
# prose ("**Compensation:** $40 - $80/hour", "Зарплата: $1,200", "Вилка
# **$700–$1500**"). Deliberately requires an explicit label word directly
# adjacent to the $ figure — a bare unlabeled `$` anywhere in the body is too
# noisy to trust (company valuation, referral bonus, revenue/budget figures
# all matched during a 2026-09-01 audit of 60 candidate vacancies; only 15
# carried an explicit label, the other 45 were false leads). Takes the FIRST
# labeled match only — a JD naming a growth trajectory ("started at $1200,
# now earns $3000") reads as one label-adjacent match on the first figure,
# which is the closest available reading of "the offered rate", though this
# specific narrative shape (vacancy #308) is inherently ambiguous and was
# deliberately left out of the one-off 2026-09-01 backfill for that reason —
# a human call, not something the regex itself can resolve.
_LABELED_SALARY_RE = re.compile(
    r"(?:salary|compensation|зарплат\w*|вилк\w*|ставк\w*)"
    r"[^$\n]{0,40}"
    r"(\$\s*[\d,]+(?:\s*(?:per\s+month|/month|/hour)?\s*[-–—]\s*\$?\s*[\d,]+)?)",
    re.IGNORECASE,
)
_SALARY_UNIT_SUFFIX_RE = re.compile(r"per\s+month|/month|/hour", re.IGNORECASE)


def _extract_salary_from_labeled_text(jd_text: str) -> str | None:
    """Deterministic pre-check: does the JD body explicitly label a salary
    figure? Returns None if no label-adjacent $ amount is found.
    """
    m = _LABELED_SALARY_RE.search(jd_text)
    if not m:
        return None
    raw = _SALARY_UNIT_SUFFIX_RE.sub("", m.group(1))
    raw = raw.replace(",", "").replace(" ", "")
    return re.sub(r"[-–—]", "-", raw)


def _extract_salary(jd_text: str) -> str | None:
    """Best available salary signal: Djinni's structured sidebar first
    (higher confidence, poster-filled field), then a labeled mention in JD
    body prose as fallback.
    """
    return _extract_salary_from_sidebar(jd_text) or _extract_salary_from_labeled_text(jd_text)


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
        jd_file_text = f"# {doc.title}\n\nSource: {doc.source_url}\n\n---\n\n{doc.markdown}"
        jd_path.write_text(jd_file_text, encoding="utf-8")
    except OSError as exc:
        raise FetchError(f"Не удалось записать JD.md: {exc}") from exc

    log.info("fetch_jd: saved JD.md → %s", jd_path)

    # ── Update DB with final path and parsed fields ───────────────────────────
    # Done BEFORE duplicate detection (below) on purpose: the file is already
    # on disk at this point, so the DB should reflect that immediately. If
    # dedup lookup then fails, the vacancy is still fully usable (JD openable,
    # status transitions to 'fetched' below) instead of silently orphaned.
    markdown_path = str(jd_path)
    # Keyword-based segment tags (igaming/deftech/mobile/etc, see
    # core/vacancy_tags.py) — additive, never clobbers a manually-set tag.
    auto_tags = classify_tags(doc.markdown)
    tags = merge_tags(existing["tags"] if existing else None, auto_tags)
    # Only fill in salary if nothing already set it (job-monitor's DOU-title
    # extraction, or a user's manual edit) — never clobber a real value with
    # a sidebar re-read. A prior probe give-up note doesn't count as "already
    # set" (_is_real_salary) — a fresh fetch is another chance to find one.
    already_had_salary = bool(existing and _is_real_salary(existing["salary"]))
    salary = None if already_had_salary else _extract_salary(doc.markdown)
    if existing and existing["status"] in ("queued", "fetching"):
        await database.update_vacancy_fields(
            vacancy_id, title=doc.title, site=site, markdown_path=markdown_path,
            company=doc.company, tags=tags or None, salary=salary,
            company_profile_url=doc.company_profile_url,
        )
    else:
        await database.update_vacancy_fields(
            vacancy_id, markdown_path=markdown_path, tags=tags or None, salary=salary,
            company_profile_url=doc.company_profile_url,
        )

    # ── EPIC-26: content hash + duplicate detection ───────────────────────────
    # Non-fatal — a dedup failure shouldn't undo the successful fetch above.
    try:
        _norm_text = re.sub(r"\s+", " ", doc.markdown.lower())
        content_hash = hashlib.sha256(_norm_text.encode()).hexdigest()
        norm_title = database._normalize_title(doc.title or "", doc.company)
        # Two tiers (2026-10-05): a content-hash match, a title+company match
        # with similar JD text, or any recent vacancy with near-identical text
        # (>= TEXT_CONFIRM_THRESHOLD, whatever its title/company) is a
        # CONFIRMED duplicate (duplicate_of); a title+company match with
        # dissimilar/unreadable text is only a POSSIBLE one
        # (possible_duplicate_of). One classify call (the text scan is the
        # costly part). Re-evaluation sets one tier and clears the other (or
        # both, when nothing matches any more).
        verdict = await database.classify_duplicate(
            deps.user_id, content_hash, norm_title, doc.company or "",
            exclude_id=vacancy_id, new_text=jd_file_text,
            profile_key=company_profile_key(site, doc.company_profile_url),
        )
        if verdict.confirmed_id is not None:
            log.info("fetch_jd: duplicate of v#%d (%s) — marking v#%d",
                     verdict.confirmed_id, verdict.reason, vacancy_id)
            await database.set_duplicate_of(vacancy_id, verdict.confirmed_id)
        elif verdict.possible_id is not None:
            log.info("fetch_jd: possible duplicate of v#%d — marking v#%d", verdict.possible_id, vacancy_id)
            await database.set_possible_duplicate_of(vacancy_id, verdict.possible_id)
        else:
            await database.clear_duplicate_flags(vacancy_id)
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

    # Djinni salary estimate — fire-and-forget, off the critical path (2026-
    # 09-07), same pattern as company-website enrichment above. Only when
    # nothing (sidebar, labeled text, existing value) already found a real
    # number — a JD that discloses nothing gets Djinni's own hidden number
    # instead, via its public search filter (services/parser/salary_probe.py).
    if site == "djinni" and not already_had_salary and not salary and deps.djinni_salary_adapter:
        asyncio.create_task(
            _estimate_djinni_salary(deps.djinni_salary_adapter, vacancy_id, url)
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


# Global concurrency limit for the salary probe itself (2026-09-07, user
# request) — separate from RSS_CONCURRENCY (how many vacancies FETCH at
# once). fetch_jd() releases its own concurrency slot as soon as it
# returns, but the salary-probe background task it spawns keeps running for
# up to ~2.5 minutes afterward (MAX_TOTAL_REQUESTS × the polite delay) — a
# burst of many new vacancies discovered in one RSSWatcher poll cycle (a
# real pattern already seen in this project: a fresh feed subscription's
# catch-up scan once pulled in 85 vacancies in a single day) could spawn
# that many concurrent probes, each independently hitting Djinni — a much
# higher instantaneous request rate than any single probe's own internal
# polite delay implies, since that delay only paces one vacancy's own
# sequence of requests against itself, not against every other vacancy's
# probe running at the same time. Serializes the actual network-calling
# part to 1 at a time system-wide, so the per-request delay inside
# crawler.fetch() actually reflects the total load Djinni sees.
_DJINNI_SALARY_SEMAPHORE = asyncio.Semaphore(1)

# A give-up note (below) is written into the same free-text `salary` column
# as a real value or a successful estimate — no new schema needed — but it
# must never be mistaken for one. A leading "(" is a marker no real salary
# or the success format ("~$4000+ (Djinni filter estimate)") ever starts
# with (that one only ever has "(" mid-string); _is_real_salary() is the
# single place that distinction is checked, so every retry-eligibility
# check (fetch, republish, manual refetch) agrees on what counts as "still
# effectively empty". No literal "probe:"/source-name wording in the note
# itself (user feedback, 2026-09-07/08) — the user already knows which
# vacancy and site this is about; the note should just say what happened.
_PROBE_NOTE_PREFIX = "("
_REASON_NOTES = {
    "not_found": f"{_PROBE_NOTE_PREFIX}not a valid Djinni job link)",
    "no_company_link": f"{_PROBE_NOTE_PREFIX}no company page found on this listing — unusual, worth a manual look)",
    "not_on_company_page": f"{_PROBE_NOTE_PREFIX}company page doesn't list this vacancy — unusual, worth a manual look)",
    "budget_exhausted": f"{_PROBE_NOTE_PREFIX}search ran out of steps before narrowing down — worth a manual look)",
    "request_failed": f"{_PROBE_NOTE_PREFIX}network error — will retry)",
    "high_salary": f"{_PROBE_NOTE_PREFIX}~$10,000+ or no salary listed at all)",
}


def _is_real_salary(value: str | None) -> bool:
    """True for an actual disclosed figure or a successful Djinni estimate —
    False for empty or a probe give-up note (both retry-eligible: a future
    fetch/republish/manual refetch should try the probe again, not treat a
    note as if it were a real answer already on file)."""
    return bool(value) and not value.startswith(_PROBE_NOTE_PREFIX)


async def _estimate_djinni_salary(adapter: DjinniSalaryAdapter, vacancy_id: int, url: str) -> None:
    """Background enrichment: estimate a Djinni vacancy's real, possibly-
    undisclosed salary via its public search filter (2026-09-07, see
    services/parser/salary_probe.py for the technique — the user's own
    manual method turned into an exponential+binary search over Djinni's
    `salary=N` filter). Shared with web/api.py's republish-refresh and
    manual "Re-fetch from source" paths, which hit the exact same gap
    (found live, vacancy #902: republished, re-extraction correctly found
    no disclosed number in the text, and this estimate simply wasn't wired
    in anywhere yet).

    Slow by design — several deliberately-throttled requests inside the
    probe, can take up to about a minute — always fire-and-forget, never
    awaited inline with whatever triggered it. Serialized system-wide via
    _DJINNI_SALARY_SEMAPHORE — the internal per-request delay only paces
    one vacancy's own request sequence, not every OTHER vacancy's probe
    running at the same time (a burst of new vacancies could otherwise fire
    many concurrent probes at once). Re-checks the vacancy's
    salary is STILL not a real value right before writing (see
    _is_real_salary) — a manual edit or another source could fill in a real
    number during that delay, or a previous probe attempt could have left
    its own give-up note; neither should be clobbered by a stale-by-then
    write, though a fresh note is allowed to replace an older one.

    When undetermined, writes a short explanatory note (_REASON_NOTES)
    instead of leaving `salary` silently empty — found live 2026-09-07,
    user feedback: a silent empty field gives no signal that anything was
    even attempted, and no way to tell "genuinely nothing to find" apart
    from "the search itself couldn't resolve it, try checking by hand".

    Fail-open: never raises. An adapter-level failure (jd-parser
    unreachable, malformed response — reason=None) is a silent no-op, same
    as before; the probe's own classified outcomes (reason set) get a note.
    """
    try:
        async with _DJINNI_SALARY_SEMAPHORE:
            ceiling, reason = await adapter.find_salary_ceiling(url)
        current = await database.get_vacancy_by_id(vacancy_id)
        if current is None or _is_real_salary(current["salary"]):
            return
        if ceiling is not None:
            await database.set_vacancy_salary(vacancy_id, f"~${ceiling}+ (Djinni filter estimate)")
            log.info("djinni salary estimate: v#%d -> ~$%d+", vacancy_id, ceiling)
        elif reason is not None:
            note = _REASON_NOTES.get(reason)
            if note:
                await database.set_vacancy_salary(vacancy_id, note)
                log.info("djinni salary estimate: v#%d -> %s", vacancy_id, note)
    except Exception as exc:
        log.warning("djinni salary estimate failed for v#%d (non-fatal): %s", vacancy_id, exc)


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
