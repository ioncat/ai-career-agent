-- agent-hub SQLite schema
-- Applied via db/database.py:init_db() on startup
-- Never execute directly against a running DB — use init_db()

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ── users ─────────────────────────────────────────────────────────────────────
-- One row per candidate. user_id=1 is the default user (seeded from TELEGRAM_CHAT_ID).
-- skill_type routes ALL pipeline phases to prompts/[skill_type]/ (pm | generic).

CREATE TABLE IF NOT EXISTS users (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_chat_id INTEGER UNIQUE,              -- NULL allowed for local/API-only users
    name             TEXT    NOT NULL DEFAULT '',
    skill_type       TEXT    NOT NULL DEFAULT 'pm', -- 'pm' | 'generic'
    profile_json     TEXT,                        -- synthesised profile (JSON); NULL until onboarding complete
    onboarding_step  TEXT,                        -- FSM resume point: NULL | 'awaiting_name' | 'awaiting_skill' | 'awaiting_pdf' | 'interview' | 'done'
    progressive_profile TEXT,                       -- EPIC-24: DB profile — structured roles {roles:[{id,narrative,key_results[],framing[],caveats[],tags[]}]}
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
    -- NOTE: profile_json stored as single column for simplicity.
    -- Known trade-off: no versioning, single-writer per user.
    -- Production path: extract to separate `profiles` table with history.
    -- See docs/discovery/core-differentiators.md — "Profile Storage".
);

CREATE INDEX IF NOT EXISTS idx_users_telegram ON users (telegram_chat_id);

-- ── vacancies ────────────────────────────────────────────────────────────────
-- One row per unique job posting URL.
-- markdown_path: relative path from project root, e.g. "vacancies/djinni/2024-01/job-123/JD.md"

CREATE TABLE IF NOT EXISTS vacancies (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    url           TEXT    NOT NULL UNIQUE,
    title         TEXT,
    site          TEXT,                   -- 'djinni' | 'dou' | 'linkedin' | 'other'
    markdown_path TEXT,                   -- path to JD.md on filesystem
    status        TEXT    NOT NULL DEFAULT 'fetched',
                                          -- fetched | analyzing | analyzed | generating | done | error
    warnings      TEXT    NOT NULL DEFAULT '',
                                          -- semicolon-separated soft flags (imported from tracker or analysis)
    salary        TEXT,                   -- e.g. "$4500" or "3000–4500 USD"
    analysis_json TEXT,                   -- structured pipeline data per phase:
                                          -- {"p1":{company_type,role_archetype,role_balance,autonomy,dominant_culture},
                                          --  "p2":{fit_score,recommendation,category,key_barriers[],hidden_risks[],warnings[],salary,fit_dimensions{}},
                                          --  "p3":{name_variant,cv_language,changes_count},
                                          --  "p4":{cover_language}}
    published_at  TEXT,                   -- ISO 8601 UTC — when vacancy was published on job board (from RSS pubDate)
    applied       INTEGER NOT NULL DEFAULT 0,
                                          -- 1 = CV was submitted to this vacancy, 0 = not yet
    starred       INTEGER NOT NULL DEFAULT 0,
                                          -- 1 = marked as favourite, 0 = normal
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_vacancies_status ON vacancies (status);
CREATE INDEX IF NOT EXISTS idx_vacancies_site   ON vacancies (site);

-- ── pipeline_runs ─────────────────────────────────────────────────────────────
-- One row per phase execution attempt per vacancy.
-- result_path: path to output artifact (analysis.md, cv.pdf, etc.)

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    vacancy_id    INTEGER NOT NULL REFERENCES vacancies(id) ON DELETE CASCADE,
    phase         TEXT    NOT NULL,       -- 'phase1' | 'phase2' | 'phase3' | 'phase3_5' | 'phase4'
    status        TEXT    NOT NULL DEFAULT 'pending',
                                          -- pending | running | done | error
    result_path   TEXT,
    error_message TEXT,
    started_at    TEXT,
    finished_at   TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_pipeline_vacancy ON pipeline_runs (vacancy_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_status  ON pipeline_runs (status);

-- ── llm_usage ─────────────────────────────────────────────────────────────────
-- One row per LLM API call. Enables cost analysis per vacancy, per phase,
-- per model, and cache efficiency tracking (unit economics).

CREATE TABLE IF NOT EXISTS llm_usage (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    vacancy_id           INTEGER REFERENCES vacancies(id) ON DELETE SET NULL,
    phase                TEXT    NOT NULL,   -- 'phase1' | 'phase2' | 'phase3' | 'phase3_5' | 'phase4'
    model                TEXT    NOT NULL,
    -- Input breakdown (estimated from len//4 — approx ±10%)
    profile_tokens       INTEGER NOT NULL DEFAULT 0,   -- PROFILE.md system block
    prompt_tokens        INTEGER NOT NULL DEFAULT 0,   -- phase prompt (phase1_analysis.md etc)
    user_tokens          INTEGER NOT NULL DEFAULT 0,   -- user message: JD / JD+analysis / etc
    -- API-reported totals (exact)
    input_tokens         INTEGER NOT NULL DEFAULT 0,   -- total charged input (excl cache reads)
    output_tokens        INTEGER NOT NULL DEFAULT 0,   -- total output incl thinking tokens
    cache_write_tokens   INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens    INTEGER NOT NULL DEFAULT 0,
    -- Extended Thinking
    budget_tokens        INTEGER NOT NULL DEFAULT 0,   -- thinking budget requested
    thinking_tokens      INTEGER NOT NULL DEFAULT 0,   -- thinking tokens used (estimated)
    -- Timing
    elapsed_ms           INTEGER NOT NULL DEFAULT 0,   -- wall-clock API call duration
    -- Cost
    cost_usd             REAL    NOT NULL DEFAULT 0.0,
    created_at           TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_llm_usage_vacancy ON llm_usage (vacancy_id);
CREATE INDEX IF NOT EXISTS idx_llm_usage_phase   ON llm_usage (phase);
CREATE INDEX IF NOT EXISTS idx_llm_usage_date    ON llm_usage (created_at);

-- ── push_subscriptions ────────────────────────────────────────────────────────
-- Web Push (VAPID) subscriptions for browser / PWA notifications.
-- endpoint is unique per browser profile; p256dh + auth = encryption keys.

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint    TEXT    NOT NULL UNIQUE,
    p256dh      TEXT    NOT NULL,
    auth        TEXT    NOT NULL,
    user_agent  TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_push_user ON push_subscriptions (user_id);

-- ── user_settings ─────────────────────────────────────────────────────────────
-- Per-user overrides for LLM model and thinking effort.
-- NULL columns fall back to env-var defaults (LLM_MODEL, etc.).
-- Admin-only in production (once EPIC-25 auth lands); freely editable during dev.

-- ── system_kv ─────────────────────────────────────────────────────────────────
-- Generic key-value store for system-level caches (e.g. available model lists).
-- updated_at used for TTL checks — no explicit expiry column (caller decides TTL).

CREATE TABLE IF NOT EXISTS system_kv (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── user_settings ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_settings (
    user_id         INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    llm_model       TEXT,                            -- NULL = use LLM_MODEL env default
    thinking_effort TEXT    NOT NULL DEFAULT 'off',  -- 'off'|'low'|'medium'|'high'|'xhigh'|'max'
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
