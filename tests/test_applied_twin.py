"""
tests/test_applied_twin.py — "already applied" detection (EPIC-26).

Part 1: core.dedup.compute_applied_twins (pure — group walk, cycles, ties).
Part 2: database.get_applied_twin_id against a temp DB.
Part 3: API payloads (list + detail) and the analyze guard (409 / force=true).
"""

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from core.dedup import compute_applied_twins
from db import database


def _row(id, dup=None, poss=None, applied=0, applied_at=None, user_id=1):
    return {
        "id": id, "user_id": user_id, "duplicate_of": dup,
        "possible_duplicate_of": poss, "applied": applied, "applied_at": applied_at,
    }


# ── Part 1: pure helper ───────────────────────────────────────────────────────

def test_confirmed_link_to_applied_row():
    twins = compute_applied_twins([_row(1, applied=1, applied_at="2026-01-01 10:00:00"), _row(2, dup=1)])
    assert twins == {2: 1}


def test_possible_link_to_applied_row():
    twins = compute_applied_twins([_row(1, applied=1), _row(2, poss=1)])
    assert twins == {2: 1}


def test_reverse_link_applied_row_points_at_new_vacancy():
    """The applied row carries the link — the clean one still sees it."""
    twins = compute_applied_twins([_row(1), _row(2, dup=1, applied=1)])
    assert twins == {1: 2}


def test_applied_row_itself_gets_no_twin():
    twins = compute_applied_twins([_row(1, applied=1), _row(2, dup=1)])
    assert 1 not in twins


def test_transitive_chain_mixed_link_kinds():
    # 4 -> 3 (possible), 3 -> 2 (confirmed), 2 -> 1 (confirmed), 1 applied
    rows = [_row(1, applied=1), _row(2, dup=1), _row(3, dup=2), _row(4, poss=3)]
    assert compute_applied_twins(rows) == {2: 1, 3: 1, 4: 1}


def test_sibling_via_shared_original():
    """Two rows pointing at the same original are in one group."""
    rows = [_row(1, applied=1), _row(2, dup=1), _row(3, dup=1)]
    assert compute_applied_twins(rows) == {2: 1, 3: 1}


def test_cycle_does_not_hang_and_still_resolves():
    # hash-twin cycles (A<->B) exist in the real DB
    rows = [_row(205, dup=233), _row(233, dup=205), _row(300, poss=233, applied=1)]
    assert compute_applied_twins(rows) == {205: 300, 233: 300}


def test_cycle_without_applied_row_yields_nothing():
    assert compute_applied_twins([_row(1, dup=2), _row(2, dup=1)]) == {}


def test_unrelated_applied_row_is_ignored():
    assert compute_applied_twins([_row(1, applied=1), _row(2)]) == {}


def test_most_recent_applied_at_wins():
    rows = [
        _row(1, applied=1, applied_at="2026-03-01 09:00:00"),
        _row(2, dup=1, applied=1, applied_at="2026-05-01 09:00:00"),
        _row(3, dup=1),
    ]
    twins = compute_applied_twins(rows)
    assert twins == {3: 2}
    assert 1 not in twins and 2 not in twins  # applied rows get none


def test_applied_at_tie_falls_back_to_lowest_id():
    rows = [
        _row(7, applied=1, applied_at="2026-05-01 09:00:00"),
        _row(5, dup=7, applied=1, applied_at="2026-05-01 09:00:00"),
        _row(9, dup=7),
    ]
    assert compute_applied_twins(rows) == {9: 5}


def test_missing_applied_at_loses_to_dated_one_and_ties_by_id():
    rows = [
        _row(1, applied=1, applied_at=None),
        _row(2, dup=1, applied=1, applied_at="2026-01-01 00:00:00"),
        _row(3, dup=1),
    ]
    assert compute_applied_twins(rows) == {3: 2}
    rows = [_row(4, applied=1), _row(2, dup=4, applied=1), _row(3, dup=4)]
    assert compute_applied_twins(rows) == {3: 2}


def test_other_users_rows_are_not_in_the_group():
    rows = [_row(1, applied=1, user_id=2), _row(2, dup=1, user_id=1)]
    assert compute_applied_twins(rows) == {}


def test_null_user_id_counts_as_user_one():
    rows = [_row(1, applied=1, user_id=None), _row(2, dup=1, user_id=1)]
    assert compute_applied_twins(rows) == {2: 1}


def test_dangling_link_is_ignored():
    assert compute_applied_twins([_row(2, dup=999)]) == {}


# ── Part 2: DB helpers ────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def env(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    database.configure(db_path)
    await database.init_db()
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("VACANCIES_PATH", str(tmp_path / "vacancies"))
    uid = await database.insert_user("Test User")
    return {"uid": uid, "n": 0}


async def _add(env, status="fetched") -> int:
    env["n"] += 1
    return await database.insert_vacancy(
        url=f"https://example.org/jobs/{env['n']}", title="PM", company="Acme",
        user_id=env["uid"], status=status,
    )


@pytest.mark.asyncio
async def test_db_applied_twin_via_confirmed_and_possible(env):
    original = await _add(env)
    await database.set_vacancy_applied(original, True)
    repub = await _add(env)
    await database.set_duplicate_of(repub, original)
    maybe = await _add(env)
    await database.set_possible_duplicate_of(maybe, repub)  # chain: maybe -> repub -> original
    lone = await _add(env)

    assert await database.get_applied_twin_id(repub) == original
    assert await database.get_applied_twin_id(maybe) == original
    assert await database.get_applied_twin_id(original) is None
    assert await database.get_applied_twin_id(lone) is None
    assert await database.get_applied_twin_id(99999) is None


@pytest.mark.asyncio
async def test_db_applied_twin_reverse_link(env):
    clean = await _add(env)
    applied = await _add(env)
    await database.set_duplicate_of(applied, clean)
    await database.set_vacancy_applied(applied, True)
    assert await database.get_applied_twin_id(clean) == applied


@pytest.mark.asyncio
async def test_db_most_recent_applied_wins(env):
    a = await _add(env)
    b = await _add(env)
    new = await _add(env)
    await database.set_duplicate_of(b, a)
    await database.set_duplicate_of(new, a)
    await database.set_vacancy_applied(a, True)
    await database.set_vacancy_applied(b, True)
    async with database.get_db() as db:
        await db.execute("UPDATE vacancies SET applied_at = '2026-01-01 00:00:00' WHERE id = ?", (a,))
        await db.execute("UPDATE vacancies SET applied_at = '2026-06-01 00:00:00' WHERE id = ?", (b,))
        await db.commit()
    assert await database.get_applied_twin_id(new) == b


@pytest.mark.asyncio
async def test_db_unapplying_removes_the_twin(env):
    a = await _add(env)
    b = await _add(env)
    await database.set_duplicate_of(b, a)
    await database.set_vacancy_applied(a, True)
    assert await database.get_applied_twin_id(b) == a
    await database.set_vacancy_applied(a, False)
    assert await database.get_applied_twin_id(b) is None


# ── Part 3: API ───────────────────────────────────────────────────────────────

@pytest.fixture()
def client(env):
    from web.api import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


async def _twin_pair(env):
    applied = await _add(env, status="analyzed")
    await database.set_vacancy_applied(applied, True)
    twin = await _add(env, status="fetched")
    await database.set_duplicate_of(twin, applied)
    return applied, twin


@pytest.mark.asyncio
async def test_list_payload_has_applied_twin_id(client, env):
    applied, twin = await _twin_pair(env)
    lone = await _add(env)
    items = {i["id"]: i for i in client.get("/api/vacancies").json()}
    assert items[twin]["applied_twin_id"] == applied
    assert items[applied]["applied_twin_id"] is None
    assert items[lone]["applied_twin_id"] is None


@pytest.mark.asyncio
async def test_list_payload_twin_survives_status_filter_and_limit(client, env):
    """The applied twin is outside the filtered/limited page — still detected."""
    applied, twin = await _twin_pair(env)
    items = client.get("/api/vacancies?status=fetched&limit=1").json()
    assert [i["id"] for i in items] == [twin]
    assert items[0]["applied_twin_id"] == applied


@pytest.mark.asyncio
async def test_detail_payload_has_applied_twin_id(client, env):
    applied, twin = await _twin_pair(env)
    assert client.get(f"/api/vacancies/{twin}").json()["applied_twin_id"] == applied
    assert client.get(f"/api/vacancies/{applied}").json()["applied_twin_id"] is None


@pytest.mark.asyncio
async def test_analyze_blocked_when_applied_twin_exists(client, env):
    applied, twin = await _twin_pair(env)
    resp = client.post(f"/api/vacancies/{twin}/analyze")
    assert resp.status_code == 409
    assert resp.json()["detail"] == {"error": "already_applied", "applied_twin_id": applied}
    row = await database.get_vacancy_by_id(twin)
    assert row["status"] == "fetched"  # nothing was queued


@pytest.mark.asyncio
async def test_analyze_force_true_passes_through(client, env):
    _applied, twin = await _twin_pair(env)
    resp = client.post(f"/api/vacancies/{twin}/analyze?force=true")
    assert resp.status_code == 202
    row = await database.get_vacancy_by_id(twin)
    assert row["status"] == "analysis_queued"


@pytest.mark.asyncio
async def test_analyze_without_twin_unchanged(client, env):
    lone = await _add(env)
    assert client.post(f"/api/vacancies/{lone}/analyze").status_code == 202


@pytest.mark.asyncio
async def test_analyze_of_applied_row_itself_is_allowed(client, env):
    applied, _twin = await _twin_pair(env)
    assert client.post(f"/api/vacancies/{applied}/analyze").status_code == 202


@pytest.mark.asyncio
async def test_batch_style_sequence_skips_only_twins(client, env):
    """Flutter mass-action calls the single endpoint per id; twins come back 409
    already_applied (counted as skipped client-side), the rest are queued."""
    _applied, twin = await _twin_pair(env)
    lone = await _add(env)
    codes = {vid: client.post(f"/api/vacancies/{vid}/analyze").status_code for vid in (twin, lone)}
    assert codes == {twin: 409, lone: 202}
