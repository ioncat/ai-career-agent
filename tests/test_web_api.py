"""
tests/test_web_api.py — contract tests for web/api.py endpoints.

Tests user_id filter on GET / and GET /api/vacancies, plus GET /api/users.
Uses FastAPI TestClient + real temp DB (no mocks).

Run: python -m pytest tests/test_web_api.py -v
"""

import datetime

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from core import config_store
from db import database


@pytest_asyncio.fixture(autouse=True)
async def temp_db(tmp_path, monkeypatch):
    """Point web/api.py and database module at a fresh temp DB.

    Also resets config_store's process-wide seed flag — each test gets a
    fresh DB, so it must also get a fresh "not yet seeded" state, otherwise
    a provider seeded by an earlier test lingers and env monkeypatches in
    this test have no effect (config_store only reads env once per process).
    """
    db_path = tmp_path / "test.db"
    database.configure(db_path)
    await database.init_db()
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("VACANCIES_PATH", str(tmp_path / "vacancies"))
    config_store._seeded = False
    yield


@pytest.fixture()
def client(tmp_path):
    """FastAPI TestClient with lifespan."""
    import os
    os.environ.setdefault("DB_PATH", str(tmp_path / "test.db"))
    from web.api import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── GET /api/health ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_no_worker(client):
    """GET /api/health returns worker_available=False when no worker attached."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["worker_available"] is False


@pytest.mark.asyncio
async def test_health_with_worker(client):
    """GET /api/health returns worker_available=True when worker is on app.state."""
    from web.api import app

    class _FakeWorker:
        pass

    app.state.analysis_worker = _FakeWorker()
    try:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["worker_available"] is True
    finally:
        app.state.analysis_worker = None


# ── GET /api/users ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_users_returns_list(client):
    """GET /api/users returns list of users (may be empty on fresh DB)."""
    await database.insert_user(name="Alice", telegram_chat_id=1001, skill_type="pm")
    await database.insert_user(name="Bob", telegram_chat_id=1002, skill_type="generic")

    resp = client.get("/api/users")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    names = {u["name"] for u in data}
    assert names == {"Alice", "Bob"}


# ── GET /api/vacancies — stage field ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_vacancies_includes_stage(client):
    """GET /api/vacancies exposes the computed `stage` field for Flutter folder routing."""
    uid = await database.insert_user(name="StageUser", telegram_chat_id=2100, skill_type="pm")
    v_inbox = await database.insert_vacancy(url="https://djinni.co/jobs/st1/", user_id=uid)
    v_analyzed = await database.insert_vacancy(url="https://djinni.co/jobs/st2/", user_id=uid)
    await database.update_vacancy_status(v_analyzed, "analyzed")
    v_processed = await database.insert_vacancy(url="https://djinni.co/jobs/st3/", user_id=uid)
    await database.update_vacancy_status(v_processed, "cv_generated")
    v_applied = await database.insert_vacancy(url="https://djinni.co/jobs/st4/", user_id=uid)
    await database.update_vacancy_status(v_applied, "analyzed")
    await database.set_vacancy_applied(v_applied, True)
    v_archive = await database.insert_vacancy(url="https://djinni.co/jobs/st5/", user_id=uid)
    await database.update_vacancy_status(v_archive, "declined")

    data = {v["id"]: v["stage"] for v in client.get(f"/api/vacancies?user_id={uid}").json()}
    assert data[v_inbox] == "inbox"
    assert data[v_analyzed] == "analyzed"
    assert data[v_processed] == "processed"
    assert data[v_applied] == "applied"
    assert data[v_archive] == "archive"


@pytest.mark.asyncio
async def test_api_vacancies_blocker_checked_distinguishes_clean_from_unchecked(client):
    """Regression guard for vacancy #716 (2026-07-17): a clean pre-filter result
    (blocker_flag=false) looked identical to "never checked" in the UI, because
    there was no signal to tell them apart. blocker_checked fixes that.
    blocker_raw_output itself must NOT appear in the list response — it's heavy
    and only needed for the single-vacancy detail fetch."""
    uid = await database.insert_user(name="BlockerUser", telegram_chat_id=2200, skill_type="pm")
    v_unchecked = await database.insert_vacancy(url="https://djinni.co/jobs/bc1/", user_id=uid)
    v_clean = await database.insert_vacancy(url="https://djinni.co/jobs/bc2/", user_id=uid)
    await database.set_vacancy_blocker(v_clean, False, [], raw_output="BLOCKED: no")
    v_blocked = await database.insert_vacancy(url="https://djinni.co/jobs/bc3/", user_id=uid)
    await database.set_vacancy_blocker(v_blocked, True, ["english: C1 required"], raw_output="BLOCKED: yes\n...")

    data = {v["id"]: v for v in client.get(f"/api/vacancies?user_id={uid}").json()}

    assert data[v_unchecked]["blocker_checked"] is False
    assert data[v_unchecked]["blocker_flag"] is False

    assert data[v_clean]["blocker_checked"] is True
    assert data[v_clean]["blocker_flag"] is False

    assert data[v_blocked]["blocker_checked"] is True
    assert data[v_blocked]["blocker_flag"] is True

    for v in data.values():
        assert "blocker_raw_output" not in v


# ── GET /api/vacancies?user_id=N ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_vacancies_filter_by_user_id(client):
    """GET /api/vacancies?user_id=N returns only that user's vacancies."""
    uid1 = await database.insert_user(name="Alice", telegram_chat_id=2001, skill_type="pm")
    uid2 = await database.insert_user(name="Bob", telegram_chat_id=2002, skill_type="generic")

    await database.insert_vacancy(url="https://djinni.co/jobs/1/", user_id=uid1)
    await database.insert_vacancy(url="https://djinni.co/jobs/2/", user_id=uid1)
    await database.insert_vacancy(url="https://djinni.co/jobs/3/", user_id=uid2)

    resp1 = client.get(f"/api/vacancies?user_id={uid1}")
    assert resp1.status_code == 200
    assert len(resp1.json()) == 2

    resp2 = client.get(f"/api/vacancies?user_id={uid2}")
    assert resp2.status_code == 200
    assert len(resp2.json()) == 1

    resp_all = client.get("/api/vacancies")
    assert resp_all.status_code == 200
    assert len(resp_all.json()) == 3


# ── folder_path resolution (Open Folder button) ────────────────────────────────

@pytest.mark.asyncio
async def test_folder_path_resolves_relative_markdown_path_to_absolute(client):
    """folder_path must be absolute — a relative one makes explorer.exe silently
    open the default Documents folder instead of the vacancy folder."""
    import os as _os
    from pathlib import Path as _Path

    uid = await database.insert_user(name="FolderUser", telegram_chat_id=6001, skill_type="pm")
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/folder1/", user_id=uid)
    relative = _os.path.join("vacancies", "inbox", str(uid), "test-folder", "JD.md")
    await database.update_vacancy_fields(vid, markdown_path=relative)

    resp = client.get(f"/api/vacancies?user_id={uid}")
    assert resp.status_code == 200
    item = next(v for v in resp.json() if v["id"] == vid)

    assert item["folder_path"] is not None
    assert _Path(item["folder_path"]).is_absolute()
    assert item["folder_path"].endswith(_os.path.join("vacancies", "inbox", str(uid), "test-folder"))


@pytest.mark.asyncio
async def test_folder_path_none_when_no_markdown_path(client):
    """No markdown_path yet (e.g. queued vacancy) → folder_path is null, not a bad path."""
    uid = await database.insert_user(name="NoFolderUser", telegram_chat_id=6002, skill_type="pm")
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/folder2/", user_id=uid)

    resp = client.get(f"/api/vacancies?user_id={uid}")
    item = next(v for v in resp.json() if v["id"] == vid)
    assert item["folder_path"] is None


# ── GET /?user_id=N (tracker page) ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tracker_page_user_id_filter(client):
    """GET /?user_id=N returns HTML and does not raise."""
    uid = await database.insert_user(name="Alice", telegram_chat_id=3001, skill_type="pm")
    await database.insert_vacancy(url="https://djinni.co/jobs/10/", user_id=uid)

    resp = client.get(f"/?user_id={uid}")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


# ── POST /api/new-vacancy ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_new_vacancy_queues_successfully(client):
    """POST /api/new-vacancy inserts vacancy with status='queued', returns 201."""
    uid = await database.insert_user(name="Alice", telegram_chat_id=4001, skill_type="pm")

    resp = client.post("/api/new-vacancy", json={
        "url": "https://djinni.co/jobs/100/",
        "title": "Senior PM",
        "feed_name": "DOU.ua — PM",
        "user_id": uid,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "queued"
    assert "vacancy_id" in data

    # Vacancy is in DB with queued status
    rows = await database.list_vacancies(status="queued", user_id=uid)
    assert len(rows) == 1
    assert rows[0]["url"] == "https://djinni.co/jobs/100"  # normalised: trailing slash stripped


@pytest.mark.asyncio
async def test_new_vacancy_duplicate_returns_409(client):
    """POST /api/new-vacancy with duplicate URL returns 409."""
    uid = await database.insert_user(name="Bob", telegram_chat_id=4002, skill_type="pm")
    url = "https://djinni.co/jobs/200/"

    resp1 = client.post("/api/new-vacancy", json={"url": url, "user_id": uid})
    assert resp1.status_code == 201

    resp2 = client.post("/api/new-vacancy", json={"url": url, "user_id": uid})
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_new_vacancy_minimal_payload(client):
    """POST /api/new-vacancy with only url field (no title/feed_name/user_id) succeeds."""
    resp = client.post("/api/new-vacancy", json={"url": "https://djinni.co/jobs/300/"})
    assert resp.status_code == 201


def test_sanitize_published_at_none_passthrough():
    from web.api import _sanitize_published_at
    assert _sanitize_published_at(None) is None


def test_sanitize_published_at_unparseable_passthrough():
    from web.api import _sanitize_published_at
    assert _sanitize_published_at("not-a-date") == "not-a-date"


def test_sanitize_published_at_future_replaced():
    from web.api import _sanitize_published_at
    future = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    result = _sanitize_published_at(future)
    assert result != future


@pytest.mark.asyncio
async def test_new_vacancy_stale_published_at_replaced_with_fetch_time(client):
    """A brand-new vacancy with an implausibly old feed pubDate (>24h stale —
    Djinni re-crawl/feed-lag artifact, found 2026-07-24 vacancy #823) gets
    published_at replaced with fetch time, not silently buried in a
    date-sorted inbox."""
    uid = await database.insert_user(name="StaleDate", telegram_chat_id=6001, skill_type="pm")
    before = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=5)

    resp = client.post("/api/new-vacancy", json={
        "url": "https://djinni.co/jobs/500/",
        "user_id": uid,
        "published_at": "2026-06-01T10:00:00",  # weeks stale relative to "now"
    })
    assert resp.status_code == 201
    vacancy_id = resp.json()["vacancy_id"]

    row = await database.get_vacancy_by_id(vacancy_id)
    stored = datetime.datetime.fromisoformat(row["published_at"]).replace(tzinfo=datetime.timezone.utc)
    assert stored >= before


@pytest.mark.asyncio
async def test_new_vacancy_fresh_published_at_kept_as_is(client):
    """A plausible, recent published_at is trusted verbatim — the guard only
    kicks in on implausible values."""
    uid = await database.insert_user(name="FreshDate", telegram_chat_id=6002, skill_type="pm")
    fresh = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")

    resp = client.post("/api/new-vacancy", json={
        "url": "https://djinni.co/jobs/501/",
        "user_id": uid,
        "published_at": fresh,
    })
    assert resp.status_code == 201
    vacancy_id = resp.json()["vacancy_id"]

    row = await database.get_vacancy_by_id(vacancy_id)
    assert row["published_at"] == fresh


@pytest.mark.asyncio
async def test_new_vacancy_republish_declined(client):
    """POST /api/new-vacancy for a declined vacancy with newer published_at returns republished."""
    uid = await database.insert_user(name="RepubUser", telegram_chat_id=5001, skill_type="pm")
    url = "https://djinni.co/jobs/400/"

    # Insert with status=declined and old published_at
    vid = await database.insert_vacancy(url=url, user_id=uid, published_at="2026-06-01T10:00:00")
    await database.update_vacancy_status(vid, "declined")

    # Re-publish with newer published_at
    resp = client.post("/api/new-vacancy", json={
        "url": url,
        "user_id": uid,
        "published_at": "2026-07-01T10:00:00",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "republished"
    assert data["vacancy_id"] == vid

    # Vacancy should be back to fetched with republished_at set
    row = await database.get_vacancy_by_id(vid)
    assert row["status"] == "fetched"
    assert row["republished_at"] is not None


@pytest.mark.asyncio
async def test_new_vacancy_republish_same_date_returns_409(client):
    """POST /api/new-vacancy for a declined vacancy with same/older published_at → 409."""
    uid = await database.insert_user(name="SameDateUser", telegram_chat_id=5002, skill_type="pm")
    url = "https://djinni.co/jobs/401/"

    vid = await database.insert_vacancy(url=url, user_id=uid, published_at="2026-06-01T10:00:00")
    await database.update_vacancy_status(vid, "declined")

    resp = client.post("/api/new-vacancy", json={
        "url": url,
        "user_id": uid,
        "published_at": "2026-06-01T10:00:00",  # same date — not a republish
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_new_vacancy_analyzed_bumps_published_at(client):
    """Analyzed vacancy re-published with newer date → published_at bumped, status unchanged, no badge."""
    uid = await database.insert_user(name="AnalyzedUser", telegram_chat_id=5003, skill_type="pm")
    url = "https://djinni.co/jobs/402/"

    vid = await database.insert_vacancy(url=url, user_id=uid, published_at="2026-06-01T10:00:00")
    await database.update_vacancy_status(vid, "analyzed")

    resp = client.post("/api/new-vacancy", json={
        "url": url,
        "user_id": uid,
        "published_at": "2026-07-01T10:00:00",
    })
    assert resp.status_code == 201
    assert resp.json()["status"] == "bumped"

    row = await database.get_vacancy_by_id(vid)
    assert row["published_at"] == "2026-07-01T10:00:00"  # rises in date-sorted inbox
    assert row["status"] == "analyzed"                    # no status change
    assert row["republished_at"] is None                  # no republished badge


@pytest.mark.asyncio
async def test_new_vacancy_bump_null_published_at(client):
    """Analyzed vacancy with NULL published_at (pre-EPIC-26) gets bumped when RSS sends a date."""
    uid = await database.insert_user(name="NullPubUser", telegram_chat_id=5004, skill_type="pm")
    url = "https://jobs.dou.ua/companies/x/vacancies/360603/"

    vid = await database.insert_vacancy(url=url, user_id=uid, published_at=None)
    await database.update_vacancy_status(vid, "analyzed")

    resp = client.post("/api/new-vacancy", json={
        "url": url,
        "user_id": uid,
        "published_at": "2026-07-13T10:00:00",
    })
    assert resp.status_code == 201
    assert resp.json()["status"] == "bumped"
    row = await database.get_vacancy_by_id(vid)
    assert row["published_at"] == "2026-07-13T10:00:00"


@pytest.mark.asyncio
async def test_new_vacancy_analyzed_same_date_returns_409(client):
    """Analyzed vacancy re-published with same/older date → 409, no change."""
    uid = await database.insert_user(name="AnalyzedSame", telegram_chat_id=5005, skill_type="pm")
    url = "https://djinni.co/jobs/403/"

    vid = await database.insert_vacancy(url=url, user_id=uid, published_at="2026-06-01T10:00:00")
    await database.update_vacancy_status(vid, "analyzed")

    resp = client.post("/api/new-vacancy", json={
        "url": url,
        "user_id": uid,
        "published_at": "2026-06-01T10:00:00",
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_new_vacancy_active_not_disturbed(client):
    """Vacancy in-flight (analyzing) is left untouched on re-publish → 409, no date change."""
    uid = await database.insert_user(name="ActiveUser", telegram_chat_id=5006, skill_type="pm")
    url = "https://djinni.co/jobs/404/"

    vid = await database.insert_vacancy(url=url, user_id=uid, published_at="2026-06-01T10:00:00")
    await database.update_vacancy_status(vid, "analyzing")

    resp = client.post("/api/new-vacancy", json={
        "url": url,
        "user_id": uid,
        "published_at": "2026-07-01T10:00:00",
    })
    assert resp.status_code == 409
    row = await database.get_vacancy_by_id(vid)
    assert row["published_at"] == "2026-06-01T10:00:00"  # untouched
    assert row["status"] == "analyzing"


# ── PATCH /api/vacancies/{id}/applied ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_applied_true(client):
    """PATCH /api/vacancies/{id}/applied with applied=true sets flag in DB."""
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/500/")

    resp = client.patch(f"/api/vacancies/{vid}/applied", json={"applied": True})
    assert resp.status_code == 200
    assert resp.json()["applied"] is True

    row = await database.get_vacancy_by_id(vid)
    assert row["applied"] == 1


@pytest.mark.asyncio
async def test_set_applied_false(client):
    """PATCH /api/vacancies/{id}/applied with applied=false clears flag in DB."""
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/501/")
    await database.set_vacancy_applied(vid, True)

    resp = client.patch(f"/api/vacancies/{vid}/applied", json={"applied": False})
    assert resp.status_code == 200

    row = await database.get_vacancy_by_id(vid)
    assert row["applied"] == 0


@pytest.mark.asyncio
async def test_set_applied_not_found(client):
    """PATCH /api/vacancies/9999/applied returns 404 for missing vacancy."""
    resp = client.patch("/api/vacancies/9999/applied", json={"applied": True})
    assert resp.status_code == 404


# ── PATCH /api/vacancies/{id}/starred ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_starred_true(client):
    """PATCH /api/vacancies/{id}/starred with starred=true sets flag in DB."""
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/510/")

    resp = client.patch(f"/api/vacancies/{vid}/starred", json={"starred": True})
    assert resp.status_code == 200
    assert resp.json()["starred"] is True

    row = await database.get_vacancy_by_id(vid)
    assert row["starred"] == 1


@pytest.mark.asyncio
async def test_set_starred_false(client):
    """PATCH /api/vacancies/{id}/starred with starred=false clears flag in DB."""
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/511/")
    await database.set_vacancy_starred(vid, True)

    resp = client.patch(f"/api/vacancies/{vid}/starred", json={"starred": False})
    assert resp.status_code == 200

    row = await database.get_vacancy_by_id(vid)
    assert row["starred"] == 0


@pytest.mark.asyncio
async def test_set_starred_not_found(client):
    """PATCH /api/vacancies/9999/starred returns 404 for missing vacancy."""
    resp = client.patch("/api/vacancies/9999/starred", json={"starred": True})
    assert resp.status_code == 404


# ── PATCH /api/vacancies/{id}/salary ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_salary(client):
    """PATCH /api/vacancies/{id}/salary persists value in DB."""
    await database.insert_user(name="Salary1", telegram_chat_id=7200, skill_type="pm")
    vid = await database.insert_vacancy(url="https://example.com/sal1", title="Salary Test", user_id=1)
    resp = client.patch(f"/api/vacancies/{vid}/salary", json={"salary": "$4500"})
    assert resp.status_code == 200
    assert resp.json()["salary"] == "$4500"
    row = await database.get_vacancy_by_id(vid)
    assert row["salary"] == "$4500"


@pytest.mark.asyncio
async def test_set_salary_clear(client):
    """PATCH /api/vacancies/{id}/salary with empty string clears the field."""
    await database.insert_user(name="Salary2", telegram_chat_id=7201, skill_type="pm")
    vid = await database.insert_vacancy(url="https://example.com/sal2", title="Salary Clear", user_id=1)
    await database.set_vacancy_salary(vid, "$3000")
    resp = client.patch(f"/api/vacancies/{vid}/salary", json={"salary": ""})
    assert resp.status_code == 200
    row = await database.get_vacancy_by_id(vid)
    assert row["salary"] is None


@pytest.mark.asyncio
async def test_set_salary_not_found(client):
    """PATCH /api/vacancies/9999/salary returns 404 for missing vacancy."""
    resp = client.patch("/api/vacancies/9999/salary", json={"salary": "$5000"})
    assert resp.status_code == 404


# ── POST /api/vacancies/{id}/analyze ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_analyze_queues_vacancy(client):
    """POST /api/vacancies/{id}/analyze sets status=analysis_queued, returns 202."""
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/ana1/", status="fetched")
    resp = client.post(f"/api/vacancies/{vid}/analyze")
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "analysis_queued"
    row = await database.get_vacancy_by_id(vid)
    assert row["status"] == "analysis_queued"


@pytest.mark.asyncio
async def test_analyze_not_found(client):
    """POST /api/vacancies/9999/analyze returns 404."""
    resp = client.post("/api/vacancies/9999/analyze")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_analyze_already_queued_accepts(client):
    """POST /api/vacancies/{id}/analyze accepts analysis_queued (no worker attached in test)."""
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/ana2/", status="analysis_queued")
    resp = client.post(f"/api/vacancies/{vid}/analyze")
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_analyze_already_analyzing_returns_409(client):
    """POST /api/vacancies/{id}/analyze returns 409 when status=analyzing."""
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/ana3/", status="analyzing")
    resp = client.post(f"/api/vacancies/{vid}/analyze")
    assert resp.status_code == 409


# ── POST /api/vacancies/{id}/prefilter (EPIC-27, manual trigger only) ────────

def _set_llm_env(monkeypatch, tmp_path):
    """load_settings() requires these — set them so the endpoint doesn't 503
    on a dev machine's real .env leaking in via dotenv.load_dotenv()."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-dummy")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    monkeypatch.setenv("PROFILE_MD_PATH", str(tmp_path / "PROFILE.md"))
    (tmp_path / "PROFILE.md").write_text("# Profile", encoding="utf-8")


@pytest.mark.asyncio
async def test_prefilter_not_found(client):
    resp = client.post("/api/vacancies/9999/prefilter")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_prefilter_no_jd_returns_422(client):
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/pf1/", status="queued")
    resp = client.post(f"/api/vacancies/{vid}/prefilter")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_prefilter_missing_settings_returns_503(client, tmp_path):
    """core.settings does its own load_dotenv() on first import — patching
    load_settings() directly (not monkeypatch.delenv) avoids depending on
    whether some earlier test in the session already imported core.settings
    (which would have already loaded the real .env, making delenv+reload race
    against it — see EPIC-27 session notes)."""
    from unittest.mock import patch
    from core.settings import ConfigError as SettingsConfigError

    jd_path = tmp_path / "JD.md"
    jd_path.write_text("# JD", encoding="utf-8")
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/pf2/", status="fetched")
    await database.update_vacancy_fields(vid, markdown_path=str(jd_path))

    with patch("core.settings.load_settings", side_effect=SettingsConfigError("missing vars")):
        resp = client.post(f"/api/vacancies/{vid}/prefilter")
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_prefilter_happy_path_returns_result_and_persists(client, monkeypatch, tmp_path):
    from unittest.mock import AsyncMock, patch

    _set_llm_env(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "ollama_api")
    await database.insert_user(name="Pf", telegram_chat_id=8001, skill_type="pm")

    jd_path = tmp_path / "JD.md"
    jd_path.write_text("# JD\n\nRequires English C1.", encoding="utf-8")
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/pf3/", status="fetched", user_id=1)
    await database.update_vacancy_fields(vid, markdown_path=str(jd_path))

    with patch("core.llm_client.OllamaProvider") as MockOllama:
        instance = MockOllama.return_value
        instance.complete = AsyncMock(return_value="BLOCKED: yes\nREASONS:\n- english: requires C1")
        instance.last_call_usage = None
        resp = client.post(f"/api/vacancies/{vid}/prefilter")

    assert resp.status_code == 200
    data = resp.json()
    assert data == {
        "vacancy_id": vid, "ok": True, "blocked": True,
        "reasons": ["english: requires C1"],
        "raw_output": "BLOCKED: yes\nREASONS:\n- english: requires C1",
        "error": None, "provider_unavailable": False,
    }

    row = await database.get_vacancy_by_id(vid)
    assert row["blocker_flag"] == 1


@pytest.mark.asyncio
async def test_prefilter_format_mismatch_surfaces_as_not_ok(client, monkeypatch, tmp_path):
    """Regression guard for the exact #716 bug: a call that succeeds but whose
    output doesn't match the expected format must return ok=False, HTTP 200 —
    never look identical to a real 'no blockers' answer."""
    from unittest.mock import AsyncMock, patch

    _set_llm_env(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "ollama_api")
    await database.insert_user(name="Pf2", telegram_chat_id=8002, skill_type="pm")

    jd_path = tmp_path / "JD.md"
    jd_path.write_text("# JD\n\nRequires English C1.", encoding="utf-8")
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/pf4/", status="fetched", user_id=1)
    await database.update_vacancy_fields(vid, markdown_path=str(jd_path))

    with patch("core.llm_client.OllamaProvider") as MockOllama:
        instance = MockOllama.return_value
        instance.complete = AsyncMock(return_value="I think there might be some issues with this one...")
        instance.last_call_usage = None
        resp = client.post(f"/api/vacancies/{vid}/prefilter")

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["blocked"] is False
    assert data["raw_output"] == "I think there might be some issues with this one..."
    assert data["error"] is not None


@pytest.mark.asyncio
async def test_prefilter_ollama_down_flags_provider_unavailable(client, monkeypatch, tmp_path):
    """Ollama not running (or Claude API down, or claude CLI missing — same
    LLMUnavailableError for all three providers) must surface as
    provider_unavailable=True, not an opaque generic error. Gap found
    2026-07-17: this looked identical to any other failure before the fix."""
    from unittest.mock import AsyncMock, patch
    from core.llm_client import LLMUnavailableError

    _set_llm_env(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "ollama_api")
    await database.insert_user(name="Pf3", telegram_chat_id=8003, skill_type="pm")

    jd_path = tmp_path / "JD.md"
    jd_path.write_text("# JD\n\nRequires English C1.", encoding="utf-8")
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/pf5/", status="fetched", user_id=1)
    await database.update_vacancy_fields(vid, markdown_path=str(jd_path))

    with patch("core.llm_client.OllamaProvider") as MockOllama:
        instance = MockOllama.return_value
        instance.complete = AsyncMock(
            side_effect=LLMUnavailableError("Ollama unreachable at http://localhost:11434: connection refused")
        )
        resp = client.post(f"/api/vacancies/{vid}/prefilter")

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["provider_unavailable"] is True
    assert "unreachable" in data["error"].lower()


# ── POST /api/vacancies/{id}/reset ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_reset_analyzing_vacancy(client):
    """POST /api/vacancies/{id}/reset resets 'analyzing' → 'fetched', returns 200."""
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/rst1/", status="analyzing")
    resp = client.post(f"/api/vacancies/{vid}/reset")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "fetched"
    assert data["id"] == vid
    row = await database.get_vacancy_by_id(vid)
    assert row["status"] == "fetched"


@pytest.mark.asyncio
async def test_reset_analysis_failed_vacancy(client):
    """POST /api/vacancies/{id}/reset resets 'analysis_failed' → 'fetched'."""
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/rst2/", status="analysis_failed")
    resp = client.post(f"/api/vacancies/{vid}/reset")
    assert resp.status_code == 200
    row = await database.get_vacancy_by_id(vid)
    assert row["status"] == "fetched"


@pytest.mark.asyncio
async def test_reset_wrong_status_returns_400(client):
    """POST /api/vacancies/{id}/reset returns 400 for non-resettable statuses."""
    for status in ("fetched", "analyzed", "cv_generated", "declined"):
        vid = await database.insert_vacancy(
            url=f"https://djinni.co/jobs/rst-{status}/", status=status
        )
        resp = client.post(f"/api/vacancies/{vid}/reset")
        assert resp.status_code == 400, f"expected 400 for status={status}, got {resp.status_code}"
        assert status in resp.json()["detail"]


@pytest.mark.asyncio
async def test_reset_not_found(client):
    """POST /api/vacancies/9999/reset returns 404."""
    resp = client.post("/api/vacancies/9999/reset")
    assert resp.status_code == 404


# ── GET /api/vacancies/{id}/jd ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_vacancy_jd_returns_markdown(client, tmp_path):
    """GET /api/vacancies/{id}/jd returns jd_md when JD.md exists on disk."""
    jd_file = tmp_path / "JD.md"
    jd_file.write_text("# Senior PM\n\nJob description here.", encoding="utf-8")

    vid = await database.insert_vacancy(
        url="https://djinni.co/jobs/jd1/",
        markdown_path=str(jd_file),
    )
    resp = client.get(f"/api/vacancies/{vid}/jd")
    assert resp.status_code == 200
    data = resp.json()
    assert "jd_md" in data
    assert "Senior PM" in data["jd_md"]


@pytest.mark.asyncio
async def test_vacancy_jd_not_found_vacancy(client):
    """GET /api/vacancies/9999/jd returns 404 for missing vacancy."""
    resp = client.get("/api/vacancies/9999/jd")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_vacancy_jd_no_markdown_path(client):
    """GET /api/vacancies/{id}/jd returns 404 when markdown_path is null."""
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/jd2/")
    resp = client.get(f"/api/vacancies/{vid}/jd")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_vacancy_jd_file_missing_on_disk(client, tmp_path):
    """GET /api/vacancies/{id}/jd returns 404 when markdown_path points to nonexistent file."""
    vid = await database.insert_vacancy(
        url="https://djinni.co/jobs/jd3/",
        markdown_path=str(tmp_path / "nonexistent" / "JD.md"),
    )
    resp = client.get(f"/api/vacancies/{vid}/jd")
    assert resp.status_code == 404


# ── GET /api/config ────────────────────────────────────────────────────────────
#
# config_store seeds llm_provider from env on the first read, and that seed is
# a real DB write (user_settings FK → users). Each test below needs user_id=1
# to exist first — in production this is guaranteed by agent.py's startup
# (get_or_create_default_user); here it must be explicit.

@pytest.mark.asyncio
async def test_api_config_defaults(client, monkeypatch):
    """GET /api/config returns llm_provider, model, analysis_mode from env (defaults)."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("ANALYSIS_MODE", raising=False)
    await database.insert_user(name="CfgDefaults", telegram_chat_id=7100, skill_type="pm")
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["llm_provider"] == "claude_api"
    assert data["model"] == "claude-opus-4-5"
    assert data["analysis_mode"] == "inbox_first"


@pytest.mark.asyncio
async def test_api_config_custom_provider(client, monkeypatch):
    """GET /api/config reflects LLM_PROVIDER env var, lowercased."""
    monkeypatch.setenv("LLM_PROVIDER", "claude_cli")
    monkeypatch.setenv("LLM_MODEL", "claude-haiku-4-5-20251001")
    await database.insert_user(name="CfgCustom", telegram_chat_id=7101, skill_type="pm")
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["llm_provider"] == "claude_cli"
    assert data["model"] == "claude-haiku-4-5-20251001"


@pytest.mark.asyncio
async def test_api_config_provider_case_insensitive(client, monkeypatch):
    """GET /api/config lowercases LLM_PROVIDER value."""
    monkeypatch.setenv("LLM_PROVIDER", "Claude_CLI")
    await database.insert_user(name="CfgCase", telegram_chat_id=7102, skill_type="pm")
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json()["llm_provider"] == "claude_cli"


@pytest.mark.asyncio
async def test_api_config_auto_check_title_defaults_true(client):
    """GET /api/config exposes auto_check_title, default True (schema default)."""
    await database.insert_user(name="CfgAutoCheck", telegram_chat_id=7104, skill_type="pm")
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json()["auto_check_title"] is True


@pytest.mark.asyncio
async def test_api_config_patch_auto_check_title(client):
    await database.insert_user(name="CfgAutoCheckPatch", telegram_chat_id=7105, skill_type="pm")

    resp = client.patch("/api/config", json={"auto_check_title": False})
    assert resp.status_code == 200
    assert resp.json()["auto_check_title"] is False

    assert client.get("/api/config").json()["auto_check_title"] is False

    resp2 = client.patch("/api/config", json={"auto_check_title": True})
    assert resp2.json()["auto_check_title"] is True


@pytest.mark.asyncio
async def test_api_config_patch_auto_check_title_does_not_affect_llm_config(client, monkeypatch):
    """Flipping the title-stage flag must not disturb the active provider/model
    (same isolation guarantee as database.set_auto_check_title's own test)."""
    monkeypatch.setenv("LLM_PROVIDER", "claude_cli")
    await database.insert_user(name="CfgAutoCheckIso", telegram_chat_id=7106, skill_type="pm")
    client.get("/api/config")  # trigger env seed

    resp = client.patch("/api/config", json={"auto_check_title": False})
    assert resp.json()["llm_provider"] == "claude_cli"


@pytest.mark.asyncio
async def test_api_config_analysis_mode_full_auto(client, monkeypatch):
    """GET /api/config reflects ANALYSIS_MODE=full_auto."""
    monkeypatch.setenv("ANALYSIS_MODE", "full_auto")
    await database.insert_user(name="CfgMode", telegram_chat_id=7103, skill_type="pm")
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json()["analysis_mode"] == "full_auto"


@pytest.mark.asyncio
async def test_api_config_exposes_valid_providers(client):
    """GET /api/config includes the provider catalog for the Flutter dropdown."""
    await database.insert_user(name="CfgProviders", telegram_chat_id=7104, skill_type="pm")
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json()["valid_providers"] == ["claude_api", "claude_cli", "ollama_api"]


# ── PATCH /api/config — provider switch ──────────────────────────────────────

@pytest.mark.asyncio
async def test_patch_config_provider_persists(client, monkeypatch):
    """PATCH llm_provider stores a DB override that GET then reflects."""
    monkeypatch.setenv("LLM_PROVIDER", "claude_api")
    await database.insert_user(name="Cfg", telegram_chat_id=7001, skill_type="pm")

    resp = client.patch("/api/config", json={"llm_provider": "claude_cli"})
    assert resp.status_code == 200
    assert resp.json()["llm_provider"] == "claude_cli"

    # Persisted — a fresh GET reads the DB override, not the env default
    assert client.get("/api/config").json()["llm_provider"] == "claude_cli"


@pytest.mark.asyncio
async def test_patch_config_switch_resets_model(client, monkeypatch):
    """Switching provider drops the stored model → falls back to new provider's env default."""
    monkeypatch.setenv("LLM_PROVIDER", "claude_api")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:32b")
    await database.insert_user(name="Cfg2", telegram_chat_id=7002, skill_type="pm")

    # Pin a claude model first
    client.patch("/api/config", json={"model": "claude-opus-4-5"})
    # Switch to ollama → the claude model must not linger
    resp = client.patch("/api/config", json={"llm_provider": "ollama_api"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["llm_provider"] == "ollama_api"
    assert data["model"] == "qwen2.5:32b"
    row = await database.get_user_settings(1)
    assert row["llm_model"] is None


@pytest.mark.asyncio
async def test_patch_config_invalid_provider_422(client):
    """Unknown provider is rejected."""
    await database.insert_user(name="Cfg3", telegram_chat_id=7003, skill_type="pm")
    resp = client.patch("/api/config", json={"llm_provider": "gpt5"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_refresh_models_returns_list(client, monkeypatch):
    """POST /api/config/refresh-models force-fetches for the active provider."""
    monkeypatch.setenv("LLM_PROVIDER", "claude_cli")  # uses _FALLBACK_MODELS, no network
    await database.insert_user(name="RefreshModels", telegram_chat_id=7202, skill_type="pm")
    # Pin provider deterministically
    await database.set_user_settings(1, llm_provider="claude_cli", llm_model=None, thinking_effort="off")
    resp = client.post("/api/config/refresh-models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["llm_provider"] == "claude_cli"
    assert isinstance(data["available_models"], list)
    assert len(data["available_models"]) > 0


@pytest.mark.asyncio
async def test_refresh_models_force_bypasses_cache(client, monkeypatch):
    """force=True re-fetches even when a fresh cache entry exists."""
    from web.api import _get_available_models
    monkeypatch.setenv("LLM_PROVIDER", "claude_cli")
    # Seed a stale cache entry that a normal read would return
    await database.set_kv("models:claude_cli", '["stale-model"]')
    normal = await _get_available_models("claude_cli")
    assert normal == ["stale-model"]  # cache honoured without force
    forced = await _get_available_models("claude_cli", force=True)
    assert forced != ["stale-model"]  # force refetched the fallback catalog


@pytest.mark.asyncio
async def test_patch_config_provider_always_stored_explicitly(client, monkeypatch):
    """Single-source-of-truth seam: DB always holds the real provider value —
    no more 'store NULL when it equals env' trick from before config_store."""
    monkeypatch.setenv("LLM_PROVIDER", "claude_cli")
    await database.insert_user(name="Cfg4", telegram_chat_id=7004, skill_type="pm")

    resp = client.patch("/api/config", json={"llm_provider": "claude_cli"})
    assert resp.status_code == 200
    assert resp.json()["llm_provider"] == "claude_cli"
    row = await database.get_user_settings(1)
    assert row["llm_provider"] == "claude_cli"  # stored explicitly


# ── PATCH /api/config — drift guard (expected_provider) ──────────────────────

@pytest.mark.asyncio
async def test_patch_config_drift_guard_mismatch_409(client, monkeypatch):
    """Patching model/effort against a stale expected_provider is rejected —
    never silently attach a setting to a provider the backend already left."""
    monkeypatch.setenv("LLM_PROVIDER", "claude_api")
    await database.insert_user(name="Drift1", telegram_chat_id=7005, skill_type="pm")

    # Someone/something switches the backend to claude_cli in the meantime
    client.patch("/api/config", json={"llm_provider": "claude_cli"})

    # Flutter still thinks claude_api is active and tries to patch effort
    resp = client.patch("/api/config", json={"thinking_effort": "high", "expected_provider": "claude_api"})
    assert resp.status_code == 409
    assert "refresh" in resp.json()["detail"].lower()

    # And nothing was applied
    assert client.get("/api/config").json()["thinking_effort"] != "high"


@pytest.mark.asyncio
async def test_patch_config_drift_guard_match_succeeds(client, monkeypatch):
    """expected_provider matching the active one → patch applies normally."""
    monkeypatch.setenv("LLM_PROVIDER", "claude_api")
    await database.insert_user(name="Drift2", telegram_chat_id=7006, skill_type="pm")

    resp = client.patch("/api/config", json={"thinking_effort": "high", "expected_provider": "claude_api"})
    assert resp.status_code == 200
    assert resp.json()["thinking_effort"] == "high"


@pytest.mark.asyncio
async def test_patch_config_no_expected_provider_skips_guard(client, monkeypatch):
    """expected_provider is optional — omitting it never triggers 409 (back-compat)."""
    monkeypatch.setenv("LLM_PROVIDER", "claude_api")
    await database.insert_user(name="Drift3", telegram_chat_id=7007, skill_type="pm")
    client.patch("/api/config", json={"llm_provider": "claude_cli"})

    resp = client.patch("/api/config", json={"thinking_effort": "low"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_patch_config_switching_provider_ignores_expected_provider(client, monkeypatch):
    """Explicitly setting llm_provider never needs the guard — you're declaring
    the new truth, not assuming an old one."""
    monkeypatch.setenv("LLM_PROVIDER", "claude_api")
    await database.insert_user(name="Drift4", telegram_chat_id=7008, skill_type="pm")

    resp = client.patch(
        "/api/config", json={"llm_provider": "claude_cli", "expected_provider": "ollama_api"}
    )
    assert resp.status_code == 200
    assert resp.json()["llm_provider"] == "claude_cli"


# ── /api/config/phases (EPIC-27) ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_config_phases_lists_all_six_unpinned_by_default(client, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "claude_api")
    await database.insert_user(name="Phases1", telegram_chat_id=7200, skill_type="pm")

    resp = client.get("/api/config/phases")
    assert resp.status_code == 200
    phases = resp.json()["phases"]
    assert set(phases.keys()) == set(config_store.VALID_PHASES)
    assert all(p["is_override"] is False for p in phases.values())
    assert all(p["provider"] == "claude_api" for p in phases.values())


@pytest.mark.asyncio
async def test_patch_config_phase_pins_only_that_phase(client, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "claude_api")
    await database.insert_user(name="Phases2", telegram_chat_id=7201, skill_type="pm")

    resp = client.patch("/api/config/phases/prefilter", json={"provider": "ollama_api", "model": "gemma3:2b"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "ollama_api"
    assert body["model"] == "gemma3:2b"
    assert body["is_override"] is True

    phases = client.get("/api/config/phases").json()["phases"]
    assert phases["prefilter"]["provider"] == "ollama_api"
    assert phases["phase1"]["provider"] == "claude_api"  # unaffected


@pytest.mark.asyncio
async def test_patch_config_phase_unknown_phase_404(client, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "claude_api")
    await database.insert_user(name="Phases3", telegram_chat_id=7202, skill_type="pm")

    resp = client.patch("/api/config/phases/not_a_phase", json={"provider": "ollama_api"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_config_phase_bad_provider_422(client, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "claude_api")
    await database.insert_user(name="Phases4", telegram_chat_id=7203, skill_type="pm")

    resp = client.patch("/api/config/phases/phase1", json={"provider": "gpt5"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_config_phase_drift_guard_409(client, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "claude_api")
    await database.insert_user(name="Phases5", telegram_chat_id=7204, skill_type="pm")

    client.patch("/api/config/phases/prefilter", json={"provider": "ollama_api", "model": "gemma3:2b"})
    resp = client.patch(
        "/api/config/phases/prefilter",
        json={"model": "other-model", "expected_provider": "claude_api"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_delete_config_phase_resets_to_default(client, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "claude_api")
    await database.insert_user(name="Phases6", telegram_chat_id=7205, skill_type="pm")

    client.patch("/api/config/phases/prefilter", json={"provider": "ollama_api", "model": "gemma3:2b"})
    resp = client.delete("/api/config/phases/prefilter")
    assert resp.status_code == 200
    assert resp.json()["is_override"] is False
    assert resp.json()["provider"] == "claude_api"


@pytest.mark.asyncio
async def test_delete_config_phase_unknown_phase_404(client, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "claude_api")
    await database.insert_user(name="Phases7", telegram_chat_id=7206, skill_type="pm")

    resp = client.delete("/api/config/phases/not_a_phase")
    assert resp.status_code == 404


# ── Seed-once behavior via the API surface ───────────────────────────────────

@pytest.mark.asyncio
async def test_env_change_after_first_get_is_ignored(client, monkeypatch):
    """Once seeded via the first GET, a later .env edit has no runtime effect
    until a fresh process (or explicit provider switch) — this is the whole
    point of the seam: no ambiguity about who's authoritative."""
    monkeypatch.setenv("LLM_PROVIDER", "claude_cli")
    await database.insert_user(name="EnvIgnore", telegram_chat_id=7105, skill_type="pm")
    first = client.get("/api/config")
    assert first.json()["llm_provider"] == "claude_cli"

    monkeypatch.setenv("LLM_PROVIDER", "ollama_api")
    second = client.get("/api/config")
    assert second.json()["llm_provider"] == "claude_cli"  # unchanged


# ── key_barriers string coercion (legacy data guard) ─────────────────────────

@pytest.mark.asyncio
async def test_api_vacancies_key_barriers_string_coerced_to_list(client):
    """GET /api/vacancies coerces legacy key_barriers string → list.

    Old analysis_json could store key_barriers as plain string 'нет'.
    Flutter casts json['key_barriers'] as List — throws TypeError if string.
    Backend must coerce to [] or ['нет'] so response is always JSON array.
    """
    import json as _json
    uid = await database.insert_user(name="Alice", telegram_chat_id=9901, skill_type="pm")
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/legacy/", user_id=uid)

    # Inject legacy analysis_json with key_barriers as plain string
    legacy_json = _json.dumps({
        "p2": {
            "fit_score": 6,
            "recommendation": "apply",
            "key_barriers": "нет",   # legacy string — would crash Flutter
            "warnings": "нет",       # same issue
            "category": "PM",
            "who_they_want": "",
        }
    })
    # Write raw legacy JSON directly (patch_analysis_json merges, not replaces)
    import aiosqlite
    async with aiosqlite.connect(database._db_path) as db:
        await db.execute(
            "UPDATE vacancies SET analysis_json=?, status='analyzed' WHERE id=?",
            (legacy_json, vid),
        )
        await db.commit()

    resp = client.get("/api/vacancies")
    assert resp.status_code == 200
    items = resp.json()
    target = next((v for v in items if v["id"] == vid), None)
    assert target is not None
    assert isinstance(target["key_barriers"], list)
    assert isinstance(target.get("warnings", []), list)


# ── POST /api/vacancies/import-jd ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_import_jd_happy_path(client, tmp_path):
    """POST /api/vacancies/import-jd inserts vacancy, writes JD.md, returns 201."""
    uid = await database.insert_user(name="Importer", telegram_chat_id=9001, skill_type="pm")
    content = "# Senior PM\n\nWe are looking for a Senior PM with 5+ years experience."

    resp = client.post("/api/vacancies/import-jd", json={
        "content": content,
        "filename": "Senior PM — Acme.md",
        "user_id": uid,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "vacancy_id" in data
    assert data["title"] == "Senior PM"  # extracted from H1, not filename

    rows = await database.list_vacancies(status="fetched", user_id=uid)
    assert len(rows) == 1
    assert rows[0]["site"] == "manual"


@pytest.mark.asyncio
async def test_import_jd_auto_checks_title_by_default(client):
    """Stage 1 (2026-07-23) — auto_check_title defaults True (schema default),
    so a mismatching title gets blocker_flag set immediately, no LLM call."""
    uid = await database.insert_user(name="Importer2", telegram_chat_id=9002, skill_type="pm")
    content = "# Product Marketing Lead\n\nWe are looking for a marketing lead."

    resp = client.post("/api/vacancies/import-jd", json={
        "content": content,
        "filename": "Product Marketing Lead — Acme.md",
        "user_id": uid,
    })
    assert resp.status_code == 201
    vacancy_id = resp.json()["vacancy_id"]

    row = await database.get_vacancy_by_id(vacancy_id)
    assert row["blocker_flag"] == 1
    assert "title:" in row["blocker_reasons"]


@pytest.mark.asyncio
async def test_import_jd_skips_title_stage_when_setting_off(client):
    uid = await database.insert_user(name="Importer3", telegram_chat_id=9003, skill_type="pm")
    await database.set_auto_check_title(uid, False)
    content = "# Product Marketing Lead\n\nWe are looking for a marketing lead."

    resp = client.post("/api/vacancies/import-jd", json={
        "content": content,
        "filename": "Product Marketing Lead — Acme.md",
        "user_id": uid,
    })
    assert resp.status_code == 201
    vacancy_id = resp.json()["vacancy_id"]

    row = await database.get_vacancy_by_id(vacancy_id)
    assert row["blocker_flag"] == 0


@pytest.mark.asyncio
async def test_import_jd_empty_content(client):
    """POST /api/vacancies/import-jd with empty content returns 422."""
    resp = client.post("/api/vacancies/import-jd", json={
        "content": "   ",
        "filename": "test.md",
        "user_id": 1,
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_import_jd_too_large(client):
    """POST /api/vacancies/import-jd with content >200 KB returns 413."""
    big = "x" * 201_000
    resp = client.post("/api/vacancies/import-jd", json={
        "content": big,
        "filename": "huge.md",
        "user_id": 1,
    })
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_import_jd_duplicate_returns_409(client):
    """POST /api/vacancies/import-jd with same content twice returns 409."""
    uid = await database.insert_user(name="DupUser", telegram_chat_id=9002, skill_type="pm")
    content = "# PM Role\n\nThis is the job description."

    resp1 = client.post("/api/vacancies/import-jd", json={
        "content": content,
        "filename": "role.md",
        "user_id": uid,
    })
    assert resp1.status_code == 201

    resp2 = client.post("/api/vacancies/import-jd", json={
        "content": content,
        "filename": "role_copy.md",
        "user_id": uid,
    })
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_import_jd_title_strips_extension(client):
    """POST /api/vacancies/import-jd strips .md/.txt extension from filename for title."""
    uid = await database.insert_user(name="ExtUser", telegram_chat_id=9003, skill_type="pm")

    # No H1 in content → title falls back to filename (extension stripped)
    resp = client.post("/api/vacancies/import-jd", json={
        "content": "Job description without any heading here.",
        "filename": "Product Owner — StartupXYZ.txt",
        "user_id": uid,
    })
    assert resp.status_code == 201
    assert resp.json()["title"] == "Product Owner — StartupXYZ"


@pytest.mark.asyncio
async def test_import_jd_site_detection(client, tmp_path):
    """POST /api/vacancies/import-jd detects site from URL in content."""
    uid = await database.insert_user(name="SiteUser", telegram_chat_id=9004, skill_type="pm")

    cases = [
        ("https://djinni.co/jobs/123-pm", "djinni"),
        ("https://jobs.dou.ua/companies/acme/vacancies/456", "dou"),
        ("https://work.ua/jobs/789", "work"),
        ("No URL here at all.", "manual"),
    ]
    for i, (url_in_content, expected_site) in enumerate(cases):
        content = f"# Role {i}\n\nSource: {url_in_content}\n\nDescription."
        resp = client.post("/api/vacancies/import-jd", json={
            "content": content,
            "filename": f"role_{i}.md",
            "user_id": uid,
        })
        assert resp.status_code == 201, f"case {i}: {resp.text}"
        vid = resp.json()["vacancy_id"]
        rows = await database.list_vacancies(user_id=uid)
        row = next((dict(r) for r in rows if r["id"] == vid), None)
        assert row is not None
        assert row["site"] == expected_site, f"case {i}: expected {expected_site}, got {row['site']}"


@pytest.mark.asyncio
async def test_import_jd_title_extraction(client, tmp_path):
    """POST /api/vacancies/import-jd extracts clean role + company from content."""
    uid = await database.insert_user(name="TitleUser", telegram_chat_id=9005, skill_type="pm")

    # work.ua format
    content_work = (
        "# Вакансія Product Manager, Дистанційно, компанія Deus Robotics\n\n"
        "https://work.ua/jobs/123\n\nDescription here."
    )
    resp = client.post("/api/vacancies/import-jd", json={
        "content": content_work, "filename": "jd.md", "user_id": uid,
    })
    assert resp.status_code == 201
    assert resp.json()["title"] == "Product Manager"

    rows = await database.list_vacancies(user_id=uid)
    row = next(dict(r) for r in rows if r["id"] == resp.json()["vacancy_id"])
    assert row["company"] == "Deus Robotics"
    assert row["site"] == "work"

    # Generic H1, no company
    content_generic = "# Senior Product Owner\n\nWe are hiring a Senior PO."
    resp2 = client.post("/api/vacancies/import-jd", json={
        "content": content_generic, "filename": "po.md", "user_id": uid,
    })
    assert resp2.status_code == 201
    assert resp2.json()["title"] == "Senior Product Owner"
