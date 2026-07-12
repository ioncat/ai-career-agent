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
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("VACANCIES_PATH", str(tmp_path / "vacancies"))
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
async def test_new_vacancy_analyzed_still_409(client):
    """POST /api/new-vacancy for an analyzed (non-declined) vacancy still returns 409."""
    uid = await database.insert_user(name="AnalyzedUser", telegram_chat_id=5003, skill_type="pm")
    url = "https://djinni.co/jobs/402/"

    vid = await database.insert_vacancy(url=url, user_id=uid, published_at="2026-06-01T10:00:00")
    await database.update_vacancy_status(vid, "analyzed")

    resp = client.post("/api/new-vacancy", json={
        "url": url,
        "user_id": uid,
        "published_at": "2026-07-01T10:00:00",
    })
    assert resp.status_code == 409


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

def test_api_config_defaults(client, monkeypatch):
    """GET /api/config returns llm_provider, model, analysis_mode from env (defaults)."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("ANALYSIS_MODE", raising=False)
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["llm_provider"] == "claude_api"
    assert data["model"] == "claude-opus-4-5"
    assert data["analysis_mode"] == "inbox_first"


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


def test_api_config_analysis_mode_full_auto(client, monkeypatch):
    """GET /api/config reflects ANALYSIS_MODE=full_auto."""
    monkeypatch.setenv("ANALYSIS_MODE", "full_auto")
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json()["analysis_mode"] == "full_auto"


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
