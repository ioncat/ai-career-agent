"""
db/database.py — async SQLite layer via aiosqlite.

All DB access in career-agent goes through this module.
Never write raw SQL in tools or adapters — use helpers here.

Usage:
    # startup
    await init_db()

    # read/write
    async with get_db() as db:
        row = await db.execute("SELECT * FROM vacancies WHERE id = ?", (vid,))
        ...
"""

import json
import logging
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import urlparse, urlunparse

import aiosqlite

from core.dedup import (
    CONFIRM_THRESHOLD,
    TEXT_CONFIRM_THRESHOLD,
    TEXT_SCAN_WINDOW_DAYS,
    build_link_graph,
    compute_applied_twins,
    compute_company_applied,
    in_text_window,
    parse_as_of,
    row_profile_key,
    same_company,
    score_candidates,
)

log = logging.getLogger(__name__)

# Default DB path — override via DB_PATH env var or settings
_DEFAULT_DB_PATH = Path(__file__).parent / "agent.db"
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()

_db_path: Path = _DEFAULT_DB_PATH


def configure(db_path: str | Path) -> None:
    """Set DB path before first call to init_db(). Called from agent.py on startup."""
    global _db_path
    _db_path = Path(db_path)


def normalize_url(url: str) -> str:
    """Return canonical URL for dedup: lowercase host, strip query/fragment/trailing slash.

    Job board IDs are always in the path (Djinni, DOU, LinkedIn) — query params
    are only tracking noise (utm_source, trk, refId, pk_campaign, etc.).
    Stripping the entire query string is safe for all supported boards.

    Examples:
        https://jobs.dou.ua/vacancies/123/?utm_source=jobsrss  →  https://jobs.dou.ua/vacancies/123
        https://linkedin.com/jobs/view/456/?trk=abc&refId=xyz  →  https://linkedin.com/jobs/view/456
        https://djinni.co/jobs/789/?ref=tg_bot                 →  https://djinni.co/jobs/789
    """
    stripped = url.strip()
    if not stripped:
        return stripped
    try:
        p = urlparse(stripped)
        # Normalise: lowercase scheme+host, strip path trailing slash, drop query+fragment
        host = p.netloc.lower()
        path = p.path.rstrip("/") or "/"
        # deftech.dou.ua is a separate host mirroring the exact same postings
        # already on jobs.dou.ua (same vacancy id in the path, just prefixed
        # with an extra "/jobs" segment there) — DOU's own DefTech category
        # page, not a distinct site. Without this, the two hosts never
        # collapse to the same canonical URL, so get_vacancy_by_url() can't
        # find the existing row and every deftech.dou.ua posting silently
        # inserts a second, undetected duplicate. Found live 2026-09-02: all
        # 4 deftech.dou.ua rows in the DB (#1303, #1336, #1337, #1338) had an
        # un-linked jobs.dou.ua twin, 3 of them applied-to vacancies with a
        # separate un-flagged "new" duplicate sitting in Inbox.
        if host == "deftech.dou.ua":
            host = "jobs.dou.ua"
            if path.startswith("/jobs/"):
                path = path[len("/jobs"):]
        return urlunparse((p.scheme.lower(), host, path, "", "", ""))
    except Exception:
        return stripped


def extract_site(url: str) -> str:
    """Infer site identifier from URL hostname.

    Returns: 'djinni' | 'dou' | 'linkedin' | 'hh' | 'other'
    Used when inserting local-mode vacancies that have no explicit site argument.
    """
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return "other"
    if "djinni" in host:
        return "djinni"
    if "dou.ua" in host:
        return "dou"
    if "linkedin" in host:
        return "linkedin"
    if "hh.ua" in host or "hh.ru" in host:
        return "hh"
    return "other"


async def init_db() -> None:
    """Create DB file and apply schema. Idempotent — safe to call on every startup."""
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    schema = _SCHEMA_PATH.read_text(encoding="utf-8")

    async with aiosqlite.connect(_db_path) as db:
        await db.executescript(schema)
        # Migrations: add columns introduced after initial schema
        for migration in [
            "ALTER TABLE vacancies ADD COLUMN warnings TEXT NOT NULL DEFAULT ''",
            # llm_usage granular breakdown (added after initial schema)
            "ALTER TABLE llm_usage ADD COLUMN profile_tokens  INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE llm_usage ADD COLUMN prompt_tokens   INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE llm_usage ADD COLUMN user_tokens     INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE llm_usage ADD COLUMN budget_tokens   INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE llm_usage ADD COLUMN thinking_tokens INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE llm_usage ADD COLUMN elapsed_ms      INTEGER NOT NULL DEFAULT 0",
            # Multi-user: user_id FK (nullable — existing rows remain valid, NULL = user_id=1)
            "ALTER TABLE vacancies ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL",
            "ALTER TABLE vacancies ADD COLUMN salary TEXT",
            "ALTER TABLE llm_usage ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL",
            # EPIC-17: onboarding profile storage
            "ALTER TABLE users ADD COLUMN profile_json TEXT",
            "ALTER TABLE users ADD COLUMN onboarding_step TEXT",
            # Structured pipeline data per phase (component-based CV assembly foundation)
            "ALTER TABLE vacancies ADD COLUMN analysis_json TEXT",
            # Applied flag: 1 = CV submitted to this vacancy
            "ALTER TABLE vacancies ADD COLUMN applied INTEGER NOT NULL DEFAULT 0",
            # Starred/favourite flag
            "ALTER TABLE vacancies ADD COLUMN starred INTEGER NOT NULL DEFAULT 0",
            # RSS publication date (ISO 8601 UTC, from job-monitor pubDate)
            "ALTER TABLE vacancies ADD COLUMN published_at TEXT",
            # Company name extracted from RSS (before full JD parse)
            "ALTER TABLE vacancies ADD COLUMN company TEXT",
            # EPIC-24: Progressive Profile (initial name — kept for existing DBs)
            "ALTER TABLE users ADD COLUMN evidence_json TEXT",
            # EPIC-24: renamed evidence_json → progressive_profile
            "ALTER TABLE users ADD COLUMN progressive_profile TEXT",
            "UPDATE users SET progressive_profile = evidence_json WHERE progressive_profile IS NULL",
            # Analysis error message — stored when analysis_failed status set
            "ALTER TABLE vacancies ADD COLUMN analysis_error TEXT",
            # System key-value cache (e.g. available model lists)
            """CREATE TABLE IF NOT EXISTS system_kv (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )""",
            # EPIC-25 prep: per-user LLM settings (model + thinking effort)
            """CREATE TABLE IF NOT EXISTS user_settings (
                user_id         INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                llm_model       TEXT,
                thinking_effort TEXT NOT NULL DEFAULT 'off',
                updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
            )""",
            # Activity log: provider name + thinking effort per LLM call
            "ALTER TABLE llm_usage ADD COLUMN provider TEXT NOT NULL DEFAULT 'claude_api'",
            "ALTER TABLE llm_usage ADD COLUMN thinking_effort TEXT NOT NULL DEFAULT ''",
            # EPIC-26: deduplication + re-publish detection
            "ALTER TABLE vacancies ADD COLUMN duplicate_of INTEGER REFERENCES vacancies(id)",
            "ALTER TABLE vacancies ADD COLUMN content_hash TEXT",
            "ALTER TABLE vacancies ADD COLUMN republished_at TEXT",
            # Settings: per-user LLM provider override (NULL = LLM_PROVIDER env default)
            "ALTER TABLE user_settings ADD COLUMN llm_provider TEXT",
            # RSSWatcher retry cap: count failed fetch attempts, give up after N
            "ALTER TABLE vacancies ADD COLUMN fetch_attempts INTEGER NOT NULL DEFAULT 0",
            # EPIC-21 C2: pipeline event log for Flutter notification polling
            """CREATE TABLE IF NOT EXISTS notifications (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                vacancy_id  INTEGER REFERENCES vacancies(id) ON DELETE SET NULL,
                event       TEXT    NOT NULL,
                title       TEXT    NOT NULL DEFAULT '',
                body        TEXT    NOT NULL DEFAULT '',
                read        INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            )""",
            "CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications (user_id, created_at)",
            # EPIC-27: per-phase LLM provider/model/effort overrides.
            # Additive — user_settings stays the global default, untouched.
            # No row (or provider IS NULL) for a phase = fall through to the global default.
            """CREATE TABLE IF NOT EXISTS phase_llm_config (
                phase           TEXT PRIMARY KEY,
                provider        TEXT,
                model           TEXT,
                thinking_effort TEXT,
                updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
            )""",
            # EPIC-27: critical blocker pre-filter result (advisory only)
            "ALTER TABLE vacancies ADD COLUMN blocker_flag INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE vacancies ADD COLUMN blocker_reasons TEXT",
            # Raw LLM response — debug parse failures (found the hard way on #716, 2026-07-17)
            "ALTER TABLE vacancies ADD COLUMN blocker_raw_output TEXT",
            # Stage 1 pre-filter (title/domain, deterministic, no LLM) auto-runs on
            # ingest when 1 — separate from Stage 2 (LLM content check), which stays
            # manual-trigger-only. Default 1: free + already-validated, no reason to
            # ship it off.
            "ALTER TABLE user_settings ADD COLUMN auto_check_title INTEGER NOT NULL DEFAULT 1",
            # Settings redesign (2026-07-24): per-provider saved config snapshot
            # (global model/effort + all phase_llm_config pins as JSON) — see
            # provider_config_snapshots comment in schema.sql for the full design.
            """CREATE TABLE IF NOT EXISTS provider_config_snapshots (
                provider        TEXT PRIMARY KEY,
                model           TEXT,
                thinking_effort TEXT NOT NULL DEFAULT 'off',
                phase_configs   TEXT,
                updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
            )""",
            # 2026-07-24: real field for which pre-filter stage set blocker_flag
            # ('title' = Stage 1 deterministic, 'content' = Stage 2 LLM) —
            # replaces string-matching blocker_reasons for a "title:" prefix,
            # which was considered and rejected as fragile. See schema.sql.
            "ALTER TABLE vacancies ADD COLUMN blocker_stage TEXT",
            # Company website — from the site's company profile page (public,
            # unauthenticated), fetched off the critical path and cached per
            # company (2026-08-12). NULL = not yet fetched / no match found.
            "ALTER TABLE vacancies ADD COLUMN company_website TEXT",
            # When the user marked applied=1 — the Applied folder sorts by
            # this, not published_at (job posting date, unrelated to when the
            # user applied) or updated_at (bumped by ~10 unrelated write
            # paths). Found live 2026-08-13: a vacancy applied to seconds ago
            # showed up second, not first. NULL = never applied / un-applied.
            "ALTER TABLE vacancies ADD COLUMN applied_at TEXT",
            # Free-form user tags (comma-separated, e.g. "deftech,ai") — distinct
            # from role_tags (auto-derived from role_balance, display-only, not
            # stored). Used to flag batches of similar vacancies (e.g. a MilTech
            # source) for tracking/filtering. 2026-08-27.
            "ALTER TABLE vacancies ADD COLUMN tags TEXT",
            # When the vacancy was declined (Skip / auto give-up) — Archive
            # sorts by this, not published_at (JD posting date, unrelated to
            # when the user acted) or updated_at (bumped by ~10 unrelated
            # write paths — starred/salary/tags edits, duplicate linking —
            # same reliability gap already fixed for applied_at 2026-08-13).
            # User request 2026-09-05: most-recently-declined first. NULL =
            # never declined, or restored back out of Archive.
            "ALTER TABLE vacancies ADD COLUMN declined_at TEXT",
            # Manual paste/import (via /api/vacancies/import-jd) vs. automatic
            # RSS ingest — url no longer reliably signals this once real
            # posting URLs (parsed from the pasted content's "Source:" line)
            # replaced the synthetic "import://{hash}" scheme. 2026-09-19.
            "ALTER TABLE vacancies ADD COLUMN manual_import INTEGER NOT NULL DEFAULT 0",
            # EPIC-26 dedup rework (2026-10-05): second, weaker duplicate tier —
            # a title+company match whose JD text is NOT similar enough to
            # confirm (see find_possible_duplicate). Never set together with
            # duplicate_of.
            "ALTER TABLE vacancies ADD COLUMN possible_duplicate_of INTEGER REFERENCES vacancies(id)",
            # Company identity (2026-10-05): the company's profile page URL on
            # its job board (DOU /companies/{slug}/, Djinni company page) — a
            # stable unique company id within that board, already extracted by
            # the parser at fetch time but never stored. See core.dedup.profile_key.
            "ALTER TABLE vacancies ADD COLUMN company_profile_url TEXT",
        ]:
            try:
                await db.execute(migration)
                await db.commit()
                log.info("DB migration applied: %s", migration[:60])
            except Exception:
                pass  # column already exists — ignore

    log.info("DB initialised at %s", _db_path)


async def reset_stuck_statuses() -> None:
    """Reset in-progress statuses left by a prior crash. Call once at agent startup, before workers start.

    RSSWatcher._process's own retry logic (fetching → queued on fetch error)
    only runs if the process survives to the except block — a hard restart
    mid-fetch (dev-session process kill, crash) skips it and leaves the row
    stuck in 'fetching' forever, since nothing else ever revisits it. This
    was the actual root cause behind 47→264 stuck rows accumulating over
    several heavy dev sessions (2026-06-17 through 07-02) — confirmed by the
    stuck-row dates matching known high-restart-frequency sessions, and zero
    new stuck rows since 07-10 once dev activity moved off rss_watcher.py.
    """
    async with aiosqlite.connect(_db_path) as db:
        cur = await db.execute(
            "UPDATE vacancies SET status = 'analysis_queued' WHERE status = 'analyzing'"
        )
        await db.commit()
        if cur.rowcount:
            log.warning("DB recovery: reset %d stuck 'analyzing' → 'analysis_queued'", cur.rowcount)
        cur2 = await db.execute(
            "UPDATE vacancies SET status = 'cv_queued' WHERE status = 'cv_generating'"
        )
        await db.commit()
        if cur2.rowcount:
            log.warning("DB recovery: reset %d stuck 'cv_generating' → 'cv_queued'", cur2.rowcount)
        cur3 = await db.execute(
            "UPDATE vacancies SET status = 'queued' WHERE status = 'fetching'"
        )
        await db.commit()
        if cur3.rowcount:
            log.warning("DB recovery: reset %d stuck 'fetching' → 'queued'", cur3.rowcount)


@asynccontextmanager
async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    """Async context manager: yields open aiosqlite connection with Row factory."""
    async with aiosqlite.connect(_db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        yield db


# ── User helpers ─────────────────────────────────────────────────────────────

async def insert_user(
    name: str,
    telegram_chat_id: int | None = None,
    skill_type: str = "pm",
) -> int:
    """Insert new user. Returns new row id.

    telegram_chat_id may be None for local/API-only users.
    Raises sqlite3.IntegrityError if telegram_chat_id already exists.
    """
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO users (telegram_chat_id, name, skill_type)
            VALUES (?, ?, ?)
            """,
            (telegram_chat_id, name, skill_type),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def upsert_user(
    user_id: int,
    name: str,
    skill_type: str = "pm",
) -> None:
    """Insert or update a user by explicit id.

    Used by local /pipeline to sync users from skill/users.yaml into DB.
    Any entry point (Telegram onboarding, admin script, web UI) can call this.
    On conflict: updates name and skill_type, preserves telegram_chat_id and created_at.
    """
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO users (id, name, skill_type)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name       = excluded.name,
                skill_type = excluded.skill_type
            """,
            (user_id, name, skill_type),
        )
        await db.commit()


async def get_user_by_id(user_id: int) -> aiosqlite.Row | None:
    """Return user row by id or None."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        )
        return await cursor.fetchone()


async def get_user_by_telegram_id(telegram_chat_id: int) -> aiosqlite.Row | None:
    """Return user row by Telegram chat_id or None."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM users WHERE telegram_chat_id = ?", (telegram_chat_id,)
        )
        return await cursor.fetchone()


async def get_or_create_default_user(
    telegram_chat_id: int,
    name: str = "Default User",
    skill_type: str = "pm",
) -> int:
    """Return existing user_id for this telegram_chat_id, or create and return new one.

    Called on agent startup. Ensures user_id=1 (first user) is always available.
    """
    row = await get_user_by_telegram_id(telegram_chat_id)
    if row is not None:
        return row["id"]
    return await insert_user(name=name, telegram_chat_id=telegram_chat_id, skill_type=skill_type)


async def list_users() -> list[aiosqlite.Row]:
    """Return all users ordered by id."""
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM users ORDER BY id ASC")
        return await cursor.fetchall()


async def update_user_skill_type(user_id: int, skill_type: str) -> None:
    """Update skill_type for a user. Called by /set_skill command."""
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET skill_type = ? WHERE id = ?",
            (skill_type, user_id),
        )
        await db.commit()


async def update_user_profile(user_id: int, profile_json: str) -> None:
    """Store synthesised onboarding profile (JSON string) for a user."""
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET profile_json = ? WHERE id = ?",
            (profile_json, user_id),
        )
        await db.commit()


async def get_user_profile(user_id: int) -> str | None:
    """Return profile_json string for a user, or None if not yet onboarded."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT profile_json FROM users WHERE id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return row["profile_json"] if row else None


async def update_user_onboarding_step(user_id: int, step: str | None) -> None:
    """Set FSM resume checkpoint. Pass None to clear after onboarding completes."""
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET onboarding_step = ? WHERE id = ?",
            (step, user_id),
        )
        await db.commit()


# ── Vacancy helpers ───────────────────────────────────────────────────────────

async def insert_vacancy(
    url: str,
    title: str | None = None,
    site: str | None = None,
    markdown_path: str | None = None,
    user_id: int | None = None,
    status: str | None = None,
    published_at: str | None = None,
    company: str | None = None,
    manual_import: bool = False,
) -> int:
    """Insert new vacancy. Returns new row id.

    URL is normalised before insert (tracking params stripped, host lowercased).
    site is auto-inferred from URL hostname when not provided.
    user_id: optional FK to users table. NULL = legacy/unscoped (treated as user_id=1).
    status: if provided, sets initial status (e.g. 'queued' for webhook-created vacancies).
    published_at: ISO 8601 UTC string from RSS pubDate (nullable).
    company: company name extracted from RSS feed before full JD parse (nullable).
    manual_import: True when this row came from a pasted/manual import (see
        db/schema.sql comment) rather than automatic RSS ingest.
    Raises sqlite3.IntegrityError if normalised URL already exists — caller should handle.
    """
    canonical_url = normalize_url(url)
    resolved_site = site or extract_site(canonical_url)
    async with get_db() as db:
        if status is not None:
            cursor = await db.execute(
                """
                INSERT INTO vacancies (url, title, site, markdown_path, user_id, status, published_at, company, manual_import)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (canonical_url, title, resolved_site, markdown_path, user_id, status, published_at, company, int(manual_import)),
            )
        else:
            cursor = await db.execute(
                """
                INSERT INTO vacancies (url, title, site, markdown_path, user_id, published_at, company, manual_import)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (canonical_url, title, resolved_site, markdown_path, user_id, published_at, company, int(manual_import)),
            )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def update_vacancy_fields(
    vacancy_id: int,
    title: str | None = None,
    site: str | None = None,
    markdown_path: str | None = None,
    salary: str | None = None,
    company: str | None = None,
    company_website: str | None = None,
    tags: str | None = None,
    company_profile_url: str | None = None,
) -> None:
    """Update mutable fields of an existing vacancy (e.g. after fetching a queued record).

    Only non-None arguments are updated. Does not touch status or timestamps.
    """
    sets: list[str] = []
    params: list = []
    if title is not None:
        sets.append("title = ?")
        params.append(title)
    if site is not None:
        sets.append("site = ?")
        params.append(site)
    if markdown_path is not None:
        sets.append("markdown_path = ?")
        params.append(markdown_path)
    if salary is not None:
        sets.append("salary = ?")
        params.append(salary)
    if company is not None:
        sets.append("company = ?")
        params.append(company)
    if company_website is not None:
        sets.append("company_website = ?")
        params.append(company_website)
    if tags is not None:
        sets.append("tags = ?")
        params.append(tags)
    if company_profile_url is not None:
        sets.append("company_profile_url = ?")
        params.append(company_profile_url)
    if not sets:
        return
    params.append(vacancy_id)
    async with get_db() as db:
        await db.execute(
            f"UPDATE vacancies SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        await db.commit()


async def get_company_website(company: str, user_id: int | None) -> str | None:
    """Return a cached company_website for `company`, if any prior vacancy
    already has one on file. Case-insensitive exact match.

    Cache-before-fetch: companies post multiple vacancies over time, so most
    lookups skip the second HTTP request (company profile page) entirely
    after the first vacancy from that company (2026-08-12).
    """
    if not company:
        return None
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT company_website FROM vacancies
            WHERE company_website IS NOT NULL
              AND LOWER(company) = LOWER(?)
              AND (user_id = ? OR ? IS NULL)
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (company, user_id, user_id),
        )
        row = await cursor.fetchone()
        return row["company_website"] if row else None


async def get_vacancy_by_url(url: str) -> aiosqlite.Row | None:
    """Return vacancy row by URL or None if not found.

    Matches against both the normalised URL and the original URL to handle
    legacy rows that were inserted before URL normalisation was added.
    """
    canonical = normalize_url(url)
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM vacancies WHERE url = ? OR url = ?",
            (canonical, url),
        )
        return await cursor.fetchone()


async def get_vacancy_by_id(vacancy_id: int) -> aiosqlite.Row | None:
    """Return vacancy row by id or None if not found."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM vacancies WHERE id = ?", (vacancy_id,)
        )
        return await cursor.fetchone()


async def patch_analysis_json(vacancy_id: int, phase: str, data: dict) -> None:
    """Merge phase data into analysis_json.

    Reads current JSON, sets analysis_json[phase] = data, writes back.
    Idempotent — repeated calls for same phase overwrite previous value.

    phase: "p1" | "p2" | "p3" | "p4"
    data: dict with phase-specific fields (see schema.sql comment for shape)
    """
    async with get_db() as db:
        cur = await db.execute(
            "SELECT analysis_json FROM vacancies WHERE id = ?", (vacancy_id,)
        )
        row = await cur.fetchone()
        existing: dict = {}
        if row and row["analysis_json"]:
            try:
                existing = json.loads(row["analysis_json"])
            except Exception:
                existing = {}
        existing[phase] = data
        await db.execute(
            "UPDATE vacancies SET analysis_json = ?, updated_at = datetime('now') WHERE id = ?",
            (json.dumps(existing, ensure_ascii=False), vacancy_id),
        )
        await db.commit()


async def update_vacancy_warnings(vacancy_id: int, warnings: str) -> None:
    """Store semicolon-separated warnings for a vacancy."""
    async with get_db() as db:
        await db.execute(
            "UPDATE vacancies SET warnings = ? WHERE id = ?",
            (warnings, vacancy_id),
        )
        await db.commit()


async def update_vacancy_status(vacancy_id: int, status: str) -> None:
    """Update vacancy status and bump updated_at.

    Also stamps declined_at when transitioning to 'declined' (Archive's sort
    key, 2026-09-05) and clears it for any other status — covers both the
    Skip button (status='declined') and Restore (status='analyzed'/'fetched')
    through this one shared setter, same dedicated-timestamp pattern as
    applied_at.
    """
    log.info("DB: vacancy #%d status -> %s", vacancy_id, status)
    declined_at_expr = "datetime('now')" if status == "declined" else "NULL"
    async with get_db() as db:
        await db.execute(
            f"""
            UPDATE vacancies
            SET status = ?, updated_at = datetime('now'), declined_at = {declined_at_expr}
            WHERE id = ?
            """,
            (status, vacancy_id),
        )
        await db.commit()


async def set_analysis_error(vacancy_id: int, error: str | None) -> None:
    """Store analysis error message and set status to analysis_failed."""
    async with get_db() as db:
        await db.execute(
            "UPDATE vacancies SET analysis_error = ?, status = 'analysis_failed', updated_at = datetime('now') WHERE id = ?",
            (error, vacancy_id),
        )
        await db.commit()


async def set_vacancy_blocker(
    vacancy_id: int, blocked: bool, reasons: list[str], raw_output: str | None = None,
    stage: str | None = None,
) -> None:
    """Store pre-filter result (EPIC-27). Advisory only — never changes status.

    raw_output: the model's full response, always stored (even when it didn't
    match the expected format) — without this, a parse failure is undebuggable
    after the fact (found the hard way on vacancy #716, 2026-07-17).

    stage: 'title' (Stage 1, deterministic) | 'content' (Stage 2, LLM) — which
    pre-filter phase produced this verdict, a real field rather than string-
    matching blocker_reasons (decided 2026-07-24). Callers passing
    blocked=True must pass a stage; blocked=False always clears it to NULL —
    a "no blocker" result was never staged by anything.
    """
    async with get_db() as db:
        await db.execute(
            "UPDATE vacancies SET blocker_flag = ?, blocker_reasons = ?, blocker_raw_output = ?, "
            "blocker_stage = ?, updated_at = datetime('now') WHERE id = ?",
            (
                1 if blocked else 0,
                json.dumps(reasons, ensure_ascii=False) if reasons else None,
                raw_output,
                stage if blocked else None,
                vacancy_id,
            ),
        )
        await db.commit()


async def increment_fetch_attempts(vacancy_id: int) -> int:
    """Increment fetch_attempts and return the new count. Called on every RSS fetch failure."""
    async with get_db() as db:
        await db.execute(
            "UPDATE vacancies SET fetch_attempts = fetch_attempts + 1, updated_at = datetime('now') WHERE id = ?",
            (vacancy_id,),
        )
        await db.commit()
        cursor = await db.execute("SELECT fetch_attempts FROM vacancies WHERE id = ?", (vacancy_id,))
        row = await cursor.fetchone()
        return row["fetch_attempts"] if row else 0


async def give_up_fetch(vacancy_id: int, error: str | None) -> None:
    """Stop retrying a vacancy that failed to fetch MAX_FETCH_ATTEMPTS times.

    Sets status='declined' (out of Inbox, matches "Inbox Zero" — an
    unparseable page isn't worth indefinite retries) and records the last
    error in analysis_error so the reason is visible, not just silently
    archived. Also stamps declined_at (Archive's sort key) — bypasses
    update_vacancy_status so it needs its own, same as that function.
    """
    async with get_db() as db:
        await db.execute(
            "UPDATE vacancies SET status = 'declined', analysis_error = ?, "
            "updated_at = datetime('now'), declined_at = datetime('now') WHERE id = ?",
            (error, vacancy_id),
        )
        await db.commit()


async def requeue_fetch(vacancy_id: int) -> None:
    """Re-queue a vacancy that gave up fetching (status='declined', no markdown_path).

    Sets status='queued' (picked up by RSSWatcher._poll_once), resets
    fetch_attempts to 0 (otherwise the next single failure would immediately
    hit MAX_FETCH_ATTEMPTS again and re-decline it) and clears analysis_error.
    Also clears declined_at — this is a restore path, bypasses
    update_vacancy_status so it needs its own.
    """
    async with get_db() as db:
        await db.execute(
            "UPDATE vacancies SET status = 'queued', fetch_attempts = 0, "
            "analysis_error = NULL, updated_at = datetime('now'), declined_at = NULL WHERE id = ?",
            (vacancy_id,),
        )
        await db.commit()


async def clear_analysis_error(vacancy_id: int) -> None:
    """Clear analysis_error when vacancy is re-queued for analysis."""
    async with get_db() as db:
        await db.execute(
            "UPDATE vacancies SET analysis_error = NULL WHERE id = ?",
            (vacancy_id,),
        )
        await db.commit()


# ── EPIC-26: Deduplication + Re-publish helpers ───────────────────────────────

def _normalize_title(title: str, company: str | None = None) -> str:
    """Lowercase + collapse whitespace. Used for title-based duplicate detection.

    When `company` is given and the title ends with a dash + that exact company
    (e.g. DOU-style "Role — Company", vs Djinni's bare "Role"), the suffix is
    stripped first — otherwise the same real job posted on both sites never
    matches on title+company even when company itself is correct (found live,
    2026-07-25: "Product Manager (Globalization)" [Djinni] vs "Product Manager
    (Globalization) — Headway Inc" [DOU] never deduped). Only strips a suffix
    matching the specific company being compared — a title with an unrelated
    dash (e.g. "Product Manager - B2B SaaS") is left alone.
    """
    import re as _re
    if company:
        title = _re.sub(
            rf"\s*[-–—]\s*{_re.escape(company.strip())}\s*$",
            "",
            title,
            flags=_re.IGNORECASE,
        )
    return _re.sub(r"\s+", " ", title.lower().strip())


@dataclass(frozen=True)
class DuplicateVerdict:
    """Outcome of classify_duplicate().

    confirmed_id — hard duplicate (content-hash match, title+company match with
                   JD containment >= CONFIRM_THRESHOLD, or a recent vacancy with
                   containment >= TEXT_CONFIRM_THRESHOLD whatever its title or
                   company) -> duplicate_of.
    possible_id  — title+company match that could not be confirmed
                   -> possible_duplicate_of. Never set together with confirmed_id.
    containment  — containment of the chosen candidate, None for a hash match or
                   when no text comparison was possible.
    reason       — "hash" | "title_company" | "text" | "title_company_unverified" | "none"
    """
    confirmed_id: int | None = None
    possible_id: int | None = None
    containment: float | None = None
    reason: str = "none"


async def _load_link_graph(db) -> dict[str, set[str]]:
    cur = await db.execute("SELECT profile_key_a, profile_key_b FROM company_profile_links")
    return build_link_graph((r["profile_key_a"], r["profile_key_b"]) for r in await cur.fetchall())


async def get_company_link_graph() -> dict[str, set[str]]:
    """Adjacency of learned cross-board company profile links (see
    core.dedup.profile_group)."""
    async with get_db() as db:
        return await _load_link_graph(db)


async def classify_duplicate(
    user_id: int,
    content_hash: str | None,
    norm_title: str | None,
    company: str | None,
    exclude_id: int | None = None,
    new_text: str | None = None,
    before_id: int | None = None,
    profile_key: str | None = None,
    as_of: str | None = None,
) -> DuplicateVerdict:
    """Duplicate verdict for one vacancy (EPIC-26 rework, 2026-10-05).

    1. content_hash match -> confirmed, unconditionally (lowest id among
       matches); wins over everything.
    2. Text-first (needs `new_text`): every same-user vacancy created/published
       within TEXT_SCAN_WINDOW_DAYS before `as_of` is scored by containment of
       `new_text` against its JD.md; one with containment >=
       TEXT_CONFIRM_THRESHOLD is CONFIRMED whatever its company or title.
    3. Title+company candidates: same user, same normalized title (exact —
       fuzzy title matching was rejected by the owner) and the SAME COMPANY
       (core.dedup.same_company: profile-key group first, normalized-name
       fallback), scored the same way; best containment >= CONFIRM_THRESHOLD
       -> confirmed; below it, or when new_text / the files are unreadable ->
       only possible.

    Among everything that qualifies as confirmed the best containment wins,
    ties -> lowest id. The score never DROPS a title+company match, only
    downgrades it (no threshold separates true duplicates from non-duplicates —
    see core/dedup.py). A text-only candidate below TEXT_CONFIRM_THRESHOLD is
    ignored.

    new_text: the new vacancy's full JD.md text (header included — it is
    stripped by core.dedup). before_id: only consider rows with a smaller id —
    for backfills that replay ingestion order. profile_key: the new vacancy's
    company profile key (core.dedup.profile_key). as_of: reference timestamp of
    the recency window (the vacancy's created_at when replaying; default now).
    Candidate files are read and shingled off the event loop and cached per
    process (core.dedup.cached_file_shingles).
    """
    async with get_db() as db:
        if content_hash:
            sql = "SELECT id FROM vacancies WHERE user_id = ? AND content_hash = ?"
            params: list = [user_id, content_hash]
            if exclude_id is not None:
                sql += " AND id != ?"
                params.append(exclude_id)
            if before_id is not None:
                sql += " AND id < ?"
                params.append(before_id)
            cur = await db.execute(sql + " ORDER BY id ASC LIMIT 1", params)
            row = await cur.fetchone()
            if row:
                return DuplicateVerdict(confirmed_id=row["id"], reason="hash")

        want_title_company = bool(norm_title and (company or profile_key))
        if not (want_title_company or new_text):
            return DuplicateVerdict()

        sql = (
            "SELECT id, title, company, site, company_profile_url, markdown_path, "
            "created_at, published_at FROM vacancies WHERE user_id = ?"
        )
        params = [user_id]
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        if before_id is not None:
            sql += " AND id < ?"
            params.append(before_id)
        cur = await db.execute(sql + " ORDER BY id ASC", params)
        rows = [dict(r) for r in await cur.fetchall()]
        graph = await _load_link_graph(db) if want_title_company else {}

    # Title+company candidates (exact normalized title + same company).
    tc_ids: list[int] = []
    if want_title_company:
        subject = {"company": company, "profile_key": profile_key}
        wanted_title = norm_title.lower()
        for r in rows:
            if _normalize_title(r["title"] or "", r["company"]) == wanted_title and same_company(r, subject, graph):
                tc_ids.append(r["id"])  # rows are ascending by id

    scores: dict[int, float | None] = {}
    if new_text:
        as_of_dt = parse_as_of(as_of)
        tc_set = set(tc_ids)
        to_score = [
            (r["id"], r["markdown_path"]) for r in rows
            if r["id"] in tc_set or in_text_window(r["created_at"], r["published_at"], as_of_dt)
        ]
        scores = await score_candidates(new_text, to_score, _PROJECT_ROOT)

    # Confirmed: a title+company candidate >= CONFIRM_THRESHOLD, or ANY scored
    # candidate >= TEXT_CONFIRM_THRESHOLD. Best score wins, ties -> lowest id.
    tc_set = set(tc_ids)
    best_conf: tuple[float, int] | None = None
    for cand_id in sorted(scores):
        score = scores[cand_id]
        if score is None:
            continue
        if score >= TEXT_CONFIRM_THRESHOLD or (cand_id in tc_set and score >= CONFIRM_THRESHOLD):
            if best_conf is None or score > best_conf[0]:
                best_conf = (score, cand_id)
    if best_conf is not None:
        score, cand_id = best_conf
        reason = "title_company" if (cand_id in tc_set and score >= CONFIRM_THRESHOLD) else "text"
        return DuplicateVerdict(confirmed_id=cand_id, containment=score, reason=reason)

    if not tc_ids:
        return DuplicateVerdict()

    # Unconfirmed title+company match -> possible: best-scoring readable
    # candidate, else the lowest id.
    best_id, best_score = tc_ids[0], None
    for cand_id in tc_ids:  # ascending id: strict ">" keeps lowest on ties
        score = scores.get(cand_id)
        if score is None:
            continue
        if best_score is None or score > best_score:
            best_id, best_score = cand_id, score
    return DuplicateVerdict(possible_id=best_id, containment=best_score, reason="title_company_unverified")


async def find_duplicate(
    user_id: int,
    content_hash: str | None,
    norm_title: str | None,
    company: str | None,
    exclude_id: int | None = None,
    new_text: str | None = None,
    profile_key: str | None = None,
) -> int | None:
    """Return the id of the CONFIRMED original of a vacancy, or None.

    Confirmed = content_hash collision, a title+company match whose JD text
    contains >= CONFIRM_THRESHOLD of the new text, or any recent vacancy with
    >= TEXT_CONFIRM_THRESHOLD (new_text required for both text paths — without
    it a title+company match is only "possible", see find_possible_duplicate).
    The web manual-import path passes no title/company/text and stays hash-only.
    exclude_id: vacancy id to skip (avoids self-match during re-fetch).
    """
    verdict = await classify_duplicate(
        user_id, content_hash, norm_title, company, exclude_id, new_text, profile_key=profile_key,
    )
    return verdict.confirmed_id


async def find_possible_duplicate(
    user_id: int,
    content_hash: str | None,
    norm_title: str | None,
    company: str | None,
    exclude_id: int | None = None,
    new_text: str | None = None,
    profile_key: str | None = None,
) -> int | None:
    """Return the id of the best title+company candidate that could NOT be
    confirmed (low text containment, no new_text, or unreadable JD file), or
    None — including when the vacancy is a confirmed duplicate."""
    verdict = await classify_duplicate(
        user_id, content_hash, norm_title, company, exclude_id, new_text, profile_key=profile_key,
    )
    return verdict.possible_id


async def set_duplicate_of(vacancy_id: int, original_id: int) -> None:
    """Mark vacancy as a CONFIRMED duplicate of original_id (clears the possible tier).

    Deliberately does NOT touch updated_at: the Analyzed/processed folders sort by it,
    so a bulk (re-)linking would push every old vacancy to the top of the list.

    Also learns company identity: when the two rows carry DIFFERENT company
    profile keys on DIFFERENT boards (typically Djinni vs DOU), those keys are
    recorded as the same company in company_profile_links. Same-board
    differences are not learned — an outsourcing vendor reposting one template
    JD for several clients must not merge their profiles.
    """
    async with get_db() as db:
        await db.execute(
            "UPDATE vacancies SET duplicate_of = ?, possible_duplicate_of = NULL WHERE id = ?",
            (original_id, vacancy_id),
        )
        try:
            cur = await db.execute(
                "SELECT id, site, company_profile_url FROM vacancies WHERE id IN (?, ?)",
                (vacancy_id, original_id),
            )
            found = {r["id"]: r for r in await cur.fetchall()}
            a, b = found.get(vacancy_id), found.get(original_id)
            if a is not None and b is not None:
                ka, kb = row_profile_key(a), row_profile_key(b)
                if ka and kb and ka != kb and (a["site"] or "") != (b["site"] or ""):
                    key_a, key_b = sorted((ka, kb))
                    va, vb = (vacancy_id, original_id) if ka <= kb else (original_id, vacancy_id)
                    await db.execute(
                        "INSERT OR IGNORE INTO company_profile_links "
                        "(profile_key_a, profile_key_b, vacancy_a, vacancy_b) VALUES (?, ?, ?, ?)",
                        (key_a, key_b, va, vb),
                    )
        except Exception as exc:  # learning is best-effort, never blocks the flag
            log.warning("company link learning failed for v#%s -> v#%s: %s", vacancy_id, original_id, exc)
        await db.commit()


async def set_possible_duplicate_of(vacancy_id: int, original_id: int) -> None:
    """Mark vacancy as a POSSIBLE duplicate of original_id (clears the confirmed tier)."""
    async with get_db() as db:
        await db.execute(
            "UPDATE vacancies SET possible_duplicate_of = ?, duplicate_of = NULL WHERE id = ?",
            (original_id, vacancy_id),
        )
        await db.commit()


async def clear_duplicate_flags(vacancy_id: int) -> None:
    """Clear both duplicate tiers (re-evaluation found no match). No-op when neither is set."""
    async with get_db() as db:
        await db.execute(
            "UPDATE vacancies SET duplicate_of = NULL, possible_duplicate_of = NULL "
            "WHERE id = ? AND (duplicate_of IS NOT NULL OR possible_duplicate_of IS NOT NULL)",
            (vacancy_id,),
        )
        await db.commit()


async def get_dedup_link_rows(user_id: int | None = None) -> list[aiosqlite.Row]:
    """Light projection of every vacancy's duplicate links, applied state and
    company identity columns — the input of core.dedup.compute_applied_twins and
    compute_company_applied. Deliberately unfiltered by
    status/limit/since: the twin of a listed row may be outside the page the
    caller fetched. user_id=None -> all users (the pure helper groups per user)."""
    sql = (
        "SELECT id, user_id, duplicate_of, possible_duplicate_of, applied, applied_at, "
        "company, site, company_profile_url FROM vacancies"
    )
    params: list = []
    if user_id is not None:
        # legacy NULL user_id counts as user 1 (see insert_vacancy)
        sql += " WHERE COALESCE(user_id, 1) = ?"
        params.append(user_id)
    async with get_db() as db:
        cursor = await db.execute(sql, params)
        return await cursor.fetchall()


async def get_applied_twin_id(vacancy_id: int) -> int | None:
    """Id of the already-applied vacancy in this vacancy's duplicate group
    (confirmed + possible links, both directions, transitive), or None.
    See core.dedup.compute_applied_twins for the exact rules."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT COALESCE(user_id, 1) AS u FROM vacancies WHERE id = ?", (vacancy_id,)
        )
        row = await cursor.fetchone()
    if row is None:
        return None
    rows = await get_dedup_link_rows(row["u"])
    return compute_applied_twins(rows).get(vacancy_id)


async def get_company_applied_id(vacancy_id: int) -> int | None:
    """Id of the most recently applied vacancy of the same company ("Applied at
    this company" hint), excluding the vacancy itself and its applied twin;
    None when there is none or this vacancy is itself applied. See
    core.dedup.compute_company_applied for the exact rules."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT COALESCE(user_id, 1) AS u FROM vacancies WHERE id = ?", (vacancy_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        graph = await _load_link_graph(db)
    rows = await get_dedup_link_rows(row["u"])
    twins = compute_applied_twins(rows)
    return compute_company_applied(rows, graph, twins).get(vacancy_id)


async def set_content_hash(vacancy_id: int, content_hash: str) -> None:
    """Store JD content hash after fetch."""
    async with get_db() as db:
        await db.execute(
            "UPDATE vacancies SET content_hash = ? WHERE id = ?",
            (content_hash, vacancy_id),
        )
        await db.commit()


async def on_vacancy_republished(vacancy_id: int, new_published_at: str) -> None:
    """Handle a declined/skipped vacancy reappearing in RSS.

    Updates published_at, sets republished_at = now(), transitions status → fetched.
    Called only when prior status was declined/skipped. Also clears
    declined_at — this reopens the vacancy out of Archive, bypasses
    update_vacancy_status so it needs its own.
    """
    async with get_db() as db:
        await db.execute(
            """
            UPDATE vacancies
            SET published_at    = ?,
                republished_at  = datetime('now'),
                status          = 'fetched',
                analysis_error  = NULL,
                updated_at      = datetime('now'),
                declined_at     = NULL
            WHERE id = ?
            """,
            (new_published_at, vacancy_id),
        )
        await db.commit()


async def bump_published_at(vacancy_id: int, new_published_at: str) -> None:
    """Refresh published_at for a settled vacancy re-published in RSS.

    Used when the vacancy is analyzed/inbox (not declined) — the employer bumped
    the posting, so it should rise in the date-sorted inbox. No status change,
    no republished_at badge (that is reserved for declined/skipped re-publishes).
    """
    async with get_db() as db:
        await db.execute(
            "UPDATE vacancies SET published_at = ? WHERE id = ?",
            (new_published_at, vacancy_id),
        )
        await db.commit()


async def update_published_at(vacancy_id: int, published_at: str) -> None:
    """Update published_at only (vacancy bumped in feed but not re-published for our purposes)."""
    async with get_db() as db:
        await db.execute(
            "UPDATE vacancies SET published_at = ?, updated_at = datetime('now') WHERE id = ?",
            (published_at, vacancy_id),
        )
        await db.commit()


async def set_vacancy_applied(vacancy_id: int, applied: bool) -> None:
    """Set applied flag for a vacancy. 1 = CV submitted, 0 = not submitted.

    applied_at records the moment this was actually toggled — the Applied
    folder sorts by it (not published_at, which is when the JOB was posted,
    not when the user applied to it; not updated_at, which is bumped by ~10
    unrelated write paths — same class of bug as the "Analyzed" chip fix,
    2026-08-12). Cleared back to NULL when un-applying, since it's no longer
    a real "applied" event.
    """
    applied_at_expr = "datetime('now')" if applied else "NULL"
    async with get_db() as db:
        await db.execute(
            f"UPDATE vacancies SET applied = ?, applied_at = {applied_at_expr}, "
            "updated_at = datetime('now') WHERE id = ?",
            (1 if applied else 0, vacancy_id),
        )
        await db.commit()


async def set_vacancy_starred(vacancy_id: int, starred: bool) -> None:
    """Set starred/favourite flag for a vacancy. 1 = favourite, 0 = normal."""
    async with get_db() as db:
        await db.execute(
            "UPDATE vacancies SET starred = ?, updated_at = datetime('now') WHERE id = ?",
            (1 if starred else 0, vacancy_id),
        )
        await db.commit()


async def set_vacancy_salary(vacancy_id: int, salary: str) -> None:
    """Set user-entered salary for a vacancy. Empty string clears the field."""
    async with get_db() as db:
        await db.execute(
            "UPDATE vacancies SET salary = ?, updated_at = datetime('now') WHERE id = ?",
            (salary or None, vacancy_id),
        )
        await db.commit()


async def set_vacancy_tags(vacancy_id: int, tags: str) -> None:
    """Set comma-separated user tags for a vacancy. Empty string clears the field."""
    async with get_db() as db:
        await db.execute(
            "UPDATE vacancies SET tags = ?, updated_at = datetime('now') WHERE id = ?",
            (tags or None, vacancy_id),
        )
        await db.commit()


async def list_vacancies(
    status: str | None = None,
    user_id: int | None = None,
    limit: int = 50,
    since: str | None = None,
) -> list[aiosqlite.Row]:
    """Return vacancies ordered by created_at desc. Optionally filter by status and/or user_id.

    user_id=None → return all users (admin/unfiltered view).
    user_id=N    → return only vacancies belonging to that user.
    since: ISO 8601 datetime string — return only rows where updated_at >= since.
           Used by Flutter polling (A5b): GET /api/vacancies?status=analyzed&since=X.
    """
    async with get_db() as db:
        conditions: list[str] = []
        params: list = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if user_id is not None:
            conditions.append("user_id = ?")
            params.append(user_id)
        if since is not None:
            conditions.append("updated_at >= ?")
            params.append(since)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        # COALESCE(published_at, created_at): RSS-sourced vacancies sort by their
        # job-posting date as before; locally-added vacancies (via /analyze skill,
        # no published_at) fall back to when we found out about them instead of
        # sinking to the very end ordered oldest-first by id. Without this, once
        # total vacancy count exceeds the caller's limit, every local addition
        # became permanently invisible — found live 2026-08-27, vacancy #1303
        # (added via /analyze, undetectable in Flutter's default 1000-row fetch
        # despite being the newest thing in the DB).
        cursor = await db.execute(
            f"SELECT * FROM vacancies {where} ORDER BY COALESCE(published_at, created_at) DESC, id DESC LIMIT ?",
            params,
        )
        return await cursor.fetchall()


# ── Pipeline run helpers ───────────────────────────────────────────────────────

async def insert_pipeline_run(vacancy_id: int, phase: str) -> int:
    """Create a new pipeline run record in 'pending' state. Returns run id."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO pipeline_runs (vacancy_id, phase, status)
            VALUES (?, ?, 'pending')
            """,
            (vacancy_id, phase),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def update_pipeline_run(
    run_id: int,
    status: str,
    result_path: str | None = None,
    error_message: str | None = None,
) -> None:
    """Update pipeline run status, optionally set result_path or error.

    Sets started_at on first transition to 'running'.
    Sets finished_at when status is 'done' or 'error'.
    """
    async with get_db() as db:
        # Fetch current status to decide timestamp updates
        cur = await db.execute("SELECT status FROM pipeline_runs WHERE id = ?", (run_id,))
        row = await cur.fetchone()
        current = row["status"] if row else None

        started_at_expr = "started_at"
        finished_at_expr = "finished_at"

        if status == "running" and current == "pending":
            started_at_expr = "datetime('now')"
        if status in ("done", "error"):
            finished_at_expr = "datetime('now')"

        if status == "error":
            log.error("DB: pipeline_run #%d → error: %s", run_id, error_message or "(no message)")
        elif status == "done":
            log.info("DB: pipeline_run #%d → done (result=%s)", run_id, result_path)

        await db.execute(
            f"""
            UPDATE pipeline_runs
            SET status        = ?,
                result_path   = COALESCE(?, result_path),
                error_message = COALESCE(?, error_message),
                started_at    = {started_at_expr},
                finished_at   = {finished_at_expr}
            WHERE id = ?
            """,
            (status, result_path, error_message, run_id),
        )
        await db.commit()


async def insert_llm_usage(
    phase: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int,
    cache_read_tokens: int,
    cost_usd: float,
    vacancy_id: int | None = None,
    user_id: int | None = None,
    profile_tokens: int = 0,
    prompt_tokens: int = 0,
    user_tokens: int = 0,
    budget_tokens: int = 0,
    thinking_tokens: int = 0,
    elapsed_ms: int = 0,
    provider: str = "claude_api",
    thinking_effort: str = "",
) -> int:
    """Record one LLM API call for cost tracking and unit economics analysis.

    Input breakdown (profile/prompt/user) is estimated from text length (len//4, ±10%).
    API-reported totals (input/output/cache) are exact from the response.
    user_id: optional FK for per-user cost analytics.
    provider: 'claude_api' | 'claude_cli' | 'ollama_api'
    thinking_effort: 'off'|'low'|'medium'|'high'|'xhigh'|'max'|'' (empty = not applicable)
    """
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO llm_usage
                (vacancy_id, user_id, phase, model,
                 profile_tokens, prompt_tokens, user_tokens,
                 input_tokens, output_tokens,
                 cache_write_tokens, cache_read_tokens,
                 budget_tokens, thinking_tokens,
                 elapsed_ms, cost_usd,
                 provider, thinking_effort)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (vacancy_id, user_id, phase, model,
             profile_tokens, prompt_tokens, user_tokens,
             input_tokens, output_tokens,
             cache_write_tokens, cache_read_tokens,
             budget_tokens, thinking_tokens,
             elapsed_ms, round(cost_usd, 6),
             provider, thinking_effort),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def get_vacancy_activity(vacancy_id: int) -> list[dict]:
    """Return all LLM usage rows for a vacancy, chronological."""
    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT phase, provider, model, thinking_effort,
                   elapsed_ms, input_tokens, output_tokens,
                   cache_read_tokens, cost_usd, created_at
            FROM llm_usage
            WHERE vacancy_id = ?
            ORDER BY created_at ASC
            """,
            (vacancy_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_vacancy_pipeline_runs(vacancy_id: int) -> list[dict]:
    """Return all pipeline_runs rows for a vacancy with computed duration_ms."""
    from datetime import datetime

    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT phase, status, error_message, started_at, finished_at, created_at
            FROM pipeline_runs
            WHERE vacancy_id = ?
            ORDER BY created_at ASC
            """,
            (vacancy_id,),
        )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            r = dict(row)
            duration_ms = None
            if r["started_at"] and r["finished_at"]:
                try:
                    start = datetime.fromisoformat(r["started_at"])
                    end = datetime.fromisoformat(r["finished_at"])
                    duration_ms = int((end - start).total_seconds() * 1000)
                except ValueError:
                    pass
            r["duration_ms"] = duration_ms
            result.append(r)
        return result


async def get_last_phase_completion(vacancy_id: int, phase: str) -> str | None:
    """Return finished_at of the most recent successful run of `phase`, or None.

    Used to report a real "last analyzed" time (pipeline_runs) instead of
    vacancies.updated_at, which is bumped by ~10 unrelated write paths
    (applied/starred toggle, salary edit, republish bump, dedup, ...) and so
    cannot be trusted to mean "this phase ran" (found live 2026-08-11, #597).
    """
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT finished_at FROM pipeline_runs
            WHERE vacancy_id = ? AND phase = ? AND status = 'done'
            ORDER BY finished_at DESC LIMIT 1
            """,
            (vacancy_id, phase),
        )
        row = await cursor.fetchone()
        return row["finished_at"] if row else None


async def get_last_phase_completions(phase: str) -> dict[int, str]:
    """{vacancy_id: finished_at} of the latest successful run of `phase`, all
    vacancies in one query — for list endpoints (same meaning as
    get_last_phase_completion, without a query per row)."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT vacancy_id, MAX(finished_at) AS finished_at FROM pipeline_runs
            WHERE phase = ? AND status = 'done' AND finished_at IS NOT NULL
            GROUP BY vacancy_id
            """,
            (phase,),
        )
        return {r["vacancy_id"]: r["finished_at"] for r in await cursor.fetchall()}


# ── Push subscription helpers ─────────────────────────────────────────────────

async def upsert_push_subscription(
    user_id: int,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str | None = None,
) -> None:
    """Store or refresh a Web Push subscription. endpoint is the unique key.

    On conflict (same endpoint, different keys — browser key rotation):
    updates p256dh + auth so sends don't fail with stale keys.
    """
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, user_agent)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(endpoint) DO UPDATE SET
                p256dh     = excluded.p256dh,
                auth       = excluded.auth,
                user_agent = excluded.user_agent
            """,
            (user_id, endpoint, p256dh, auth, user_agent),
        )
        await db.commit()


async def delete_push_subscription(endpoint: str) -> None:
    """Remove a push subscription. Called when endpoint returns 404/410 (expired)."""
    async with get_db() as db:
        await db.execute(
            "DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,)
        )
        await db.commit()


async def get_push_subscriptions(user_id: int) -> list[aiosqlite.Row]:
    """Return all active push subscriptions for user_id."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM push_subscriptions WHERE user_id = ? ORDER BY created_at ASC",
            (user_id,),
        )
        return await cursor.fetchall()


# ── System KV helpers ────────────────────────────────────────────────────────

async def get_kv(key: str) -> tuple[str | None, str | None]:
    """Return (value, updated_at) for key. Both None if key missing."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT value, updated_at FROM system_kv WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
    if row is None:
        return None, None
    return row["value"], row["updated_at"]


async def set_kv(key: str, value: str) -> None:
    """Upsert a key-value entry, setting updated_at to now."""
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO system_kv (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, value),
        )
        await db.commit()


# ── User settings helpers ─────────────────────────────────────────────────────

async def get_user_settings(user_id: int) -> dict:
    """Return user LLM settings. Missing row returns empty dict (caller falls back to env)."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT llm_provider, llm_model, thinking_effort FROM user_settings WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
    if row is None:
        return {}
    return {
        "llm_provider": row["llm_provider"],    # None if not overridden
        "llm_model": row["llm_model"],          # None if not overridden
        "thinking_effort": row["thinking_effort"],
    }


async def set_user_settings(
    user_id: int,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    thinking_effort: str = "off",
) -> None:
    """Upsert LLM settings for user. None provider/model means use env default."""
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO user_settings (user_id, llm_provider, llm_model, thinking_effort, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                llm_provider = excluded.llm_provider,
                llm_model = excluded.llm_model,
                thinking_effort = excluded.thinking_effort,
                updated_at = excluded.updated_at
            """,
            (user_id, llm_provider, llm_model, thinking_effort),
        )
        await db.commit()


async def get_auto_check_title(user_id: int) -> bool:
    """Whether Stage 1 (deterministic title/domain pre-filter) auto-runs on
    ingest for this user. Missing row → default True (matches the column's
    schema default) — a fresh user hasn't opted OUT yet."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT auto_check_title FROM user_settings WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
    if row is None:
        return True
    return bool(row["auto_check_title"])


async def set_auto_check_title(user_id: int, enabled: bool) -> None:
    """Upsert just the auto_check_title flag — deliberately narrow (not folded
    into set_user_settings) so flipping it never touches llm_provider/model/
    thinking_effort on an existing row."""
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO user_settings (user_id, auto_check_title, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                auto_check_title = excluded.auto_check_title,
                updated_at = excluded.updated_at
            """,
            (user_id, int(enabled)),
        )
        await db.commit()


async def get_phase_llm_config(phase: str) -> dict | None:
    """Return override row for one phase, or None if unset (caller falls back to global default)."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT provider, model, thinking_effort FROM phase_llm_config WHERE phase = ?",
            (phase,),
        )
        row = await cursor.fetchone()
    if row is None or row["provider"] is None:
        return None
    return {
        "provider": row["provider"],
        "model": row["model"],
        "thinking_effort": row["thinking_effort"],
    }


async def list_phase_llm_configs() -> dict[str, dict]:
    """Return all override rows, keyed by phase. Phases with no override are absent."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT phase, provider, model, thinking_effort FROM phase_llm_config WHERE provider IS NOT NULL",
        )
        rows = await cursor.fetchall()
    return {
        row["phase"]: {
            "provider": row["provider"],
            "model": row["model"],
            "thinking_effort": row["thinking_effort"],
        }
        for row in rows
    }


async def set_phase_llm_config(
    phase: str,
    provider: str,
    model: str | None,
    thinking_effort: str,
) -> None:
    """Upsert an override for one phase."""
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO phase_llm_config (phase, provider, model, thinking_effort, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(phase) DO UPDATE SET
                provider = excluded.provider,
                model = excluded.model,
                thinking_effort = excluded.thinking_effort,
                updated_at = excluded.updated_at
            """,
            (phase, provider, model, thinking_effort),
        )
        await db.commit()


async def delete_phase_llm_config(phase: str) -> None:
    """Remove a phase's override — resets it to follow the global default."""
    async with get_db() as db:
        await db.execute("DELETE FROM phase_llm_config WHERE phase = ?", (phase,))
        await db.commit()


async def get_provider_snapshot(provider: str) -> dict | None:
    """Return the last-saved full config for one provider (global model/effort
    + all phase pins), or None if never saved."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT model, thinking_effort, phase_configs FROM provider_config_snapshots WHERE provider = ?",
            (provider,),
        )
        row = await cursor.fetchone()
    if row is None:
        return None
    try:
        phase_configs = json.loads(row["phase_configs"]) if row["phase_configs"] else {}
    except (json.JSONDecodeError, TypeError):
        phase_configs = {}
    return {
        "model": row["model"],
        "thinking_effort": row["thinking_effort"],
        "phase_configs": phase_configs,
    }


async def set_provider_snapshot(
    provider: str,
    model: str | None,
    thinking_effort: str,
    phase_configs: dict,
) -> None:
    """Upsert the full saved state for one provider."""
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO provider_config_snapshots (provider, model, thinking_effort, phase_configs, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(provider) DO UPDATE SET
                model = excluded.model,
                thinking_effort = excluded.thinking_effort,
                phase_configs = excluded.phase_configs,
                updated_at = excluded.updated_at
            """,
            (provider, model, thinking_effort, json.dumps(phase_configs)),
        )
        await db.commit()


async def get_pipeline_runs(vacancy_id: int) -> list[aiosqlite.Row]:
    """Return all pipeline runs for a vacancy, ordered by phase."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT * FROM pipeline_runs
            WHERE vacancy_id = ?
            ORDER BY created_at ASC
            """,
            (vacancy_id,),
        )
        return await cursor.fetchall()


# ── Notification helpers ──────────────────────────────────────────────────────

async def insert_notification(
    user_id: int,
    event: str,
    vacancy_id: int | None = None,
    title: str = "",
    body: str = "",
) -> int:
    """Insert a pipeline event notification. Returns new row id."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO notifications (user_id, vacancy_id, event, title, body)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, vacancy_id, event, title, body),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def list_notifications(
    user_id: int,
    since: str | None = None,
    unread_only: bool = False,
    limit: int = 50,
) -> list[dict]:
    """Return notifications for user_id, newest first.

    since: ISO 8601 datetime — only rows where created_at >= since.
    unread_only: filter to read=0 rows only.
    """
    conditions = ["user_id = ?"]
    params: list = [user_id]
    if since:
        conditions.append("created_at >= ?")
        params.append(since)
    if unread_only:
        conditions.append("read = 0")
    where = " AND ".join(conditions)
    params.append(limit)

    async with get_db() as db:
        cursor = await db.execute(
            f"SELECT * FROM notifications WHERE {where} ORDER BY created_at DESC LIMIT ?",
            params,
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def mark_notification_read(notification_id: int) -> None:
    """Mark a single notification as read."""
    async with get_db() as db:
        await db.execute(
            "UPDATE notifications SET read = 1 WHERE id = ?",
            (notification_id,),
        )
        await db.commit()


async def mark_all_notifications_read(user_id: int) -> None:
    """Mark all unread notifications for user as read."""
    async with get_db() as db:
        await db.execute(
            "UPDATE notifications SET read = 1 WHERE user_id = ? AND read = 0",
            (user_id,),
        )
        await db.commit()
