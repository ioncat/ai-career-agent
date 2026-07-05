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
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import urlparse, urlunparse

import aiosqlite

log = logging.getLogger(__name__)

# Default DB path — override via DB_PATH env var or settings
_DEFAULT_DB_PATH = Path(__file__).parent / "agent.db"
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"

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
        path = p.path.rstrip("/") or "/"
        return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "", "", ""))
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
        ]:
            try:
                await db.execute(migration)
                await db.commit()
                log.info("DB migration applied: %s", migration[:60])
            except Exception:
                pass  # column already exists — ignore

    log.info("DB initialised at %s", _db_path)


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
) -> int:
    """Insert new vacancy. Returns new row id.

    URL is normalised before insert (tracking params stripped, host lowercased).
    site is auto-inferred from URL hostname when not provided.
    user_id: optional FK to users table. NULL = legacy/unscoped (treated as user_id=1).
    status: if provided, sets initial status (e.g. 'queued' for webhook-created vacancies).
    published_at: ISO 8601 UTC string from RSS pubDate (nullable).
    company: company name extracted from RSS feed before full JD parse (nullable).
    Raises sqlite3.IntegrityError if normalised URL already exists — caller should handle.
    """
    canonical_url = normalize_url(url)
    resolved_site = site or extract_site(canonical_url)
    async with get_db() as db:
        if status is not None:
            cursor = await db.execute(
                """
                INSERT INTO vacancies (url, title, site, markdown_path, user_id, status, published_at, company)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (canonical_url, title, resolved_site, markdown_path, user_id, status, published_at, company),
            )
        else:
            cursor = await db.execute(
                """
                INSERT INTO vacancies (url, title, site, markdown_path, user_id, published_at, company)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (canonical_url, title, resolved_site, markdown_path, user_id, published_at, company),
            )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def update_vacancy_fields(
    vacancy_id: int,
    title: str | None = None,
    site: str | None = None,
    markdown_path: str | None = None,
    salary: str | None = None,
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
    if not sets:
        return
    params.append(vacancy_id)
    async with get_db() as db:
        await db.execute(
            f"UPDATE vacancies SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        await db.commit()


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
    """Update vacancy status and bump updated_at."""
    log.info("DB: vacancy #%d status -> %s", vacancy_id, status)
    async with get_db() as db:
        await db.execute(
            """
            UPDATE vacancies
            SET status = ?, updated_at = datetime('now')
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


async def clear_analysis_error(vacancy_id: int) -> None:
    """Clear analysis_error when vacancy is re-queued for analysis."""
    async with get_db() as db:
        await db.execute(
            "UPDATE vacancies SET analysis_error = NULL WHERE id = ?",
            (vacancy_id,),
        )
        await db.commit()


async def set_vacancy_applied(vacancy_id: int, applied: bool) -> None:
    """Set applied flag for a vacancy. 1 = CV submitted, 0 = not submitted."""
    async with get_db() as db:
        await db.execute(
            "UPDATE vacancies SET applied = ?, updated_at = datetime('now') WHERE id = ?",
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

        cursor = await db.execute(
            f"SELECT * FROM vacancies {where} ORDER BY created_at DESC LIMIT ?",
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
) -> int:
    """Record one LLM API call for cost tracking and unit economics analysis.

    Input breakdown (profile/prompt/user) is estimated from text length (len//4, ±10%).
    API-reported totals (input/output/cache) are exact from the response.
    user_id: optional FK for per-user cost analytics.
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
                 elapsed_ms, cost_usd)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (vacancy_id, user_id, phase, model,
             profile_tokens, prompt_tokens, user_tokens,
             input_tokens, output_tokens,
             cache_write_tokens, cache_read_tokens,
             budget_tokens, thinking_tokens,
             elapsed_ms, round(cost_usd, 6)),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


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
            "SELECT llm_model, thinking_effort FROM user_settings WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
    if row is None:
        return {}
    return {
        "llm_model": row["llm_model"],          # None if not overridden
        "thinking_effort": row["thinking_effort"],
    }


async def set_user_settings(
    user_id: int,
    llm_model: str | None = None,
    thinking_effort: str = "off",
) -> None:
    """Upsert LLM settings for user. llm_model=None means use env default."""
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO user_settings (user_id, llm_model, thinking_effort, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                llm_model = excluded.llm_model,
                thinking_effort = excluded.thinking_effort,
                updated_at = excluded.updated_at
            """,
            (user_id, llm_model, thinking_effort),
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
