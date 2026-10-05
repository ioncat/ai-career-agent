"""
tests/test_company_identity.py — company identity + text-first duplicate
detection + "applied at this company" hint (EPIC-26, 2026-10-05).

Part 1: pure helpers in core/dedup.py (profile_key, normalize_company_name,
        link graph / BFS, same_company, compute_company_applied).
Part 2: database — link learning, classify_duplicate text-first rules, cache.
Part 3: API payload field company_applied_id.
Part 4: scripts/company_profile_backfill.py and the --scan-missed report.
Part 5: fetch_jd stores company_profile_url.
"""

import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from core import dedup
from core.dedup import (
    TEXT_CONFIRM_THRESHOLD,
    build_link_graph,
    compute_company_applied,
    normalize_company_name,
    profile_group,
    profile_key,
    same_company,
)
from db import database

# The owner's real case: a Latin word with Cyrillic lookalike letters inside.
DRIPIFY_LOOKALIKE = "Drіріfy"  # "Dr" + Cyrillic i, er, i + "fy"
DRIPIFY = "Dripify"


def _words(prefix: str, n: int) -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def _jd(body: str) -> str:
    return f"# Role\n\nSource: https://example.org/1\n\n---\n\n{body}"


# ── Part 1: pure helpers ──────────────────────────────────────────────────────

@pytest.mark.parametrize("site,url,expected", [
    ("dou", "https://jobs.dou.ua/companies/dripify/", "dou:dripify"),
    ("dou", "https://jobs.dou.ua/companies/Dripify", "dou:dripify"),
    ("dou", "https://jobs.dou.ua/companies/dripify/vacancies/354206/?utm=1", "dou:dripify"),
    ("dou", "https://deftech.dou.ua/jobs/companies/everstar/", "dou:everstar"),
    ("djinni", "https://djinni.co/jobs/company-gypsy-collective/", "djinni:jobs/company-gypsy-collective"),
    ("djinni", "https://djinni.co/jobs/company-gypsy-collective", "djinni:jobs/company-gypsy-collective"),
    ("djinni", "/jobs/company-gypsy-collective/?x=1#frag", "djinni:jobs/company-gypsy-collective"),
    ("DJINNI", "https://DJINNI.co/jobs/Company-Influence-Pro-Services/", "djinni:jobs/company-influence-pro-services"),
])
def test_profile_key_shapes(site, url, expected):
    assert profile_key(site, url) == expected


@pytest.mark.parametrize("site,url", [
    (None, "https://jobs.dou.ua/companies/x/"), ("dou", None), ("dou", ""), ("dou", "   "),
    ("", "https://jobs.dou.ua/companies/x/"), ("dou", "https://jobs.dou.ua/"),
])
def test_profile_key_none_when_input_missing(site, url):
    assert profile_key(site, url) is None


def test_same_slug_on_two_boards_is_not_the_same_key():
    assert profile_key("dou", "https://jobs.dou.ua/companies/acme/") != \
        profile_key("djinni", "https://djinni.co/jobs/company-acme/")


def test_normalize_owner_case_lookalike_letters_fold_to_latin():
    assert normalize_company_name(DRIPIFY_LOOKALIKE) == "dripify"
    assert normalize_company_name(DRIPIFY_LOOKALIKE) == normalize_company_name(DRIPIFY)


def test_normalize_pure_cyrillic_name_is_untouched():
    # every letter of "Сорока" has a Latin lookalike (С, о, о, а) — still no fold
    assert normalize_company_name("Сорока") == "сорока"
    assert normalize_company_name("ПриватБанк") == "приватбанк"


def test_normalize_only_the_mixed_token_is_folded():
    # Cyrillic word next to a mixed token: the pure Cyrillic one stays Cyrillic
    out = normalize_company_name("Компанія Drірify")
    assert out == "компанія dripify"


def test_normalize_strips_legal_suffixes_and_punctuation():
    assert normalize_company_name("Acme, Inc.") == "acme"
    assert normalize_company_name("ACME LLC") == "acme"
    assert normalize_company_name("Acme Ltd") == "acme"
    assert normalize_company_name("Acme GmbH") == "acme"
    assert normalize_company_name("Acme Sp. z o.o.") == "acme"
    assert normalize_company_name("ТОВ Ромашка") == "ромашка"
    assert normalize_company_name("  Acme   —  Group  ") == "acme group"
    assert normalize_company_name("Acme") == normalize_company_name("ACME Inc")


def test_normalize_keeps_name_that_is_only_a_suffix_word():
    assert normalize_company_name("Inc") == "inc"
    assert normalize_company_name(None) == ""
    assert normalize_company_name("") == ""
    assert normalize_company_name("...") == ""


def test_normalize_nfkc_and_casefold():
    assert normalize_company_name("ＡＣＭＥ") == "acme"  # fullwidth
    assert normalize_company_name("STRAßE") == "strasse"


# ── link graph / BFS ──────────────────────────────────────────────────────────

def test_profile_group_bfs_is_transitive_and_includes_self():
    g = build_link_graph([("a", "b"), ("b", "c"), ("x", "y")])
    assert profile_group("a", g) == {"a", "b", "c"}
    assert profile_group("c", g) == {"a", "b", "c"}
    assert profile_group("x", g) == {"x", "y"}
    assert profile_group("lonely", g) == {"lonely"}
    assert profile_group(None, g) == frozenset()


def test_profile_group_handles_cycles():
    g = build_link_graph([("a", "b"), ("b", "c"), ("c", "a")])
    assert profile_group("b", g) == {"a", "b", "c"}


def test_build_link_graph_ignores_self_and_empty():
    assert build_link_graph([("a", "a"), ("", "b"), ("c", "")]) == {}


def _r(company, site=None, url=None, **kw):
    return {"company": company, "site": site, "company_profile_url": url, **kw}


def test_same_company_by_profile_group_even_with_different_names():
    a = _r("Acme", "dou", "https://jobs.dou.ua/companies/acme/")
    b = _r("Totally Different Name", "djinni", "https://djinni.co/jobs/company-acme-ua/")
    assert not same_company(a, b, {})
    g = build_link_graph([("dou:acme", "djinni:jobs/company-acme-ua")])
    assert same_company(a, b, g)


def test_same_company_falls_back_to_normalized_name():
    assert same_company(_r(DRIPIFY_LOOKALIKE), _r(DRIPIFY), {})
    assert same_company(_r("Acme Inc."), _r("ACME"), {})
    assert not same_company(_r("Acme"), _r("Acme Labs"), {})


def test_same_company_empty_names_never_match():
    assert not same_company(_r(""), _r(""), {})
    assert not same_company(_r(None), _r(None), {})


def test_same_company_same_profile_key_matches_without_names():
    a = _r(None, "dou", "https://jobs.dou.ua/companies/acme/")
    b = _r("", "dou", "https://jobs.dou.ua/companies/acme/vacancies/1")
    assert same_company(a, b, {})


def test_same_company_explicit_profile_key_entry_wins():
    a = {"company": "X", "profile_key": "dou:acme"}
    b = {"company": "Y", "profile_key": "dou:acme"}
    assert same_company(a, b, {})


# ── compute_company_applied ───────────────────────────────────────────────────

def _v(id, company, applied=0, applied_at=None, user_id=1, site=None, url=None):
    return {"id": id, "user_id": user_id, "company": company, "applied": applied,
            "applied_at": applied_at, "site": site, "company_profile_url": url}


def test_company_applied_basic_most_recent_wins():
    rows = [
        _v(1, "Acme", applied=1, applied_at="2026-01-01 00:00:00"),
        _v(2, "Acme", applied=1, applied_at="2026-06-01 00:00:00"),
        _v(3, "Acme"),
    ]
    assert compute_company_applied(rows) == {3: 2}


def test_company_applied_fallback_to_highest_id_without_applied_at():
    rows = [_v(1, "Acme", applied=1), _v(5, "Acme", applied=1), _v(9, "Acme")]
    assert compute_company_applied(rows) == {9: 5}


def test_company_applied_null_when_itself_applied():
    rows = [_v(1, "Acme", applied=1), _v(2, "Acme", applied=1)]
    assert compute_company_applied(rows) == {}


def test_company_applied_excludes_the_applied_twin_and_takes_the_next_one():
    rows = [
        _v(1, "Acme", applied=1, applied_at="2026-01-01 00:00:00"),
        _v(2, "Acme", applied=1, applied_at="2026-06-01 00:00:00"),  # the twin
        _v(3, "Acme"),
    ]
    assert compute_company_applied(rows, applied_twins={3: 2}) == {3: 1}


def test_company_applied_none_when_only_candidate_is_the_twin():
    rows = [_v(1, "Acme", applied=1), _v(3, "Acme")]
    assert compute_company_applied(rows, applied_twins={3: 1}) == {}


def test_company_applied_is_per_user():
    rows = [_v(1, "Acme", applied=1, user_id=2), _v(2, "Acme", user_id=1)]
    assert compute_company_applied(rows) == {}


def test_company_applied_matches_lookalike_name_and_cross_board_profile_link():
    rows = [
        _v(1, DRIPIFY, applied=1, site="dou", url="https://jobs.dou.ua/companies/dripify/"),
        _v(2, DRIPIFY_LOOKALIKE, site="djinni", url="https://djinni.co/jobs/company-x/"),
        _v(3, "Renamed Brand", site="djinni", url="https://djinni.co/jobs/company-renamed/"),
    ]
    assert compute_company_applied(rows) == {2: 1}
    g = build_link_graph([("dou:dripify", "djinni:jobs/company-renamed")])
    assert compute_company_applied(rows, g) == {2: 1, 3: 1}


def test_company_applied_empty_company_never_matches():
    rows = [_v(1, "", applied=1), _v(2, ""), _v(3, None)]
    assert compute_company_applied(rows) == {}


# ── Part 2: database ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def env(tmp_path):
    dedup.clear_shingle_cache()
    database.configure(tmp_path / "test.db")
    await database.init_db()
    uid = await database.insert_user("Test User")
    return {"tmp": tmp_path, "uid": uid, "n": 0}


async def _add(env, body, *, title="Product Manager", company="Acme", site=None,
               profile_url=None, url=None, write_file=True) -> int:
    env["n"] += 1
    n = env["n"]
    folder = env["tmp"] / f"v{n}"
    folder.mkdir()
    md = folder / "JD.md"
    if write_file and body is not None:
        md.write_text(_jd(body), encoding="utf-8")
    vid = await database.insert_vacancy(
        url=url or f"https://example.org/jobs/{n}", title=title, company=company,
        markdown_path=str(md), user_id=env["uid"], site=site,
    )
    if profile_url:
        await database.update_vacancy_fields(vid, company_profile_url=profile_url)
    return vid


def _norm(title="Product Manager"):
    return database._normalize_title(title, None)


async def _classify(env, body, **kw):
    kw.setdefault("title", "Product Manager")
    kw.setdefault("company", "Acme")
    title, company = kw.pop("title"), kw.pop("company")
    return await database.classify_duplicate(
        env["uid"], kw.pop("content_hash", None), _norm(title), company,
        new_text=_jd(body) if body is not None else None, **kw,
    )


@pytest.mark.asyncio
async def test_migration_adds_column_and_links_table(env):
    async with database.get_db() as db:
        cur = await db.execute("PRAGMA table_info(vacancies)")
        assert "company_profile_url" in {r["name"] for r in await cur.fetchall()}
        cur = await db.execute("PRAGMA table_info(company_profile_links)")
        assert {r["name"] for r in await cur.fetchall()} >= {
            "profile_key_a", "profile_key_b", "vacancy_a", "vacancy_b", "created_at"}


@pytest.mark.asyncio
async def test_update_vacancy_fields_stores_company_profile_url(env):
    vid = await _add(env, _words("a", 40))
    await database.update_vacancy_fields(vid, company_profile_url="https://jobs.dou.ua/companies/acme/")
    row = await database.get_vacancy_by_id(vid)
    assert row["company_profile_url"] == "https://jobs.dou.ua/companies/acme/"


# link learning

@pytest.mark.asyncio
async def test_confirmed_duplicate_across_boards_learns_a_link(env):
    orig = await _add(env, _words("a", 40), site="dou", profile_url="https://jobs.dou.ua/companies/dripify/")
    dup = await _add(env, _words("a", 40), site="djinni",
                     profile_url="https://djinni.co/jobs/company-dripify/")
    await database.set_duplicate_of(dup, orig)
    graph = await database.get_company_link_graph()
    assert profile_group("dou:dripify", graph) == {"dou:dripify", "djinni:jobs/company-dripify"}
    # idempotent: setting it again does not duplicate or fail
    await database.set_duplicate_of(dup, orig)
    async with database.get_db() as db:
        cur = await db.execute("SELECT * FROM company_profile_links")
        rows = await cur.fetchall()
    assert len(rows) == 1
    assert [rows[0]["profile_key_a"], rows[0]["profile_key_b"]] == sorted(
        ["dou:dripify", "djinni:jobs/company-dripify"])
    assert {rows[0]["vacancy_a"], rows[0]["vacancy_b"]} == {orig, dup}


@pytest.mark.asyncio
async def test_no_link_learned_for_possible_same_key_same_board_or_missing_keys(env):
    a = await _add(env, _words("a", 40), site="dou", profile_url="https://jobs.dou.ua/companies/one/")
    b = await _add(env, _words("a", 40), site="dou", profile_url="https://jobs.dou.ua/companies/two/")
    d = await _add(env, _words("a", 40), site="djinni")  # other board, no profile key
    await database.set_possible_duplicate_of(b, a)   # possible tier: never learned
    await database.set_duplicate_of(b, a)            # same board, different keys: not learned
    await database.set_duplicate_of(d, a)            # missing key
    assert await database.get_company_link_graph() == {}


# text-first classification

@pytest.mark.asyncio
async def test_text_first_confirms_across_different_company_and_title(env):
    body = _words("t", 80)
    orig = await _add(env, body, title="Totally Other Title", company="Other Co")
    verdict = await _classify(env, body, title="Product Owner", company="Dripify")
    assert verdict.confirmed_id == orig
    assert verdict.reason == "text"
    assert verdict.containment == 1.0


def _boundary(common: int) -> tuple[str, str]:
    base = _words("a", 104)  # 100 shingles
    return base, _words("a", common) + " " + _words("z", 104 - common)


@pytest.mark.asyncio
async def test_text_threshold_090_confirms_but_089_does_not(env):
    new_body, at = _boundary(94)       # 90/100 = 0.90
    _, below = _boundary(93)           # 89/100 = 0.89
    orig_at = await _add(env, at, title="Different", company="Elsewhere")
    verdict = await _classify(env, new_body, title="Product Owner", company="Dripify")
    assert verdict.containment == pytest.approx(0.90)
    assert verdict.confirmed_id == orig_at and verdict.reason == "text"
    assert TEXT_CONFIRM_THRESHOLD == 0.90

    env2_orig = await _add(env, below, title="Different", company="Elsewhere2")
    # remove the 0.90 candidate's influence by classifying with only the 0.89 one in scope
    verdict2 = await database.classify_duplicate(
        env["uid"], None, _norm("Product Owner"), "Dripify",
        new_text=_jd(new_body), before_id=orig_at,  # only rows older than orig_at: none
    )
    assert verdict2.confirmed_id is None
    # and directly: just the 0.89 row
    async with database.get_db() as db:
        await db.execute("DELETE FROM vacancies WHERE id = ?", (orig_at,))
        await db.commit()
    verdict3 = await _classify(env, new_body, title="Product Owner", company="Dripify")
    assert verdict3.confirmed_id is None and verdict3.possible_id is None
    assert env2_orig > 0


@pytest.mark.asyncio
async def test_text_only_candidate_below_threshold_is_never_possible(env):
    await _add(env, _words("a", 60), title="Other", company="Else")
    verdict = await _classify(env, _words("a", 30) + " " + _words("q", 30), title="X", company="Y")
    assert (verdict.confirmed_id, verdict.possible_id, verdict.reason) == (None, None, "none")


@pytest.mark.asyncio
async def test_title_company_still_needs_exact_title(env):
    """Owner rejected fuzzy title matching: a near-identical title is no match."""
    await _add(env, _words("a", 60), title="Product Manager", company="Acme")
    verdict = await _classify(env, _words("b", 60), title="Product Manager (Growth)", company="Acme")
    assert verdict.possible_id is None and verdict.confirmed_id is None
    exact = await _classify(env, _words("b", 60), title="Product Manager", company="Acme")
    assert exact.possible_id is not None


@pytest.mark.asyncio
async def test_title_company_uses_normalized_company_name(env):
    """The owner's case: same title, company spelled with Cyrillic lookalikes."""
    cand = await _add(env, _words("c", 60), title="Product Owner", company=DRIPIFY)
    verdict = await _classify(env, _words("d", 60), title="Product Owner", company=DRIPIFY_LOOKALIKE)
    assert verdict.possible_id == cand and verdict.confirmed_id is None


@pytest.mark.asyncio
async def test_title_company_confirms_at_080_with_same_company_via_profile_group(env):
    new_body, cand_body = _boundary(84)  # 0.80
    cand = await _add(env, cand_body, title="Product Owner", company="Brand A",
                      site="dou", profile_url="https://jobs.dou.ua/companies/branda/")
    # different company name, no link yet -> not the same company, 0.80 < text threshold
    none = await _classify(env, new_body, title="Product Owner", company="Brand B",
                           profile_key="djinni:jobs/company-brandb")
    assert none.confirmed_id is None and none.possible_id is None
    # learn that the two profile keys are the same employer
    async with database.get_db() as db:
        await db.execute(
            "INSERT INTO company_profile_links (profile_key_a, profile_key_b) VALUES (?, ?)",
            ("dou:branda", "djinni:jobs/company-brandb"))
        await db.commit()
    hit = await _classify(env, new_body, title="Product Owner", company="Brand B",
                          profile_key="djinni:jobs/company-brandb")
    assert hit.confirmed_id == cand and hit.reason == "title_company"
    assert hit.containment == pytest.approx(0.80)


@pytest.mark.asyncio
async def test_best_containment_wins_across_text_and_title_company_paths(env):
    body = _words("w", 80)
    partial = await _add(env, _words("w", 70) + " " + _words("zz", 20), title="Product Manager", company="Acme")  # tc, ~0.88
    perfect = await _add(env, body, title="Other Title", company="Elsewhere")                                     # text 1.0
    verdict = await _classify(env, body)
    assert verdict.confirmed_id == perfect and verdict.containment == 1.0
    assert partial < perfect


@pytest.mark.asyncio
async def test_text_ties_go_to_lowest_id(env):
    body = _words("w", 60)
    first = await _add(env, body, title="A", company="X")
    await _add(env, body, title="B", company="Y")
    verdict = await _classify(env, body, title="C", company="Z")
    assert verdict.confirmed_id == first


@pytest.mark.asyncio
async def test_text_window_excludes_old_candidates_and_replay_uses_as_of(env):
    body = _words("w", 60)
    old = await _add(env, body, title="A", company="X")
    async with database.get_db() as db:
        await db.execute("UPDATE vacancies SET created_at = '2026-01-01 00:00:00', "
                         "published_at = NULL WHERE id = ?", (old,))
        await db.commit()
    # now-relative window: 2026-01-01 is far older than 120 days
    assert (await _classify(env, body, title="C", company="Z")).confirmed_id is None
    # replay: the subject was itself created within 120 days of that row
    replay = await _classify(env, body, title="C", company="Z", as_of="2026-02-01 00:00:00")
    assert replay.confirmed_id == old


@pytest.mark.asyncio
async def test_text_window_counts_a_fresh_published_at(env):
    body = _words("w", 60)
    old = await _add(env, body, title="A", company="X")
    async with database.get_db() as db:
        await db.execute("UPDATE vacancies SET created_at = '2026-01-01 00:00:00', "
                         "published_at = datetime('now') WHERE id = ?", (old,))
        await db.commit()
    assert (await _classify(env, body, title="C", company="Z")).confirmed_id == old


@pytest.mark.asyncio
async def test_text_first_respects_exclude_before_and_user(env):
    body = _words("w", 60)
    a = await _add(env, body, title="A", company="X")
    me = await _add(env, body, title="B", company="Y")
    newer = await _add(env, body, title="C", company="Z")
    assert (await _classify(env, body, exclude_id=me, before_id=me, title="B", company="Y")).confirmed_id == a
    assert (await _classify(env, body, exclude_id=a, before_id=a, title="A", company="X")).confirmed_id is None
    other = await database.insert_user("Other")
    verdict = await database.classify_duplicate(other, None, _norm("A"), "X", new_text=_jd(body))
    assert verdict.confirmed_id is None
    assert newer > me


@pytest.mark.asyncio
async def test_hash_still_wins_over_text(env):
    twin = await _add(env, _words("x", 60), title="Other", company="Else")
    await database.set_content_hash(twin, "h1")
    await _add(env, _words("a", 60), title="Z", company="Z")
    verdict = await _classify(env, _words("a", 60), content_hash="h1")
    assert verdict.confirmed_id == twin and verdict.reason == "hash"


@pytest.mark.asyncio
async def test_no_new_text_means_no_text_scan(env):
    await _add(env, _words("a", 60), title="Other", company="Else")
    verdict = await _classify(env, None, title="Product Manager", company="Acme")
    assert verdict.confirmed_id is None and verdict.possible_id is None


@pytest.mark.asyncio
async def test_find_duplicate_wrappers_pass_profile_key(env):
    body = _words("w", 60)
    orig = await _add(env, body, title="A", company="X")
    assert await database.find_duplicate(env["uid"], None, _norm("Q"), "Y", new_text=_jd(body),
                                         profile_key="djinni:jobs/company-y") == orig
    assert await database.find_possible_duplicate(env["uid"], None, _norm("Q"), "Y",
                                                  new_text=_jd(body)) is None


# cache

@pytest.mark.asyncio
async def test_shingle_cache_reads_each_file_once(env):
    body = _words("w", 60)
    await _add(env, body, title="A", company="X")
    await _add(env, _words("v", 60), title="B", company="Y")
    dedup.clear_shingle_cache()
    await _classify(env, body, title="C", company="Z")
    assert dedup.cache_stats["misses"] == 2 and dedup.cache_stats["hits"] == 0
    await _classify(env, body, title="C", company="Z")
    assert dedup.cache_stats["misses"] == 2 and dedup.cache_stats["hits"] == 2


@pytest.mark.asyncio
async def test_shingle_cache_invalidates_when_file_changes(env):
    body = _words("w", 60)
    vid = await _add(env, _words("old", 60), title="A", company="X")
    assert (await _classify(env, body, title="C", company="Z")).confirmed_id is None
    path = Path((await database.get_vacancy_by_id(vid))["markdown_path"])
    path.write_text(_jd(body), encoding="utf-8")
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))  # force a new mtime
    verdict = await _classify(env, body, title="C", company="Z")
    assert verdict.confirmed_id == vid and verdict.containment == 1.0


def test_hashed_shingle_containment_equals_tuple_containment():
    a = _jd(_words("a", 70) + " " + _words("b", 30))
    b = _jd(_words("a", 50) + " " + _words("c", 40))
    exact = dedup.containment(a, b)
    hashed = dedup.shingle_containment(dedup.jd_shingle_hashes(a), dedup.jd_shingle_hashes(b))
    assert hashed == pytest.approx(exact)


@pytest.mark.asyncio
async def test_scoring_runs_off_the_event_loop(env, monkeypatch):
    await _add(env, _words("a", 60), title="A", company="X")
    seen = []
    real = dedup.asyncio.to_thread

    async def spy(func, *a, **kw):
        seen.append(func.__name__)
        return await real(func, *a, **kw)

    monkeypatch.setattr(dedup.asyncio, "to_thread", spy)
    await _classify(env, _words("a", 60), title="C", company="Z")
    assert "_score_candidates_sync" in seen


# ── Part 3: API payload ───────────────────────────────────────────────────────

@pytest.fixture()
def client(env, tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("VACANCIES_PATH", str(tmp_path / "vacancies"))
    from web.api import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


async def _simple(env, company, *, applied=False, status="fetched", site=None, profile_url=None):
    env["n"] += 1
    vid = await database.insert_vacancy(
        url=f"https://example.org/x/{env['n']}", title="PM", company=company,
        user_id=env["uid"], status=status, site=site,
    )
    if profile_url:
        await database.update_vacancy_fields(vid, company_profile_url=profile_url)
    if applied:
        await database.set_vacancy_applied(vid, True)
    return vid


@pytest.mark.asyncio
async def test_list_and_detail_payload_company_applied_id(client, env):
    applied = await _simple(env, DRIPIFY, applied=True, status="analyzed")
    other = await _simple(env, DRIPIFY_LOOKALIKE)       # same company by name folding
    unrelated = await _simple(env, "Somebody Else")
    items = {i["id"]: i for i in client.get("/api/vacancies").json()}
    assert items[other]["company_applied_id"] == applied
    assert items[applied]["company_applied_id"] is None
    assert items[unrelated]["company_applied_id"] is None
    assert client.get(f"/api/vacancies/{other}").json()["company_applied_id"] == applied
    assert client.get(f"/api/vacancies/{applied}").json()["company_applied_id"] is None


@pytest.mark.asyncio
async def test_company_applied_id_skips_the_applied_twin(client, env):
    older = await _simple(env, "Acme", applied=True)
    async with database.get_db() as db:
        await db.execute("UPDATE vacancies SET applied_at = '2026-01-01 00:00:00' WHERE id = ?", (older,))
        await db.commit()
    twin_orig = await _simple(env, "Acme", applied=True)
    async with database.get_db() as db:
        await db.execute("UPDATE vacancies SET applied_at = '2026-06-01 00:00:00' WHERE id = ?", (twin_orig,))
        await db.commit()
    new = await _simple(env, "Acme")
    await database.set_duplicate_of(new, twin_orig)
    item = client.get(f"/api/vacancies/{new}").json()
    assert item["applied_twin_id"] == twin_orig
    assert item["company_applied_id"] == older
    listed = {i["id"]: i for i in client.get("/api/vacancies").json()}
    assert listed[new]["company_applied_id"] == older


@pytest.mark.asyncio
async def test_company_applied_id_uses_learned_cross_board_link(client, env):
    applied = await _simple(env, "Brand A", applied=True, site="dou",
                            profile_url="https://jobs.dou.ua/companies/branda/")
    other = await _simple(env, "Brand B", site="djinni",
                          profile_url="https://djinni.co/jobs/company-brandb/")
    assert client.get(f"/api/vacancies/{other}").json()["company_applied_id"] is None
    async with database.get_db() as db:
        await db.execute("INSERT INTO company_profile_links (profile_key_a, profile_key_b) VALUES (?, ?)",
                         ("dou:branda", "djinni:jobs/company-brandb"))
        await db.commit()
    assert client.get(f"/api/vacancies/{other}").json()["company_applied_id"] == applied


@pytest.mark.asyncio
async def test_unknown_vacancy_company_applied_id_is_none(env):
    assert await database.get_company_applied_id(99999) is None


# ── Part 4: scripts ───────────────────────────────────────────────────────────

from scripts import company_profile_backfill as cpb  # noqa: E402
from scripts import dedup_backfill as ddb  # noqa: E402


def test_derive_dou_profile_url_shapes():
    d = cpb.derive_dou_profile_url
    assert d("https://jobs.dou.ua/companies/dripify/vacancies/354206") == "https://jobs.dou.ua/companies/dripify/"
    assert d("https://jobs.dou.ua/companies/paybis-com/vacancies/360309/") == "https://jobs.dou.ua/companies/paybis-com/"
    assert d("https://deftech.dou.ua/jobs/companies/everstar/vacancies/371") == "https://jobs.dou.ua/companies/everstar/"
    assert d("import://abc123/") is None
    assert d("https://djinni.co/jobs/1-pm/") is None
    assert d("https://jobs.dou.ua/vacancies/123/") is None
    assert d(None) is None


def test_plan_updates_counts():
    rows = [
        {"id": 1, "site": "dou", "url": "https://jobs.dou.ua/companies/a/vacancies/1", "company_profile_url": None},
        {"id": 2, "site": "dou", "url": "https://jobs.dou.ua/companies/b/vacancies/2", "company_profile_url": "https://x/"},
        {"id": 3, "site": "dou", "url": "import://zzz/", "company_profile_url": None},
        {"id": 4, "site": "djinni", "url": "https://djinni.co/jobs/4/", "company_profile_url": None},
    ]
    updates, counts = cpb.plan_updates(rows)
    assert updates == [(1, "https://jobs.dou.ua/companies/a/")]
    assert counts == {"dou_rows": 3, "already_set": 1, "to_fill": 1, "unmatched": 1, "other_sites": 1}


def _make_legacy_db(path: Path) -> None:
    """A DB as it was BEFORE this feature: vacancies without company_profile_url."""
    import sqlite3
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE vacancies (id INTEGER PRIMARY KEY, url TEXT NOT NULL UNIQUE, site TEXT)")
    con.executemany("INSERT INTO vacancies (id, url, site) VALUES (?, ?, ?)", [
        (1, "https://jobs.dou.ua/companies/dripify/vacancies/1", "dou"),
        (2, "https://jobs.dou.ua/companies/acme/vacancies/2", "dou"),
        (3, "import://abc/", "dou"),
        (4, "https://djinni.co/jobs/4-pm/", "djinni"),
    ])
    con.commit()
    con.close()


@pytest.mark.asyncio
async def test_backfill_dry_run_leaves_db_untouched_apply_writes(tmp_path):
    import sqlite3
    db = tmp_path / "legacy.db"
    _make_legacy_db(db)

    counts = await cpb.run(db, apply=False)
    assert counts["to_fill"] == 2 and counts["applied"] == 0
    con = sqlite3.connect(db)
    cols = {r[1] for r in con.execute("PRAGMA table_info(vacancies)")}
    con.close()
    assert "company_profile_url" not in cols  # dry run did not even migrate

    # apply needs the full schema (init_db adds the missing columns to an
    # existing vacancies table only if it has the base columns) — use a real schema DB
    db2 = tmp_path / "real.db"
    database.configure(db2)
    await database.init_db()
    for i, (url, site) in enumerate([
        ("https://jobs.dou.ua/companies/dripify/vacancies/1", "dou"),
        ("https://jobs.dou.ua/companies/acme/vacancies/2", "dou"),
        ("import://abc/", "dou"),
        ("https://djinni.co/jobs/4-pm/", "djinni"),
    ], start=1):
        await database.insert_vacancy(url=url, site=site, status="fetched")

    dry = await cpb.run(db2, apply=False)
    assert dry["to_fill"] == 2 and dry["applied"] == 0
    rows = await _profile_urls()
    assert all(v is None for v in rows.values())

    applied = await cpb.run(db2, apply=True)
    assert applied["applied"] == 2
    rows = await _profile_urls()
    assert sorted(v for v in rows.values() if v) == [
        "https://jobs.dou.ua/companies/acme/", "https://jobs.dou.ua/companies/dripify/"]
    # idempotent: a second apply has nothing left to fill
    again = await cpb.run(db2, apply=True)
    assert again["to_fill"] == 0 and again["already_set"] == 2


async def _profile_urls() -> dict[int, str | None]:
    async with database.get_db() as db:
        cur = await db.execute("SELECT id, company_profile_url FROM vacancies")
        return {r["id"]: r["company_profile_url"] for r in await cur.fetchall()}


@pytest.mark.asyncio
async def test_backfill_apply_migrates_a_legacy_schema_db(tmp_path):
    """Dry-run on a pre-feature DB works; --apply adds the column + table."""
    db = tmp_path / "pre.db"
    database.configure(db)
    await database.init_db()
    async with database.get_db() as db_:
        await db_.execute("ALTER TABLE vacancies DROP COLUMN company_profile_url")
        await db_.execute("DROP TABLE company_profile_links")
        await db_.commit()
    await database.insert_vacancy(url="https://jobs.dou.ua/companies/acme/vacancies/9", site="dou", status="fetched")

    counts = await cpb.run(db, apply=False)
    assert counts["to_fill"] == 1
    async with database.get_db() as db_:
        cur = await db_.execute("PRAGMA table_info(vacancies)")
        assert "company_profile_url" not in {r["name"] for r in await cur.fetchall()}

    counts = await cpb.run(db, apply=True)
    assert counts["applied"] == 1
    assert list((await _profile_urls()).values()) == ["https://jobs.dou.ua/companies/acme/"]


@pytest.mark.asyncio
async def test_scan_missed_finds_owner_case_and_never_writes(env, tmp_path, monkeypatch):
    monkeypatch.setattr(ddb, "_ROOT", tmp_path)
    body = _words("t", 80)
    a = await _add(env, body, title="Product Owner", company=DRIPIFY_LOOKALIKE, site="djinni",
                   url="https://djinni.co/jobs/832099-product-owner/")
    b = await _add(env, body, title="Product Owner", company=DRIPIFY, site="dou",
                   profile_url="https://jobs.dou.ua/companies/dripify/",
                   url="https://jobs.dou.ua/companies/dripify/vacancies/354206")
    c = await _add(env, _words("other", 80), title="AI Product Owner", company=DRIPIFY, site="dou",
                   profile_url="https://jobs.dou.ua/companies/dripify/",
                   url="https://jobs.dou.ua/companies/dripify/vacancies/354121")
    await database.set_vacancy_applied(c, True)

    before = await _profile_urls()
    findings, by_id = await ddb._scan_missed()
    by_new = {f["id"]: f for f in findings}
    # replay order: the later row (b) points at the older original (a)
    assert by_new[b]["orig"] == a and by_new[b]["state"] == "confirmed"
    assert a not in by_new and c not in by_new
    assert await _profile_urls() == before
    async with database.get_db() as db:
        cur = await db.execute("SELECT duplicate_of, possible_duplicate_of FROM vacancies")
        assert all(tuple(r) == (None, None) for r in await cur.fetchall())

    report = await ddb.build_missed_report(findings, by_id, [a, b, c])
    assert "Контрольные пары" in report and f"#{b} -> #{a}: confirmed" in report


@pytest.mark.asyncio
async def test_scan_missed_skips_already_flagged_rows(env, tmp_path, monkeypatch):
    monkeypatch.setattr(ddb, "_ROOT", tmp_path)
    body = _words("t", 80)
    a = await _add(env, body, title="A", company="X")
    b = await _add(env, body, title="B", company="Y")
    await database.set_duplicate_of(b, a)
    findings, _ = await ddb._scan_missed()
    assert findings == []


def test_scan_missed_cannot_combine_with_apply(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.argv", ["dedup_backfill.py", "--db", str(tmp_path / "x.db"),
                                     "--scan-missed", "--apply"])
    with pytest.raises(SystemExit):
        ddb.main()


# ── Part 5: fetch_jd stores the profile URL ───────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_jd_saves_company_profile_url_and_passes_profile_key(tmp_path):
    from unittest.mock import MagicMock
    from contracts.parsed_document import ParsedDocument
    from tools.cv_fetch_jd import fetch_jd

    doc = ParsedDocument(
        title="Product Owner", markdown="## Job\nGreat role.", source_url="https://djinni.co/jobs/1-po/",
        company="Dripify", company_profile_url="https://djinni.co/jobs/company-dripify/",
    )
    parser = AsyncMock()
    parser.fetch_markdown = AsyncMock(return_value=doc)
    deps = MagicMock()
    deps.parser_adapter = parser
    deps.vacancies_path = tmp_path / "vacancies"
    deps.user_id = 1
    deps.djinni_salary_adapter = None

    with patch("tools.cv_fetch_jd.database") as mock_db, \
         patch("tools.cv_fetch_jd.asyncio.create_task"):
        mock_db.get_vacancy_by_url = AsyncMock(return_value=None)
        mock_db.insert_vacancy = AsyncMock(return_value=77)
        mock_db.update_vacancy_fields = AsyncMock()
        mock_db._normalize_title = database._normalize_title
        mock_db.classify_duplicate = AsyncMock(return_value=database.DuplicateVerdict())
        mock_db.clear_duplicate_flags = AsyncMock()
        mock_db.set_content_hash = AsyncMock()
        mock_db.update_vacancy_status = AsyncMock()

        await fetch_jd(deps, "https://djinni.co/jobs/1-po/")

    assert mock_db.update_vacancy_fields.call_args.kwargs["company_profile_url"] == \
        "https://djinni.co/jobs/company-dripify/"
    assert mock_db.classify_duplicate.call_args.kwargs["profile_key"] == "djinni:jobs/company-dripify"
    mock_db.classify_duplicate.assert_awaited_once()
