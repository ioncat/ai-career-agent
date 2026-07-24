"""
tests/test_db.py — contract tests for db/database.py.

Run: python -m pytest tests/test_db.py -v
Uses a temporary DB file, cleaned up after each test.
"""

import pytest
import pytest_asyncio

from db import database
from db.database import normalize_url, extract_site


@pytest_asyncio.fixture(autouse=True)
async def temp_db(tmp_path):
    """Point database module at a fresh temp DB for each test."""
    database.configure(tmp_path / "test.db")
    await database.init_db()
    yield
    # cleanup handled by tmp_path fixture


# ── init_db ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_init_db_idempotent():
    """init_db() can be called twice without error."""
    await database.init_db()  # second call


# ── vacancies ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_insert_and_get_vacancy():
    vid = await database.insert_vacancy(
        url="https://djinni.co/jobs/123/",
        title="Backend Dev",
        site="djinni",
        markdown_path="vacancies/djinni/job-123/JD.md",
    )
    assert isinstance(vid, int)
    assert vid > 0

    row = await database.get_vacancy_by_url("https://djinni.co/jobs/123/")
    assert row is not None
    assert row["title"] == "Backend Dev"
    assert row["site"] == "djinni"
    assert row["status"] == "fetched"


@pytest.mark.asyncio
async def test_get_vacancy_by_id():
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/456/")
    row = await database.get_vacancy_by_id(vid)
    assert row is not None
    assert row["url"] == "https://djinni.co/jobs/456"  # normalised: trailing slash stripped


@pytest.mark.asyncio
async def test_get_vacancy_not_found():
    row = await database.get_vacancy_by_url("https://example.com/not-there")
    assert row is None


@pytest.mark.asyncio
async def test_update_vacancy_status():
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/789/")
    await database.update_vacancy_status(vid, "analyzing")

    row = await database.get_vacancy_by_id(vid)
    assert row["status"] == "analyzing"


@pytest.mark.asyncio
async def test_list_vacancies():
    await database.insert_vacancy(url="https://djinni.co/jobs/1/")
    await database.insert_vacancy(url="https://djinni.co/jobs/2/")
    rows = await database.list_vacancies()
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_list_vacancies_filter_status():
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/10/")
    await database.update_vacancy_status(vid, "done")
    await database.insert_vacancy(url="https://djinni.co/jobs/11/")  # stays 'fetched'

    done = await database.list_vacancies(status="done")
    assert len(done) == 1
    assert done[0]["url"] == "https://djinni.co/jobs/10"  # normalised


# ── pipeline_runs ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_insert_pipeline_run():
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/20/")
    run_id = await database.insert_pipeline_run(vid, "phase1")
    assert isinstance(run_id, int)


@pytest.mark.asyncio
async def test_update_pipeline_run_done():
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/21/")
    run_id = await database.insert_pipeline_run(vid, "phase1")

    await database.update_pipeline_run(run_id, "running")
    await database.update_pipeline_run(run_id, "done", result_path="vacancies/job-21/analysis.md")

    runs = await database.get_pipeline_runs(vid)
    assert len(runs) == 1
    assert runs[0]["status"] == "done"
    assert runs[0]["result_path"] == "vacancies/job-21/analysis.md"
    assert runs[0]["finished_at"] is not None


@pytest.mark.asyncio
async def test_update_pipeline_run_error():
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/22/")
    run_id = await database.insert_pipeline_run(vid, "phase2")

    await database.update_pipeline_run(run_id, "error", error_message="Claude API timeout")

    runs = await database.get_pipeline_runs(vid)
    assert runs[0]["status"] == "error"
    assert "timeout" in runs[0]["error_message"]


# ── users ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_insert_and_get_user_by_id():
    uid = await database.insert_user(name="Alex Bondarenko", telegram_chat_id=123456, skill_type="pm")
    assert isinstance(uid, int)
    assert uid > 0

    row = await database.get_user_by_id(uid)
    assert row is not None
    assert row["name"] == "Alex Bondarenko"
    assert row["telegram_chat_id"] == 123456
    assert row["skill_type"] == "pm"


@pytest.mark.asyncio
async def test_get_user_by_telegram_id():
    await database.insert_user(name="Maria Beleshko", telegram_chat_id=999888, skill_type="generic")
    row = await database.get_user_by_telegram_id(999888)
    assert row is not None
    assert row["name"] == "Maria Beleshko"
    assert row["skill_type"] == "generic"


@pytest.mark.asyncio
async def test_get_user_not_found():
    row = await database.get_user_by_id(9999)
    assert row is None

    row2 = await database.get_user_by_telegram_id(0)
    assert row2 is None


@pytest.mark.asyncio
async def test_get_or_create_default_user_creates_new():
    uid = await database.get_or_create_default_user(telegram_chat_id=111222, name="New User", skill_type="pm")
    assert isinstance(uid, int)
    row = await database.get_user_by_id(uid)
    assert row["name"] == "New User"


@pytest.mark.asyncio
async def test_get_or_create_default_user_returns_existing():
    uid1 = await database.get_or_create_default_user(telegram_chat_id=333444, name="Existing", skill_type="pm")
    uid2 = await database.get_or_create_default_user(telegram_chat_id=333444, name="Existing", skill_type="pm")
    assert uid1 == uid2  # idempotent — same user returned


@pytest.mark.asyncio
async def test_list_users():
    await database.insert_user(name="User A", telegram_chat_id=1001, skill_type="pm")
    await database.insert_user(name="User B", telegram_chat_id=1002, skill_type="generic")
    users = await database.list_users()
    assert len(users) == 2
    assert users[0]["name"] == "User A"
    assert users[1]["skill_type"] == "generic"


@pytest.mark.asyncio
async def test_update_user_skill_type():
    uid = await database.insert_user(name="Switch User", telegram_chat_id=5555, skill_type="pm")
    await database.update_user_skill_type(uid, "generic")
    row = await database.get_user_by_id(uid)
    assert row["skill_type"] == "generic"


@pytest.mark.asyncio
async def test_user_telegram_id_unique_constraint():
    """Duplicate telegram_chat_id must raise IntegrityError."""
    import sqlite3
    await database.insert_user(name="First", telegram_chat_id=77777)
    with pytest.raises(Exception):  # sqlite3.IntegrityError wrapped by aiosqlite
        await database.insert_user(name="Duplicate", telegram_chat_id=77777)


# ── user_id FK — vacancies & llm_usage ───────────────────────────────────────

@pytest.mark.asyncio
async def test_insert_vacancy_with_user_id():
    uid = await database.insert_user(name="Alex", telegram_chat_id=11111, skill_type="pm")
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/100/", user_id=uid)

    row = await database.get_vacancy_by_id(vid)
    assert row["user_id"] == uid


@pytest.mark.asyncio
async def test_insert_vacancy_without_user_id_is_null():
    """Backward compat: vacancy without user_id inserts fine, user_id=NULL."""
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/200/")
    row = await database.get_vacancy_by_id(vid)
    assert row["user_id"] is None


@pytest.mark.asyncio
async def test_list_vacancies_filter_by_user_id():
    uid1 = await database.insert_user(name="User1", telegram_chat_id=22221, skill_type="pm")
    uid2 = await database.insert_user(name="User2", telegram_chat_id=22222, skill_type="generic")

    await database.insert_vacancy(url="https://djinni.co/jobs/300/", user_id=uid1)
    await database.insert_vacancy(url="https://djinni.co/jobs/301/", user_id=uid1)
    await database.insert_vacancy(url="https://djinni.co/jobs/302/", user_id=uid2)

    rows1 = await database.list_vacancies(user_id=uid1)
    rows2 = await database.list_vacancies(user_id=uid2)
    all_rows = await database.list_vacancies()

    assert len(rows1) == 2
    assert len(rows2) == 1
    assert len(all_rows) == 3


@pytest.mark.asyncio
async def test_list_vacancies_filter_status_and_user_id():
    uid = await database.insert_user(name="User3", telegram_chat_id=33331, skill_type="pm")
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/400/", user_id=uid)
    await database.update_vacancy_status(vid, "done")
    await database.insert_vacancy(url="https://djinni.co/jobs/401/", user_id=uid)  # stays fetched

    done = await database.list_vacancies(status="done", user_id=uid)
    assert len(done) == 1
    assert done[0]["url"] == "https://djinni.co/jobs/400"  # normalised


@pytest.mark.asyncio
async def test_insert_llm_usage_with_user_id():
    uid = await database.insert_user(name="Alex", telegram_chat_id=44441, skill_type="pm")
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/500/", user_id=uid)

    row_id = await database.insert_llm_usage(
        phase="phase1",
        model="claude-sonnet-4-6",
        input_tokens=100,
        output_tokens=200,
        cache_write_tokens=0,
        cache_read_tokens=0,
        cost_usd=0.001,
        vacancy_id=vid,
        user_id=uid,
    )
    assert isinstance(row_id, int)
    assert row_id > 0


# ── reset_stuck_statuses ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reset_stuck_statuses_resets_all_three_in_progress_states():
    """analyzing/cv_generating/fetching left by a prior crash all get reset —
    fetching→queued closes the gap that let 47→264 rows accumulate across
    dev-session restarts (RSSWatcher's own retry never runs if the process
    dies before reaching its except block)."""
    v1 = await database.insert_vacancy(url="https://djinni.co/jobs/r1/", status="analyzing")
    v2 = await database.insert_vacancy(url="https://djinni.co/jobs/r2/", status="cv_generating")
    v3 = await database.insert_vacancy(url="https://djinni.co/jobs/r3/", status="fetching")

    await database.reset_stuck_statuses()

    assert (await database.get_vacancy_by_id(v1))["status"] == "analysis_queued"
    assert (await database.get_vacancy_by_id(v2))["status"] == "cv_queued"
    assert (await database.get_vacancy_by_id(v3))["status"] == "queued"


@pytest.mark.asyncio
async def test_reset_stuck_statuses_leaves_other_statuses_untouched():
    v = await database.insert_vacancy(url="https://djinni.co/jobs/r4/", status="analyzed")
    await database.reset_stuck_statuses()
    assert (await database.get_vacancy_by_id(v))["status"] == "analyzed"


@pytest.mark.asyncio
async def test_reset_stuck_statuses_noop_on_empty_db():
    await database.reset_stuck_statuses()  # must not raise


# ── fetch_attempts / give_up_fetch (RSSWatcher retry cap) ───────────────────

@pytest.mark.asyncio
async def test_increment_fetch_attempts_starts_at_zero_and_counts_up():
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/fa1/", status="fetching")
    first = await database.increment_fetch_attempts(vid)
    second = await database.increment_fetch_attempts(vid)
    assert first == 1
    assert second == 2


@pytest.mark.asyncio
async def test_give_up_fetch_declines_and_records_reason():
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/fa2/", status="fetching")
    await database.give_up_fetch(vid, "Fetch failed 5x — giving up: 503")
    row = await database.get_vacancy_by_id(vid)
    assert row["status"] == "declined"
    assert row["analysis_error"] == "Fetch failed 5x — giving up: 503"


# ── normalize_url ─────────────────────────────────────────────────────────────

class TestNormalizeUrl:
    def test_strips_utm_params(self):
        url = "https://jobs.dou.ua/vacancies/360005/?utm_source=jobsrss"
        assert normalize_url(url) == "https://jobs.dou.ua/vacancies/360005"

    def test_strips_linkedin_tracking(self):
        url = "https://www.linkedin.com/jobs/view/123/?trk=abc&refId=xyz&trackingId=123"
        assert normalize_url(url) == "https://www.linkedin.com/jobs/view/123"

    def test_strips_djinni_tracking(self):
        url = "https://djinni.co/jobs/789/?ref=tg_bot&pk_campaign=Telegram&pk_source=tg"
        assert normalize_url(url) == "https://djinni.co/jobs/789"

    def test_strips_trailing_slash(self):
        assert normalize_url("https://djinni.co/jobs/123/") == "https://djinni.co/jobs/123"

    def test_no_trailing_slash_unchanged(self):
        assert normalize_url("https://djinni.co/jobs/123") == "https://djinni.co/jobs/123"

    def test_lowercases_host(self):
        assert normalize_url("https://Djinni.CO/jobs/1/") == "https://djinni.co/jobs/1"

    def test_empty_string_returns_empty(self):
        assert normalize_url("") == ""

    def test_same_url_twice_is_idempotent(self):
        url = "https://jobs.dou.ua/vacancies/123/?utm_source=rss"
        assert normalize_url(normalize_url(url)) == normalize_url(url)


# ── extract_site ──────────────────────────────────────────────────────────────

class TestExtractSite:
    def test_djinni(self):
        assert extract_site("https://djinni.co/jobs/123/") == "djinni"

    def test_dou(self):
        assert extract_site("https://jobs.dou.ua/vacancies/123/") == "dou"

    def test_linkedin(self):
        assert extract_site("https://www.linkedin.com/jobs/view/456/") == "linkedin"

    def test_hh_ua(self):
        assert extract_site("https://hh.ua/vacancy/123") == "hh"

    def test_other(self):
        assert extract_site("https://example.com/jobs/1") == "other"

    def test_empty(self):
        assert extract_site("") == "other"


# ── URL deduplication via insert_vacancy + get_vacancy_by_url ─────────────────

@pytest.mark.asyncio
async def test_insert_normalises_utm_url():
    """URL with UTM params → stored as clean URL."""
    vid = await database.insert_vacancy(
        url="https://jobs.dou.ua/vacancies/123/?utm_source=jobsrss"
    )
    row = await database.get_vacancy_by_id(vid)
    assert row["url"] == "https://jobs.dou.ua/vacancies/123"


@pytest.mark.asyncio
async def test_get_by_url_finds_with_utm():
    """get_vacancy_by_url with UTM URL finds normalised entry."""
    await database.insert_vacancy(url="https://jobs.dou.ua/vacancies/456/")
    row = await database.get_vacancy_by_url(
        "https://jobs.dou.ua/vacancies/456/?utm_source=jobsrss"
    )
    assert row is not None
    assert row["url"] == "https://jobs.dou.ua/vacancies/456"


@pytest.mark.asyncio
async def test_get_by_url_finds_without_utm():
    """get_vacancy_by_url with clean URL finds entry inserted with UTM URL."""
    await database.insert_vacancy(
        url="https://jobs.dou.ua/vacancies/789/?utm_source=jobsrss"
    )
    row = await database.get_vacancy_by_url("https://jobs.dou.ua/vacancies/789/")
    assert row is not None


@pytest.mark.asyncio
async def test_insert_dedup_raises_on_duplicate():
    """Second insert of same URL (with different tracking params) raises IntegrityError."""
    import sqlite3 as _sqlite3
    await database.insert_vacancy(url="https://djinni.co/jobs/999/")
    with pytest.raises(Exception):  # IntegrityError — url UNIQUE violated
        await database.insert_vacancy(
            url="https://djinni.co/jobs/999/?ref=tg_bot&pk_campaign=Telegram"
        )


@pytest.mark.asyncio
async def test_insert_auto_infers_site_from_url():
    """site is auto-inferred when not passed explicitly."""
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/111/")
    row = await database.get_vacancy_by_id(vid)
    assert row["site"] == "djinni"

    vid2 = await database.insert_vacancy(url="https://jobs.dou.ua/vacancies/222/")
    row2 = await database.get_vacancy_by_id(vid2)
    assert row2["site"] == "dou"


@pytest.mark.asyncio
async def test_insert_explicit_site_overrides_inferred():
    """Explicit site= overrides auto-inference."""
    vid = await database.insert_vacancy(
        url="https://djinni.co/jobs/333/",
        site="other",
    )
    row = await database.get_vacancy_by_id(vid)
    assert row["site"] == "other"


# ── auto_check_title (Stage 1 pre-filter auto-trigger setting, 2026-07-23) ─────

@pytest.mark.asyncio
async def test_auto_check_title_defaults_true_with_no_row():
    """No user_settings row at all → default True (schema default, matches
    'free and already-validated, no reason to ship it off')."""
    assert await database.get_auto_check_title(1) is True


@pytest.mark.asyncio
async def test_auto_check_title_set_and_get_roundtrip():
    await database.upsert_user(1, "Test User")
    await database.set_auto_check_title(1, False)
    assert await database.get_auto_check_title(1) is False

    await database.set_auto_check_title(1, True)
    assert await database.get_auto_check_title(1) is True


@pytest.mark.asyncio
async def test_set_auto_check_title_does_not_touch_llm_settings():
    """Narrow upsert — flipping the flag must not clobber llm_provider/model/
    thinking_effort on an existing row (the reason it's a separate function
    from set_user_settings, not folded into it)."""
    await database.upsert_user(1, "Test User")
    await database.set_user_settings(1, llm_provider="ollama_api", llm_model="gemma4:e4b", thinking_effort="high")

    await database.set_auto_check_title(1, False)

    settings = await database.get_user_settings(1)
    assert settings["llm_provider"] == "ollama_api"
    assert settings["llm_model"] == "gemma4:e4b"
    assert settings["thinking_effort"] == "high"
    assert await database.get_auto_check_title(1) is False


# ── provider_config_snapshots (2026-07-24 Settings redesign) ───────────────────

@pytest.mark.asyncio
async def test_get_provider_snapshot_missing_returns_none():
    assert await database.get_provider_snapshot("claude_api") is None


@pytest.mark.asyncio
async def test_set_and_get_provider_snapshot_roundtrip():
    phase_configs = {"prefilter": {"provider": "claude_api", "model": "claude-haiku-4-5", "thinking_effort": "low"}}
    await database.set_provider_snapshot("claude_api", "claude-opus-4-5", "high", phase_configs)

    snapshot = await database.get_provider_snapshot("claude_api")
    assert snapshot["model"] == "claude-opus-4-5"
    assert snapshot["thinking_effort"] == "high"
    assert snapshot["phase_configs"] == phase_configs


@pytest.mark.asyncio
async def test_set_provider_snapshot_upserts():
    await database.set_provider_snapshot("ollama_api", "qwen2.5:32b", "off", {})
    await database.set_provider_snapshot("ollama_api", "gemma4:e4b", "medium", {"phase1": {"provider": "ollama_api", "model": None, "thinking_effort": "off"}})

    snapshot = await database.get_provider_snapshot("ollama_api")
    assert snapshot["model"] == "gemma4:e4b"
    assert snapshot["thinking_effort"] == "medium"
    assert "phase1" in snapshot["phase_configs"]


@pytest.mark.asyncio
async def test_provider_snapshots_are_independent_per_provider():
    await database.set_provider_snapshot("claude_api", "claude-opus-4-5", "high", {})
    await database.set_provider_snapshot("ollama_api", "qwen2.5:32b", "off", {})

    assert (await database.get_provider_snapshot("claude_api"))["model"] == "claude-opus-4-5"
    assert (await database.get_provider_snapshot("ollama_api"))["model"] == "qwen2.5:32b"


@pytest.mark.asyncio
async def test_get_provider_snapshot_malformed_json_falls_back_to_empty_dict():
    """Defensive: a hand-edited or corrupted phase_configs blob must not crash
    the read path — same fail-open principle as blocker_reasons parsing."""
    async with database.get_db() as db:
        await db.execute(
            "INSERT INTO provider_config_snapshots (provider, model, thinking_effort, phase_configs) VALUES (?, ?, ?, ?)",
            ("claude_api", "claude-opus-4-5", "off", "not valid json"),
        )
        await db.commit()

    snapshot = await database.get_provider_snapshot("claude_api")
    assert snapshot["phase_configs"] == {}
