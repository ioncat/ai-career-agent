"""
tests/test_web_api.py — contract tests for web/api.py endpoints.

Tests user_id filter on GET / and GET /api/vacancies, plus GET /api/users.
Uses FastAPI TestClient + real temp DB (no mocks).

Run: python -m pytest tests/test_web_api.py -v
"""

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from db import database


@pytest_asyncio.fixture(autouse=True)
async def temp_db(tmp_path, monkeypatch):
    """Point web/api.py and database module at a fresh temp DB."""
    db_path = tmp_path / "test.db"
    database.configure(db_path)
    await database.init_db()
    # Patch the env var read in web/api.py lifespan so it uses the same DB path
    monkeypatch.setenv("DB_PATH", str(db_path))
    yield


@pytest.fixture()
def client(tmp_path):
    """FastAPI TestClient with lifespan."""
    import os
    os.environ.setdefault("DB_PATH", str(tmp_path / "test.db"))
    from web.api import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


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
    vid = await database.insert_vacancy(url="https://example.com/sal1", title="Salary Test", user_id=1)
    resp = client.patch(f"/api/vacancies/{vid}/salary", json={"salary": "$4500"})
    assert resp.status_code == 200
    assert resp.json()["salary"] == "$4500"
    row = await database.get_vacancy_by_id(vid)
    assert row["salary"] == "$4500"


@pytest.mark.asyncio
async def test_set_salary_clear(client):
    """PATCH /api/vacancies/{id}/salary with empty string clears the field."""
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


# ── GET /api/config ────────────────────────────────────────────────────────────

def test_api_config_defaults(client, monkeypatch):
    """GET /api/config returns llm_provider and model from env (defaults)."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["llm_provider"] == "claude_api"
    assert data["model"] == "claude-opus-4-5"


def test_api_config_custom_provider(client, monkeypatch):
    """GET /api/config reflects LLM_PROVIDER env var, lowercased."""
    monkeypatch.setenv("LLM_PROVIDER", "claude_cli")
    monkeypatch.setenv("LLM_MODEL", "claude-haiku-4-5-20251001")
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["llm_provider"] == "claude_cli"
    assert data["model"] == "claude-haiku-4-5-20251001"


def test_api_config_provider_case_insensitive(client, monkeypatch):
    """GET /api/config lowercases LLM_PROVIDER value."""
    monkeypatch.setenv("LLM_PROVIDER", "Claude_CLI")
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json()["llm_provider"] == "claude_cli"
