"""
tests/test_flutter_endpoints.py — FastAPI endpoints for Flutter (B3).

Tests: GET /api/vacancies (with since/status filter + analysis fields),
       GET /api/vacancies/{id}/analysis, GET /api/vacancies/{id}/cv.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from contracts.pipeline import (
    AnalysisJson,
    FitDimensions,
    Phase1Data,
    Phase2Data,
    VacScoreDims,
)
from db import database


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "")
    from web.api import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture()
async def db_with_vacancies(tmp_path):
    database.configure(tmp_path / "test.db")
    await database.init_db()
    await database.insert_user(name="Alice", telegram_chat_id=1)
    return tmp_path


def _make_analysis_json(fit: int = 7, rec: str = "apply", vscore: float = 8.1) -> str:
    dims = VacScoreDims(
        company_tier=3, seniority=4, market_scope=2, company_type=3,
        company_stage_fit=2, domain_score=4, remote_policy=3, compensation=2,
    )
    p1 = Phase1Data(
        role="Product Manager", company="Acme", north_star="PM ships CRM.",
        primary_archetype="Execution-heavy PM", company_type="product",
        role_balance={"strategy": 20, "execution": 80},
        dominant_culture="ownership", vacscore_dims=dims, vacancy_score=vscore,
    )
    p2 = Phase2Data(
        fit_score=fit, recommendation=rec,
        recommendation_label=f"{rec.replace('_', ' ')} — strong match" if rec == "apply" else rec.replace("_", " "),
        category="Execution-heavy PM · Remote", who_they_want="A senior PM.",
        key_barriers=["no CRM direct ownership"],
        hidden_risks=["early-stage"],
        warnings=[],
        fit_dimensions=FitDimensions(
            domain_fit=7, execution_fit=8, strategy_fit=6,
            systems_fit=7, stakeholder_fit=6, overall_fit=7,
        ),
    )
    return AnalysisJson(p1=p1, p2=p2).model_dump_json(exclude_none=True)


# ── GET /api/vacancies — basic ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_vacancies_empty(client, db_with_vacancies):
    database.configure(db_with_vacancies / "test.db")
    resp = client.get("/api/vacancies")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_vacancies_returns_vacancy(client, db_with_vacancies):
    database.configure(db_with_vacancies / "test.db")
    await database.insert_vacancy(url="https://djinni.co/jobs/1", title="PM at Acme", user_id=1)

    resp = client.get("/api/vacancies")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["title"] == "PM at Acme"


@pytest.mark.asyncio
async def test_list_vacancies_applied_starred_are_bool(client, db_with_vacancies):
    database.configure(db_with_vacancies / "test.db")
    await database.insert_vacancy(url="https://djinni.co/jobs/2", user_id=1)

    resp = client.get("/api/vacancies")
    item = resp.json()[0]
    assert isinstance(item["applied"], bool)
    assert isinstance(item["starred"], bool)
    assert item["applied"] is False
    assert item["starred"] is False


@pytest.mark.asyncio
async def test_list_vacancies_analysis_fields_extracted(client, db_with_vacancies):
    database.configure(db_with_vacancies / "test.db")
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/3", user_id=1)
    await database.patch_analysis_json(vid, "p1", json.loads(_make_analysis_json())["p1"])
    await database.patch_analysis_json(vid, "p2", json.loads(_make_analysis_json())["p2"])

    resp = client.get("/api/vacancies")
    item = resp.json()[0]
    assert item["fit_score"] == 7
    assert item["recommendation"] == "apply"
    assert item["vacancy_score"] == 8.1
    assert "no CRM direct ownership" in item["key_barriers"]
    assert "analysis_json" not in item


@pytest.mark.asyncio
async def test_list_vacancies_no_analysis_fields_when_not_run(client, db_with_vacancies):
    database.configure(db_with_vacancies / "test.db")
    await database.insert_vacancy(url="https://djinni.co/jobs/4", user_id=1)

    resp = client.get("/api/vacancies")
    item = resp.json()[0]
    assert "fit_score" not in item
    assert "recommendation" not in item


# ── GET /api/vacancies — since filter ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_vacancies_since_filters_old_rows(client, db_with_vacancies):
    database.configure(db_with_vacancies / "test.db")
    await database.insert_vacancy(url="https://djinni.co/jobs/5", user_id=1)

    resp = client.get("/api/vacancies?since=2030-01-01T00:00:00")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_vacancies_since_returns_recent(client, db_with_vacancies):
    database.configure(db_with_vacancies / "test.db")
    await database.insert_vacancy(url="https://djinni.co/jobs/6", user_id=1)

    resp = client.get("/api/vacancies?since=2000-01-01T00:00:00")
    assert len(resp.json()) == 1


# ── GET /api/vacancies — status filter ────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_vacancies_status_filter(client, db_with_vacancies):
    database.configure(db_with_vacancies / "test.db")
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/7", user_id=1)
    await database.update_vacancy_status(vid, "analyzed")
    await database.insert_vacancy(url="https://djinni.co/jobs/8", user_id=1)  # stays fetched

    resp = client.get("/api/vacancies?status=analyzed")
    items = resp.json()
    assert len(items) == 1
    assert items[0]["status"] == "analyzed"


# ── GET /api/vacancies/{id}/analysis ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_analysis_endpoint_404_unknown(client, db_with_vacancies):
    database.configure(db_with_vacancies / "test.db")
    resp = client.get("/api/vacancies/999/analysis")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_analysis_endpoint_empty_when_not_run(client, db_with_vacancies):
    database.configure(db_with_vacancies / "test.db")
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/9", user_id=1)

    resp = client.get(f"/api/vacancies/{vid}/analysis")
    assert resp.status_code == 200
    assert resp.json() == {}


@pytest.mark.asyncio
async def test_analysis_endpoint_returns_structured_json(client, db_with_vacancies):
    database.configure(db_with_vacancies / "test.db")
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/10", user_id=1)
    aj_data = json.loads(_make_analysis_json(fit=8, rec="apply", vscore=9.0))
    await database.patch_analysis_json(vid, "p1", aj_data["p1"])
    await database.patch_analysis_json(vid, "p2", aj_data["p2"])

    resp = client.get(f"/api/vacancies/{vid}/analysis")
    assert resp.status_code == 200
    body = resp.json()
    assert body["p2"]["fit_score"] == 8
    assert body["p2"]["recommendation"] == "apply"
    assert body["p1"]["vacancy_score"] == 9.0
    assert "p3" not in body
    assert "p4" not in body


@pytest.mark.asyncio
async def test_analysis_endpoint_valid_against_pydantic(client, db_with_vacancies):
    database.configure(db_with_vacancies / "test.db")
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/11", user_id=1)
    aj_data = json.loads(_make_analysis_json())
    await database.patch_analysis_json(vid, "p1", aj_data["p1"])
    await database.patch_analysis_json(vid, "p2", aj_data["p2"])

    resp = client.get(f"/api/vacancies/{vid}/analysis")
    aj = AnalysisJson.model_validate(resp.json())
    assert aj.p1 is not None
    assert aj.p2 is not None


@pytest.mark.asyncio
async def test_analysis_endpoint_includes_analyzed_at_from_pipeline_runs(client, db_with_vacancies):
    """analyzed_at must come from pipeline_runs (real Phase 2 completion),
    not vacancies.updated_at — regression for 2026-08-11, vacancy #597."""
    database.configure(db_with_vacancies / "test.db")
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/12", user_id=1)
    aj_data = json.loads(_make_analysis_json())
    await database.patch_analysis_json(vid, "p1", aj_data["p1"])
    await database.patch_analysis_json(vid, "p2", aj_data["p2"])
    run_id = await database.insert_pipeline_run(vid, "phase2")
    await database.update_pipeline_run(run_id, "done", result_path="vacancies/job-12/analysis.md")

    resp = client.get(f"/api/vacancies/{vid}/analysis")
    body = resp.json()
    assert body["analyzed_at"] is not None


@pytest.mark.asyncio
async def test_analysis_endpoint_omits_analyzed_at_without_pipeline_run(client, db_with_vacancies):
    """No phase2 pipeline_runs row (e.g. legacy data) → key absent, not null."""
    database.configure(db_with_vacancies / "test.db")
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/13", user_id=1)
    aj_data = json.loads(_make_analysis_json())
    await database.patch_analysis_json(vid, "p1", aj_data["p1"])
    await database.patch_analysis_json(vid, "p2", aj_data["p2"])

    resp = client.get(f"/api/vacancies/{vid}/analysis")
    body = resp.json()
    assert "analyzed_at" not in body


# ── GET /api/vacancies/{id}/cv ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cv_endpoint_404_unknown(client, db_with_vacancies):
    database.configure(db_with_vacancies / "test.db")
    resp = client.get("/api/vacancies/999/cv")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cv_endpoint_empty_when_no_markdown_path(client, db_with_vacancies):
    database.configure(db_with_vacancies / "test.db")
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/12", user_id=1)

    resp = client.get(f"/api/vacancies/{vid}/cv")
    assert resp.status_code == 200
    assert resp.json() == {}


@pytest.mark.asyncio
async def test_cv_endpoint_returns_cv_md(client, db_with_vacancies, tmp_path):
    database.configure(db_with_vacancies / "test.db")
    vacancy_folder = tmp_path / "vacancies" / "test_job"
    vacancy_folder.mkdir(parents=True)
    jd = vacancy_folder / "JD.md"
    jd.write_text("# Job Description", encoding="utf-8")
    cv = vacancy_folder / "Alex_CV.md"
    cv.write_text("# Alex Bondarenko\n\nProduct Manager", encoding="utf-8")

    vid = await database.insert_vacancy(url="https://djinni.co/jobs/13", user_id=1)
    await database.update_vacancy_fields(vid, markdown_path=str(jd))

    resp = client.get(f"/api/vacancies/{vid}/cv")
    assert resp.status_code == 200
    body = resp.json()
    assert "cv_md" in body
    assert "Alex Bondarenko" in body["cv_md"]
    assert "cover_md" not in body


@pytest.mark.asyncio
async def test_cv_endpoint_returns_cover_md(client, db_with_vacancies, tmp_path):
    database.configure(db_with_vacancies / "test.db")
    vacancy_folder = tmp_path / "vacancies" / "test_job2"
    vacancy_folder.mkdir(parents=True)
    jd = vacancy_folder / "JD.md"
    jd.write_text("# JD", encoding="utf-8")
    cover = vacancy_folder / "Cover.md"
    cover.write_text("Вітаю!\n\nПовідомлення.", encoding="utf-8")

    vid = await database.insert_vacancy(url="https://djinni.co/jobs/14", user_id=1)
    await database.update_vacancy_fields(vid, markdown_path=str(jd))

    resp = client.get(f"/api/vacancies/{vid}/cv")
    body = resp.json()
    assert "cover_md" in body
    assert "Вітаю" in body["cover_md"]


@pytest.mark.asyncio
async def test_cv_endpoint_returns_both_cv_and_cover(client, db_with_vacancies, tmp_path):
    database.configure(db_with_vacancies / "test.db")
    vacancy_folder = tmp_path / "vacancies" / "test_job3"
    vacancy_folder.mkdir(parents=True)
    jd = vacancy_folder / "JD.md"
    jd.write_text("# JD", encoding="utf-8")
    (vacancy_folder / "Alex_CV.md").write_text("# CV", encoding="utf-8")
    (vacancy_folder / "Cover.md").write_text("# Cover", encoding="utf-8")

    vid = await database.insert_vacancy(url="https://djinni.co/jobs/15", user_id=1)
    await database.update_vacancy_fields(vid, markdown_path=str(jd))

    resp = client.get(f"/api/vacancies/{vid}/cv")
    body = resp.json()
    assert "cv_md" in body
    assert "cover_md" in body


# ── GET /api/users/{id}/progressive_profile (EPIC-24 T8) ─────────────────────

@pytest.mark.asyncio
async def test_progressive_profile_returns_seeded_roles(client, db_with_vacancies):
    """T8: GET /api/users/{id}/progressive_profile returns JSON with roles."""
    database.configure(db_with_vacancies / "test.db")
    profile = {
        "meta": {"schema_version": 1, "last_updated": "2026-07-05"},
        "roles": [{"id": "test_role", "title": "Product Owner", "company": "Acme"}],
    }
    import json
    con = __import__("sqlite3").connect(str(db_with_vacancies / "test.db"))
    con.execute("UPDATE users SET progressive_profile = ? WHERE id = 1", (json.dumps(profile),))
    con.commit()
    con.close()

    resp = client.get("/api/users/1/progressive_profile")
    assert resp.status_code == 200
    body = resp.json()
    assert "roles" in body
    assert body["roles"][0]["company"] == "Acme"


@pytest.mark.asyncio
async def test_progressive_profile_returns_empty_when_null(client, db_with_vacancies):
    """T8: endpoint returns empty roles list when profile not yet seeded."""
    database.configure(db_with_vacancies / "test.db")
    resp = client.get("/api/users/1/progressive_profile")
    assert resp.status_code == 200
    body = resp.json()
    assert body["roles"] == []


@pytest.mark.asyncio
async def test_progressive_profile_404_unknown_user(client, db_with_vacancies):
    """T8: 404 for non-existent user."""
    database.configure(db_with_vacancies / "test.db")
    resp = client.get("/api/users/999/progressive_profile")
    assert resp.status_code == 404
